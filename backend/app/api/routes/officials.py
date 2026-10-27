"""Officials: CRUD, search, per-field provenance, verification, and timeline."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import false, func, or_, select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models.audit import AuditLog
from ...models.official import (
    FieldVerification,
    Official,
    OfficialFieldProvenance,
    OfficialStatus,
    PROVENANCED_FIELDS,
    VerificationStatus,
)
from ...models.commitment import Commitment, CommitmentStatus
from ...models.intelligence_feedback import SUBJECT_OFFICIAL
from ...models.official_date import DateKind, OfficialDate
from ...models.organization_unit import OrganizationUnit
from ...models.user import Role, User
from ...schemas.official import (
    FieldProvenanceOut,
    OfficialCreate,
    OfficialDetail,
    OfficialListResponse,
    OfficialSummary,
    OfficialUpdate,
    SetFieldRequest,
    TimelineEntry,
)
from ...schemas.intelligence import CommitmentStatusUpdate, DuplicateDecision, FeedbackIn
from ...schemas.official_date import DateSet, OfficialDateOut
from ...security.deps import get_current_user, require_roles
from ...services import audit
from ...services import commitments as commitments_svc
from ...services import intelligence_feedback as feedback_svc
from ...services import official_intel
from ...services.dc_territory import can_access_unit, visible_unit_ids
from ...services.officials import recompute_verification

router = APIRouter(prefix="/officials", tags=["officials"])

_EDITORS = require_roles(Role.ADMIN, Role.RELATIONSHIP_MANAGER, Role.DC)
_SORTABLE = {
    "name": Official.name,
    "-name": Official.name.desc(),
    "updated_at": Official.updated_at,
    "-updated_at": Official.updated_at.desc(),
}


def _detail(official: Official) -> OfficialDetail:
    fields = {
        p.field: FieldProvenanceOut.model_validate(p)
        for p in official.field_provenance
    }
    base = OfficialSummary.model_validate(official).model_dump()
    return OfficialDetail(**base, department=official.department, fields=fields)


def _scoped_official(db: Session, official_id: int, actor: User) -> Official:
    """A DC only ever sees/acts on officials inside their own territory -
    enforced here, not just by hiding the search results, so a guessed id
    can't be used to read or edit an out-of-territory official either."""
    official = db.get(Official, official_id)
    if official is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Official not found")
    if actor.role is Role.RELATIONSHIP_MANAGER:
        # An RM has no access to SBI officials (CSPs only).
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Official not found")
    if actor.role is Role.DC:
        if official.organization_unit_id is None or official.organization_unit_id not in visible_unit_ids(
            db, actor.id
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Official not found")
    return official


@router.get("", response_model=OfficialListResponse)
def list_officials(
    q: str | None = None,
    unit_id: int | None = None,
    level: str | None = None,
    verification_status: VerificationStatus | None = None,
    status_filter: OfficialStatus = Query(default=OfficialStatus.ACTIVE, alias="status"),
    sort: str = Query(default="name"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    if sort not in _SORTABLE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown sort key")

    filters = [Official.status == status_filter]
    if q:
        pattern = f"%{q}%"
        filters.append(
            or_(
                Official.name.ilike(pattern),
                Official.phone.ilike(pattern),
                Official.designation.ilike(pattern),
            )
        )
    if unit_id is not None:
        filters.append(Official.organization_unit_id == unit_id)
    if level:
        filters.append(Official.level == level)
    if verification_status is not None:
        filters.append(Official.verification_status == verification_status)
    if actor.role is Role.DC:
        # A DC sees officials in their own territory, plus ones recorded at an
        # ancestor RBO/AO (e.g. that area's shared Field Investigator).
        scoped_units = visible_unit_ids(db, actor.id)
        filters.append(
            Official.organization_unit_id.in_(scoped_units) if scoped_units else false()
        )
    elif actor.role is Role.RELATIONSHIP_MANAGER:
        # An RM works only with their CSPs (/csps/mine) - they have no access to SBI officials.
        filters.append(false())

    total = db.scalar(select(func.count()).select_from(Official).where(*filters)) or 0
    rows = db.scalars(
        select(Official).where(*filters).order_by(_SORTABLE[sort]).limit(limit).offset(offset)
    ).all()
    return OfficialListResponse(
        items=[OfficialSummary.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=OfficialDetail, status_code=status.HTTP_201_CREATED)
def create_official(
    payload: OfficialCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    if payload.organization_unit_id is not None:
        if db.get(OrganizationUnit, payload.organization_unit_id) is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Organisation unit not found"
            )
        if actor.role is Role.DC and not can_access_unit(db, actor.id, payload.organization_unit_id):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Outside your assigned territory"
            )
    elif actor.role is Role.DC:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "organization_unit_id is required"
        )

    official = Official(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        designation=payload.designation,
        department=payload.department,
        level=payload.level,
        location=payload.location,
        organization_unit_id=payload.organization_unit_id,
        status=OfficialStatus.ACTIVE,
    )
    db.add(official)
    db.flush()

    # Manual entry: record "Manual entry" provenance for every field the creator
    # filled in. An admin vouches for what they type, so those fields are marked
    # verified straight away; a relationship manager's entries wait for review.
    verified = actor.role is Role.ADMIN
    now = datetime.now(timezone.utc)
    for field in PROVENANCED_FIELDS:
        if getattr(official, field) in (None, ""):
            continue
        db.add(
            OfficialFieldProvenance(
                official_id=official.id,
                field=field,
                source="Manual entry",
                confidence=100,
                verification_status=(
                    FieldVerification.VERIFIED if verified else FieldVerification.UNVERIFIED
                ),
                verified_by=actor.id if verified else None,
                verified_at=now if verified else None,
            )
        )
    db.flush()
    db.refresh(official)
    recompute_verification(official)
    audit.record(
        db,
        action="official.create",
        entity_type="official",
        entity_id=official.id,
        actor_id=actor.id,
        after={
            "name": official.name,
            "level": official.level,
            "fields_verified": verified,
        },
    )
    db.commit()
    db.refresh(official)
    return _detail(official)


@router.get("/{official_id}", response_model=OfficialDetail)
def get_official(
    official_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    return _detail(_scoped_official(db, official_id, actor))


@router.patch("/{official_id}", response_model=OfficialDetail)
def update_official(
    official_id: int,
    payload: OfficialUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    official = _scoped_official(db, official_id, actor)

    data = payload.model_dump(exclude_unset=True)
    if data.get("organization_unit_id") is not None:
        if db.get(OrganizationUnit, data["organization_unit_id"]) is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Organisation unit not found"
            )
        if actor.role is Role.DC and not can_access_unit(db, actor.id, data["organization_unit_id"]):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Outside your assigned territory")

    provenance = {p.field: p for p in official.field_provenance}
    before = {k: getattr(official, k) for k in data}

    for key, value in data.items():
        setattr(official, key, value)
        # Editing a provenanced field directly invalidates its verification.
        if key in PROVENANCED_FIELDS and key in provenance:
            provenance[key].verification_status = FieldVerification.UNVERIFIED
            provenance[key].verified_by = None
            provenance[key].verified_at = None

    recompute_verification(official)
    audit.record(
        db,
        action="official.update",
        entity_type="official",
        entity_id=official.id,
        actor_id=actor.id,
        before={k: (v.value if hasattr(v, "value") else v) for k, v in before.items()},
        after={k: (getattr(official, k).value if hasattr(getattr(official, k), "value") else getattr(official, k)) for k in data},
    )
    db.commit()
    db.refresh(official)
    return _detail(official)


@router.put("/{official_id}/fields/{field}", response_model=OfficialDetail)
def set_field(
    official_id: int,
    field: str,
    payload: SetFieldRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    if field not in PROVENANCED_FIELDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Field is not provenanced")

    official = _scoped_official(db, official_id, actor)

    if field == "organization_unit_id":
        value: object = int(payload.value) if payload.value not in (None, "") else None
        if value is not None and db.get(OrganizationUnit, value) is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Organisation unit not found"
            )
        if value is not None and actor.role is Role.DC and not can_access_unit(db, actor.id, value):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Outside your assigned territory")
    else:
        value = str(payload.value) if payload.value not in (None, "") else None

    setattr(official, field, value)

    row = db.scalar(
        select(OfficialFieldProvenance).where(
            OfficialFieldProvenance.official_id == official_id,
            OfficialFieldProvenance.field == field,
        )
    )
    if row is None:
        row = OfficialFieldProvenance(official_id=official_id, field=field)
        db.add(row)
    row.source = payload.source
    row.confidence = payload.confidence
    row.note = payload.note
    # Any value/source change starts unverified again.
    row.verification_status = FieldVerification.UNVERIFIED
    row.verified_by = None
    row.verified_at = None

    db.flush()
    db.refresh(official)
    recompute_verification(official)
    audit.record(
        db,
        action="official_field.set",
        entity_type="official_field",
        entity_id=f"{official_id}:{field}",
        actor_id=actor.id,
        after={"value": value, "source": payload.source, "confidence": payload.confidence},
    )
    db.commit()
    db.refresh(official)
    return _detail(official)


@router.post("/{official_id}/fields/{field}/verify", response_model=OfficialDetail)
def verify_field(
    official_id: int,
    field: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(Role.ADMIN)),
):
    official = db.get(Official, official_id)
    if official is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Official not found")

    row = db.scalar(
        select(OfficialFieldProvenance).where(
            OfficialFieldProvenance.official_id == official_id,
            OfficialFieldProvenance.field == field,
        )
    )
    if row is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Set the field with a source before verifying it",
        )

    row.verification_status = FieldVerification.VERIFIED
    row.verified_by = actor.id
    row.verified_at = datetime.now(timezone.utc)

    db.flush()
    db.refresh(official)
    recompute_verification(official)
    audit.record(
        db,
        action="official_field.verify",
        entity_type="official_field",
        entity_id=f"{official_id}:{field}",
        actor_id=actor.id,
        after={"verification_status": "verified"},
    )
    db.commit()
    db.refresh(official)
    return _detail(official)


@router.get("/{official_id}/timeline", response_model=list[TimelineEntry])
def official_timeline(
    official_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    _scoped_official(db, official_id, actor)

    rows = db.scalars(
        select(AuditLog)
        .where(
            or_(
                (AuditLog.entity_type == "official")
                & (AuditLog.entity_id == str(official_id)),
                (AuditLog.entity_type == "official_field")
                & (AuditLog.entity_id.like(f"{official_id}:%")),
            )
        )
        .order_by(AuditLog.at.desc(), AuditLog.id.desc())
        .limit(limit)
    ).all()
    actor_ids = {r.actor_id for r in rows if r.actor_id is not None}
    actor_names = {
        u.id: u.name
        for u in db.scalars(select(User).where(User.id.in_(actor_ids))).all()
    }
    return [
        TimelineEntry(
            action=r.action,
            entity_type=r.entity_type,
            at=r.at,
            actor_id=r.actor_id,
            actor_name=actor_names.get(r.actor_id) if r.actor_id is not None else None,
            before=r.before,
            after=r.after,
        )
        for r in rows
    ]


# --- dated facts (birthday / joined / promoted) --------------------------


@router.get("/{official_id}/dates", response_model=list[OfficialDateOut])
def list_dates(
    official_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    _scoped_official(db, official_id, actor)
    rows = db.scalars(
        select(OfficialDate)
        .where(OfficialDate.official_id == official_id)
        .order_by(OfficialDate.kind, OfficialDate.value.desc())
    ).all()
    return [OfficialDateOut.model_validate(r) for r in rows]


@router.put("/{official_id}/dates/{kind}", response_model=OfficialDateOut)
def set_date(
    official_id: int,
    kind: DateKind,
    payload: DateSet,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    _scoped_official(db, official_id, actor)

    row = None
    if kind is not DateKind.PROMOTED:
        # one birthday / joining date per official -> replace in place
        row = db.scalar(
            select(OfficialDate).where(
                OfficialDate.official_id == official_id, OfficialDate.kind == kind
            )
        )
    if row is None:
        row = OfficialDate(official_id=official_id, kind=kind)
        db.add(row)
    row.value = payload.value
    row.source = payload.source
    row.confidence = payload.confidence
    row.note = payload.note
    row.verification_status = FieldVerification.UNVERIFIED
    row.verified_by = None
    row.verified_at = None
    db.flush()
    audit.record(
        db,
        action="official_date.set",
        entity_type="official_date",
        entity_id=f"{official_id}:{kind.value}",
        actor_id=actor.id,
        after={"value": payload.value.isoformat(), "source": payload.source},
    )
    db.commit()
    db.refresh(row)
    return OfficialDateOut.model_validate(row)


@router.post("/{official_id}/dates/{date_id}/verify", response_model=OfficialDateOut)
def verify_date(
    official_id: int,
    date_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(Role.ADMIN)),
):
    row = db.get(OfficialDate, date_id)
    if row is None or row.official_id != official_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Date not found")
    row.verification_status = FieldVerification.VERIFIED
    row.verified_by = actor.id
    row.verified_at = datetime.now(timezone.utc)
    db.flush()
    audit.record(
        db,
        action="official_date.verify",
        entity_type="official_date",
        entity_id=f"{official_id}:{row.kind.value}",
        actor_id=actor.id,
    )
    db.commit()
    db.refresh(row)
    return OfficialDateOut.model_validate(row)


@router.delete("/{official_id}/dates/{date_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_date(
    official_id: int,
    date_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    _scoped_official(db, official_id, actor)
    row = db.get(OfficialDate, date_id)
    if row is None or row.official_id != official_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Date not found")
    db.delete(row)
    audit.record(
        db,
        action="official_date.delete",
        entity_type="official_date",
        entity_id=f"{official_id}:{row.kind.value}",
        actor_id=actor.id,
    )
    db.commit()


# ---------------------------------------------------------------------------------------------
# Relationship intelligence for an SBI official (the DC-facing pre-call / pre-meeting briefing).
# Every route goes through _scoped_official: a DC reaches only officials in their own territory, an
# RM reaches none (404), and a guessed id reveals nothing. Reading is open to ADMIN / viewer / DC;
# changing a commitment or giving feedback is ADMIN / DC only.
# ---------------------------------------------------------------------------------------------


def _require_writer(actor: User) -> None:
    if actor.role not in (Role.ADMIN, Role.DC):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed to change this")


def _scoped_official_commitment(db: Session, commitment_id: int, actor: User) -> Commitment:
    """A commitment reachable through the OFFICIAL routes: it must belong to an official the actor may
    act on. A CSP's commitment (no official_id) is never reachable here."""
    c = db.get(Commitment, commitment_id)
    if c is None or c.official_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Commitment not found")
    _scoped_official(db, c.official_id, actor)
    return c


@router.get("/{official_id}/intelligence")
def official_intelligence(
    official_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)
):
    """Interaction history, relationship memory, who committed what, pending follow-ups and suggested
    discussion points - built from the existing CRM records, with the viewer's own feedback applied."""
    official = _scoped_official(db, official_id, actor)
    return official_intel.build_for_official(db, official, actor)


@router.post("/commitments/{commitment_id}/status")
def set_official_commitment_status(
    commitment_id: int, payload: CommitmentStatusUpdate,
    db: Session = Depends(get_db), actor: User = Depends(get_current_user),
):
    c = _scoped_official_commitment(db, commitment_id, actor)
    _require_writer(actor)
    try:
        target = CommitmentStatus(payload.status)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid status")
    if target == CommitmentStatus.PROPOSED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid status")
    try:
        commitments_svc.set_status(db, c, target, actor, outcome=payload.outcome)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return commitments_svc.commitment_dict(db, c)


@router.post("/commitments/{commitment_id}/duplicate")
def review_official_commitment_duplicate(
    commitment_id: int, payload: DuplicateDecision,
    db: Session = Depends(get_db), actor: User = Depends(get_current_user),
):
    c = _scoped_official_commitment(db, commitment_id, actor)
    _require_writer(actor)
    try:
        commitments_svc.review_duplicate(db, c, payload.decision, actor)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return commitments_svc.commitment_dict(db, c)


@router.get("/commitments/{commitment_id}/history")
def official_commitment_history(
    commitment_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user),
):
    c = _scoped_official_commitment(db, commitment_id, actor)
    return {"commitment_id": c.id, "events": commitments_svc.history(db, c)}


@router.post("/{official_id}/feedback")
def official_feedback(
    official_id: int, payload: FeedbackIn,
    db: Session = Depends(get_db), actor: User = Depends(get_current_user),
):
    """Say whether a talking point was useful / a suggested follow-up relevant. Checked against what
    the server generates now, so a verdict cannot be forged for a suggestion that does not exist."""
    official = _scoped_official(db, official_id, actor)
    _require_writer(actor)
    try:
        row = feedback_svc.submit(
            db, actor, SUBJECT_OFFICIAL, official.id, payload.target_type, payload.key, payload.verdict,
            payload.note, official_intel.items_for_official(db, official),
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return {"ok": True, "verdict": row.verdict}
