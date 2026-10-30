"""The dashboards, from one source: the admin's command view of everything, and each RM's / DC's own view.

One function, `build`, answers for whoever is asking and returns only what their role may see:
- An admin (or viewer) sees the whole CRM: every RM and DC side by side, the SBI officials, the CSPs, the calls, and
  the work waiting. They can narrow it to one RM or one DC with `rm_id` / `dc_id`.
- A Relationship Manager is always narrowed to their own CSPs and calls: whatever `rm_id` they send is ignored.
- A District Coordinator is always narrowed to their own SBI officials and calls.

Everything is counted from the CRM's own records (no AI, no network), so it is quick and repeatable. A call "counts"
once it was reported back and not cancelled; a call that was registered but never placed is not a call.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from ..models.call_intelligence import CallSession, CallSessionStatus
from ..models.commitment import Commitment, CommitmentSourceKind, CommitmentStatus
from ..models.csp import Csp, CspStatus
from ..models.official import Official, OfficialStatus
from ..models.relationship import Relationship, RiskLevel
from ..models.task import Task, TaskStatus
from ..models.user import Role, User, UserStatus
from .scoring import band

NOT_A_CALL = (CallSessionStatus.CANCELLED, CallSessionStatus.INITIATED)
NEEDS_REVIEW = (CallSessionStatus.REVIEW_REQUIRED, CallSessionStatus.INITIATED)
STALE_DAYS = 30
LIST_LIMIT = 12


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    dt = _aware(dt)
    return dt.isoformat() if dt else None


def _days_since(dt: datetime | None, now: datetime) -> int | None:
    dt = _aware(dt)
    return None if dt is None else max(0, (now - dt).days)


def _scope(user: User, rm_id: int | None, dc_id: int | None) -> tuple[int | None, int | None, bool]:
    """(rm filter, dc filter, sees everyone) for this user."""
    if user.role == Role.RELATIONSHIP_MANAGER:
        return user.id, None, False
    if user.role == Role.DC:
        return None, user.id, False
    return rm_id, dc_id, True


def _people(db: Session, role: Role) -> list[User]:
    return list(db.scalars(
        select(User).where(User.role == role, User.status == UserStatus.ACTIVE).order_by(User.name)
    ).all())


def _connected_calls(since: datetime | None = None, **extra):
    conds = [CallSession.processing_status.not_in(NOT_A_CALL)]
    if since is not None:
        conds.append(CallSession.started_at >= since)
    return conds


def _calls_by_user(db: Session, since: datetime) -> dict[int, int]:
    rows = db.execute(
        select(CallSession.dc_user_id, func.count())
        .where(*_connected_calls(since)).group_by(CallSession.dc_user_id)
    ).all()
    return {r[0]: r[1] for r in rows}


def _connect_rate(db: Session, since: datetime) -> dict[int, float | None]:
    """Of the calls reported back in the window, the share that connected, per user."""
    rows = db.execute(
        select(
            CallSession.dc_user_id,
            func.sum(case((CallSession.processing_status.in_(NOT_A_CALL), 0), else_=1)),
            func.count(),
        )
        .where(CallSession.started_at >= since,
               or_(CallSession.ended_at.is_not(None), CallSession.processing_status.not_in(NOT_A_CALL)))
        .group_by(CallSession.dc_user_id)
    ).all()
    return {r[0]: (round(100.0 * (r[1] or 0) / r[2]) if r[2] else None) for r in rows}


def _last_call(db: Session) -> dict[int, datetime]:
    rows = db.execute(
        select(CallSession.dc_user_id, func.max(CallSession.started_at))
        .where(*_connected_calls()).group_by(CallSession.dc_user_id)
    ).all()
    return {r[0]: r[1] for r in rows}


def _csps_uncalled(db: Session, cutoff: datetime, rm_id: int | None) -> list[Csp]:
    """Active CSPs with no connected call since the cutoff, never-called first."""
    called = select(CallSession.csp_id).where(
        CallSession.csp_id.is_not(None), *_connected_calls(cutoff)
    )
    q = select(Csp).where(Csp.status == CspStatus.ACTIVE, Csp.id.not_in(called))
    if rm_id is not None:
        q = q.where(Csp.rm_user_id == rm_id)
    return list(db.scalars(q).all())


def _rm_rows(db: Session, now: datetime, only: int | None) -> list[dict]:
    rms = [u for u in _people(db, Role.RELATIONSHIP_MANAGER) if only is None or u.id == only]
    if not rms:
        return []
    today = now.date()
    csp_counts = dict(db.execute(
        select(Csp.rm_user_id, func.count()).where(Csp.status == CspStatus.ACTIVE).group_by(Csp.rm_user_id)
    ).all())
    c7, c30 = _calls_by_user(db, now - timedelta(days=7)), _calls_by_user(db, now - timedelta(days=30))
    rate, last = _connect_rate(db, now - timedelta(days=30)), _last_call(db)
    uncalled: dict[int, int] = {}
    for c in _csps_uncalled(db, now - timedelta(days=STALE_DAYS), None):
        uncalled[c.rm_user_id] = uncalled.get(c.rm_user_id, 0) + 1
    open_c = dict(db.execute(
        select(Commitment.owner_user_id, func.count())
        .where(Commitment.source_kind == CommitmentSourceKind.RM_CSP, Commitment.status == CommitmentStatus.OPEN,
               Commitment.merged_into_id.is_(None)).group_by(Commitment.owner_user_id)
    ).all())
    late_c = dict(db.execute(
        select(Commitment.owner_user_id, func.count())
        .where(Commitment.source_kind == CommitmentSourceKind.RM_CSP, Commitment.status == CommitmentStatus.OPEN,
               Commitment.merged_into_id.is_(None), Commitment.due_date.is_not(None), Commitment.due_date < today)
        .group_by(Commitment.owner_user_id)
    ).all())
    return [
        {
            "id": u.id, "name": u.name,
            "csps": csp_counts.get(u.id, 0),
            "calls_7d": c7.get(u.id, 0), "calls_30d": c30.get(u.id, 0),
            "connect_rate_30d": rate.get(u.id),
            "last_call_at": _iso(last.get(u.id)), "days_since_last_call": _days_since(last.get(u.id), now),
            "csps_not_called_30d": uncalled.get(u.id, 0),
            "commitments_open": open_c.get(u.id, 0), "commitments_overdue": late_c.get(u.id, 0),
        }
        for u in rms
    ]


def _dc_rows(db: Session, now: datetime, only: int | None) -> list[dict]:
    dcs = [u for u in _people(db, Role.DC) if only is None or u.id == only]
    if not dcs:
        return []
    cutoff30 = now - timedelta(days=30)
    rel = {
        r[0]: r for r in db.execute(
            select(
                Relationship.owner_id, func.count(), func.avg(Relationship.score),
                func.sum(case((Relationship.risk_level == RiskLevel.HIGH, 1), else_=0)),
                func.sum(case((or_(Relationship.last_interaction_at.is_(None),
                                   Relationship.last_interaction_at < cutoff30), 1), else_=0)),
            ).group_by(Relationship.owner_id)
        ).all()
    }
    c30, last = _calls_by_user(db, cutoff30), _last_call(db)
    late_tasks = dict(db.execute(
        select(Task.assigned_to, func.count())
        .where(Task.status == TaskStatus.OPEN, Task.due_at.is_not(None), Task.due_at < now)
        .group_by(Task.assigned_to)
    ).all())
    return [
        {
            "id": u.id, "name": u.name,
            "officials": (rel.get(u.id) or (None, 0))[1],
            "avg_relationship": round(rel[u.id][2]) if u.id in rel and rel[u.id][2] is not None else None,
            "at_risk": int((rel.get(u.id) or (0, 0, 0, 0))[3] or 0),
            "not_contacted_30d": int((rel.get(u.id) or (0, 0, 0, 0, 0))[4] or 0),
            "calls_30d": c30.get(u.id, 0),
            "last_call_at": _iso(last.get(u.id)), "days_since_last_call": _days_since(last.get(u.id), now),
            "followups_overdue": late_tasks.get(u.id, 0),
        }
        for u in dcs
    ]


def _officials_block(db: Session, now: datetime, dc_id: int | None) -> dict:
    q_off = select(func.count()).select_from(Official).where(Official.status == OfficialStatus.ACTIVE)
    total = db.scalar(q_off) or 0
    rel_q = select(Relationship)
    if dc_id is not None:
        rel_q = rel_q.where(Relationship.owner_id == dc_id)
    rels = list(db.scalars(rel_q).all())
    owner = {u.id: u.name for u in db.scalars(select(User)).all()}
    names = dict(db.execute(select(Official.id, Official.name)).all())
    levels = dict(db.execute(select(Official.id, Official.level)).all())

    bands: dict[str, int] = {"Strong": 0, "Healthy": 0, "Attention required": 0, "At risk": 0}
    for r in rels:
        bands[band(r.score)[0]] += 1
    by_level: dict[str, int] = {}
    for r in rels:
        k = levels.get(r.official_id) or "Unspecified"
        by_level[k] = by_level.get(k, 0) + 1
    worst = sorted(rels, key=lambda r: r.score)[:LIST_LIMIT]
    return {
        "total": total,
        "with_relationship": len(rels),
        "without_relationship": max(0, total - len(rels)) if dc_id is None else None,
        "avg_score": round(sum(r.score for r in rels) / len(rels)) if rels else None,
        "by_band": [{"name": k, "value": v} for k, v in bands.items()],
        "by_level": [{"name": k, "value": v} for k, v in sorted(by_level.items(), key=lambda kv: -kv[1])[:8]],
        "needs_attention": [
            {
                "official_id": r.official_id, "relationship_id": r.id, "name": names.get(r.official_id),
                "level": levels.get(r.official_id), "score": r.score, "band": band(r.score)[0],
                "dc": owner.get(r.owner_id), "days_since_contact": _days_since(r.last_interaction_at, now),
            }
            for r in worst
        ],
    }


def _csp_block(db: Session, now: datetime, rm_id: int | None) -> dict:
    base = [Csp.status == CspStatus.ACTIVE] + ([Csp.rm_user_id == rm_id] if rm_id is not None else [])
    active = db.scalar(select(func.count()).select_from(Csp).where(*base)) or 0
    inactive_q = select(func.count()).select_from(Csp).where(Csp.status != CspStatus.ACTIVE)
    if rm_id is not None:
        inactive_q = inactive_q.where(Csp.rm_user_id == rm_id)
    uncalled = _csps_uncalled(db, now - timedelta(days=STALE_DAYS), rm_id)
    last = dict(db.execute(
        select(CallSession.csp_id, func.max(CallSession.started_at))
        .where(CallSession.csp_id.is_not(None), *_connected_calls()).group_by(CallSession.csp_id)
    ).all())
    late = dict(db.execute(
        select(Commitment.csp_id, func.count())
        .where(Commitment.csp_id.is_not(None), Commitment.status == CommitmentStatus.OPEN,
               Commitment.merged_into_id.is_(None), Commitment.due_date.is_not(None),
               Commitment.due_date < now.date())
        .group_by(Commitment.csp_id)
    ).all())
    ordered = sorted(uncalled, key=lambda c: (last.get(c.id) is not None, _aware(last.get(c.id)) or now, c.name))
    return {
        "active": active,
        "inactive": db.scalar(inactive_q) or 0,
        "not_called_30d": len(uncalled),
        "never_called": sum(1 for c in uncalled if last.get(c.id) is None),
        "to_call": [
            {
                "id": c.id, "csp_id": c.csp_id, "name": c.name, "rm_name": c.rm_name, "branch": c.branch_name,
                "mobile": c.mobile,
                "last_call_at": _iso(last.get(c.id)), "days_since_last_call": _days_since(last.get(c.id), now),
                "overdue_commitments": late.get(c.id, 0),
            }
            for c in ordered[:LIST_LIMIT]
        ],
    }


def _calls_block(db: Session, now: datetime, rm_id: int | None, dc_id: int | None) -> dict:
    who = [CallSession.dc_user_id == (rm_id if rm_id is not None else dc_id)] if (rm_id or dc_id) else []
    start = now.date() - timedelta(days=13)
    rows = db.execute(
        select(func.date(CallSession.started_at), User.role, func.count())
        .join(User, User.id == CallSession.dc_user_id)
        .where(func.date(CallSession.started_at) >= start.isoformat(), *_connected_calls(), *who)
        .group_by(func.date(CallSession.started_at), User.role)
    ).all()
    grid: dict[tuple[str, str], int] = {(str(r[0]), r[1].value): r[2] for r in rows}
    timeline = []
    for i in range(14):
        d = (start + timedelta(days=i)).isoformat()
        timeline.append({"date": d, "rm": grid.get((d, Role.RELATIONSHIP_MANAGER.value), 0),
                         "dc": grid.get((d, Role.DC.value), 0)})
    count = lambda *c: db.scalar(select(func.count()).select_from(CallSession).where(*c, *who)) or 0  # noqa: E731
    recent = db.execute(
        select(CallSession, User.name, User.role).join(User, User.id == CallSession.dc_user_id)
        .where(*_connected_calls(), *who).order_by(CallSession.started_at.desc()).limit(LIST_LIMIT)
    ).all()
    csp_names = dict(db.execute(select(Csp.id, Csp.name)).all())
    off_names = dict(db.execute(select(Official.id, Official.name)).all())
    return {
        "total": count(*_connected_calls()),
        "last_7d": count(*_connected_calls(now - timedelta(days=7))),
        "last_30d": count(*_connected_calls(now - timedelta(days=30))),
        "awaiting_review": count(CallSession.processing_status.in_(NEEDS_REVIEW)),
        "timeline": timeline,
        "recent": [
            {
                "id": c.id, "when": _iso(c.started_at), "by": name, "role": role.value,
                "with": csp_names.get(c.csp_id) if c.csp_id else off_names.get(c.official_id),
                "kind": "csp" if c.csp_id else ("official" if c.official_id else "unknown"),
                "direction": c.direction.value if c.direction else None, "seconds": c.duration_seconds,
                "status": c.processing_status.value,
            }
            for c, name, role in recent
        ],
    }


def _work_block(db: Session, now: datetime, rm_id: int | None, dc_id: int | None) -> dict:
    today = now.date()
    open_c = [Commitment.status == CommitmentStatus.OPEN, Commitment.merged_into_id.is_(None)]
    if rm_id is not None:
        open_c.append(Commitment.owner_user_id == rm_id)
    if dc_id is not None:
        open_c.append(Commitment.owner_user_id == dc_id)

    def n(kind: CommitmentSourceKind, overdue: bool) -> int:
        conds = [*open_c, Commitment.source_kind == kind]
        if overdue:
            conds += [Commitment.due_date.is_not(None), Commitment.due_date < today]
        return db.scalar(select(func.count()).select_from(Commitment).where(*conds)) or 0

    task_q = [Task.status == TaskStatus.OPEN, Task.due_at.is_not(None), Task.due_at < now]
    if dc_id is not None:
        task_q.append(Task.assigned_to == dc_id)
    return {
        "csp_commitments_open": n(CommitmentSourceKind.RM_CSP, False),
        "csp_commitments_overdue": n(CommitmentSourceKind.RM_CSP, True),
        "official_commitments_open": n(CommitmentSourceKind.DC_OFFICIAL, False),
        "official_commitments_overdue": n(CommitmentSourceKind.DC_OFFICIAL, True),
        "followups_overdue": db.scalar(select(func.count()).select_from(Task).where(*task_q)) or 0,
    }


def build(db: Session, user: User, *, rm_id: int | None = None, dc_id: int | None = None,
          now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    rm_f, dc_f, sees_all = _scope(user, rm_id, dc_id)
    show_csp = user.role != Role.DC
    show_officials = user.role != Role.RELATIONSHIP_MANAGER

    def pick(uid: int | None) -> dict | None:
        u = db.get(User, uid) if uid else None
        return {"id": u.id, "name": u.name} if u else None

    return {
        "scope": {
            "role": user.role.value,
            "rm": pick(rm_f), "dc": pick(dc_f),
            "can_filter": sees_all,
            "generated_at": _iso(now),
        },
        "filters": {
            "rms": [{"id": u.id, "name": u.name} for u in _people(db, Role.RELATIONSHIP_MANAGER)],
            "dcs": [{"id": u.id, "name": u.name} for u in _people(db, Role.DC)],
        } if sees_all else None,
        "csp": _csp_block(db, now, rm_f) if show_csp else None,
        "officials": _officials_block(db, now, dc_f) if show_officials else None,
        "calls": _calls_block(db, now, rm_f, dc_f),
        "work": _work_block(db, now, rm_f, dc_f),
        # Side-by-side tables are the admin's comparison view; an RM sees only their own row.
        "rms": _rm_rows(db, now, rm_f) if show_csp and (sees_all or user.role == Role.RELATIONSHIP_MANAGER) else None,
        "dcs": _dc_rows(db, now, dc_f) if show_officials and (sees_all or user.role == Role.DC) else None,
    }
