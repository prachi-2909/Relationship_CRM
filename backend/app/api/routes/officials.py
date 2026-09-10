"""Officials: CRUD, search, per-field provenance, verification, and timeline."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
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
from ...schemas.official_date import DateSet, OfficialDateOut
from ...security.deps import get_current_user, require_roles
from ...services import audit
from ...services.officials import recompute_verification

router = APIRouter(prefix="/officials", tags=["officials"])

_EDITORS = require_roles(Role.ADMIN, Role.RELATIONSHIP_MANAGER)
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
    _: User = Depends(get_current_user),
):
    if sort not in _SORTABLE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown sort key")

    filters = [Official.status == status_filter]
    if q:
        filters.append(Official.name.ilike(f"%{q}%"))
    if unit_id is not None:
        filters.append(Official.organization_unit_id == unit_id)
    if level:
        filters.append(Official.level == level)
    if verification_status is not None:
        filters.append(Official.verification_status == verification_status)

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

    official = Official(
        name=payload.name,
        email=payload.email,
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
    _: User = Depends(get_current_user),
):
    official = db.get(Official, official_id)
    if official is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Official not found")
    return _detail(official)


@router.patch("/{official_id}", response_model=OfficialDetail)
def update_official(
    official_id: int,
    payload: OfficialUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    official = db.get(Official, official_id)
    if official is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Official not found")

    data = payload.model_dump(exclude_unset=True)
    if data.get("organization_unit_id") is not None:
        if db.get(OrganizationUnit, data["organization_unit_id"]) is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Organisation unit not found"
            )

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

    official = db.get(Official, official_id)
    if official is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Official not found")

    if field == "organization_unit_id":
        value: object = int(payload.value) if payload.value not in (None, "") else None
        if value is not None and db.get(OrganizationUnit, value) is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Organisation unit not found"
            )
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
    _: User = Depends(get_current_user),
):
    if db.get(Official, official_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Official not found")

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
    return [
        TimelineEntry(
            action=r.action,
            entity_type=r.entity_type,
            at=r.at,
            actor_id=r.actor_id,
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
    _: User = Depends(get_current_user),
):
    if db.get(Official, official_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Official not found")
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
    if db.get(Official, official_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Official not found")

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
