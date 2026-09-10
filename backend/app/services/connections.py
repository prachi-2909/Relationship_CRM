"""The stakeholder graph — edges between officials.

Manual assertions land as ``confirmed``. System guesses (two officials named in
the same interaction) land as ``suggested`` and wait for a human. Reads for the
Relationship Brief only ever surface ``confirmed`` edges.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models.connection import (
    DIRECTED_TYPES,
    Connection,
    ConnectionStatus,
    ConnectionType,
)
from ..models.interaction import Interaction
from ..models.official import Official

_HONORIFIC = re.compile(
    r"^(mr|mrs|ms|shri|smt|dr|sri|sir|madam)\.?\s+", re.IGNORECASE
)
_NON_NAME = re.compile(r"[^a-z\s]")


# --------------------------------------------------------------------------
# storage helpers
# --------------------------------------------------------------------------
def _canonical(
    from_id: int, to_id: int, type_: ConnectionType
) -> tuple[int, int]:
    """Order the pair. Directed types keep the caller's order; ``works_with``
    is stored low-id -> high-id so A-B and B-A are the same row."""
    if type_ in DIRECTED_TYPES:
        return from_id, to_id
    return (from_id, to_id) if from_id < to_id else (to_id, from_id)


def get_pair(
    db: Session, from_id: int, to_id: int, type_: ConnectionType
) -> Connection | None:
    a, b = _canonical(from_id, to_id, type_)
    return db.scalar(
        select(Connection)
        .where(Connection.from_official_id == a)
        .where(Connection.to_official_id == b)
        .where(Connection.type == type_)
    )


def upsert(
    db: Session,
    *,
    from_id: int,
    to_id: int,
    type_: ConnectionType,
    source: str,
    status: ConnectionStatus,
    actor_id: int | None = None,
    source_interaction_id: int | None = None,
    confidence: int | None = None,
    note: str | None = None,
) -> tuple[Connection, bool]:
    """Create the edge, or return the existing one. Returns (connection, created).

    A ``CONFIRMED`` request always wins — it lifts a prior ``SUGGESTED`` *or*
    ``DISMISSED`` row (an RM re-asserting a fact overrides an earlier dismissal).
    A ``SUGGESTED`` request never changes an existing row, so the system won't
    re-propose something a human already rejected.
    """
    a, b = _canonical(from_id, to_id, type_)
    existing = get_pair(db, a, b, type_)
    if existing is not None:
        if (
            status is ConnectionStatus.CONFIRMED
            and existing.status is not ConnectionStatus.CONFIRMED
        ):
            existing.status = ConnectionStatus.CONFIRMED
            existing.source = source
            existing.decided_by = actor_id
            existing.decided_at = datetime.now(timezone.utc)
            if note and not existing.note:
                existing.note = note
        return existing, False

    conn = Connection(
        from_official_id=a,
        to_official_id=b,
        type=type_,
        status=status,
        source=source,
        source_interaction_id=source_interaction_id,
        confidence=confidence,
        note=note,
        created_by=actor_id,
    )
    if status is ConnectionStatus.CONFIRMED:
        conn.decided_by = actor_id
        conn.decided_at = datetime.now(timezone.utc)
    db.add(conn)
    db.flush()
    return conn, True


def set_status(
    db: Session, conn: Connection, status: ConnectionStatus, *, actor_id: int
) -> Connection:
    conn.status = status
    conn.decided_by = actor_id
    conn.decided_at = datetime.now(timezone.utc)
    return conn


# --------------------------------------------------------------------------
# reads
# --------------------------------------------------------------------------
def _label(type_: ConnectionType, direction: str, other_name: str) -> str:
    if type_ is ConnectionType.WORKS_WITH:
        return f"works with {other_name}"
    if type_ is ConnectionType.REPORTS_TO:
        return (
            f"reports to {other_name}"
            if direction == "outgoing"
            else f"{other_name} reports to them"
        )
    # introduced_by
    return (
        f"introduced by {other_name}"
        if direction == "outgoing"
        else f"introduced us to {other_name}"
    )


def neighbors(
    db: Session, official_id: int, *, statuses: tuple[ConnectionStatus, ...] = ()
) -> list[dict]:
    """Every edge touching ``official_id`` as a neighbour view. Defaults to
    confirmed edges only; pass ``statuses`` to widen."""
    statuses = statuses or (ConnectionStatus.CONFIRMED,)
    rows = db.scalars(
        select(Connection)
        .where(
            or_(
                Connection.from_official_id == official_id,
                Connection.to_official_id == official_id,
            )
        )
        .where(Connection.status.in_(statuses))
        .order_by(Connection.type, Connection.id)
    ).all()

    out: list[dict] = []
    for c in rows:
        if c.from_official_id == official_id:
            other = c.to_official
            direction = "mutual" if c.type is ConnectionType.WORKS_WITH else "outgoing"
        else:
            other = c.from_official
            direction = "mutual" if c.type is ConnectionType.WORKS_WITH else "incoming"
        out.append(
            {
                "connection_id": c.id,
                "official_id": other.id,
                "name": other.name,
                "level": other.level,
                "type": c.type.value,
                "direction": direction,
                "status": c.status.value,
                "label": _label(c.type, direction, other.name),
                "note": c.note,
                "source": c.source,
            }
        )
    return out


# --------------------------------------------------------------------------
# name resolution + suggestions from interactions
# --------------------------------------------------------------------------
def _norm(name: str) -> str:
    name = _HONORIFIC.sub("", name.strip())
    return _NON_NAME.sub("", name.lower()).strip()


def resolve_name(db: Session, raw_name: str) -> tuple[Official | None, int]:
    """Best-effort match of a free-text name to an official.
    Returns (official_or_None, confidence 0-100)."""
    q = _norm(raw_name)
    if len(q) < 3:
        return None, 0
    q_tokens = set(q.split())

    officials = db.scalars(select(Official)).all()
    exact = [o for o in officials if _norm(o.name) == q]
    if len(exact) == 1:
        return exact[0], 95
    if len(exact) > 1:
        return None, 0  # ambiguous

    scored: list[tuple[int, Official]] = []
    for o in officials:
        o_tokens = set(_norm(o.name).split())
        if not o_tokens:
            continue
        if q_tokens <= o_tokens or o_tokens <= q_tokens:
            overlap = len(q_tokens & o_tokens)
            scored.append((60 + 10 * overlap, o))
    if len(scored) == 1:
        return scored[0][1], min(scored[0][0], 90)
    return None, 0


def suggest_from_interaction(db: Session, interaction: Interaction) -> int:
    """From the names the extractor pulled, propose ``works_with`` edges between
    every pair of resolvable officials (including this interaction's own
    official). Returns the number of new suggestions created."""
    structured = interaction.structured or {}
    names = list(structured.get("people") or [])
    if not names:  # fall back to raw model output if the effective field is bare
        names = list((interaction.ai_structured or {}).get("people") or [])

    resolved: dict[int, Official] = {}
    if interaction.official_id:
        owner = db.get(Official, interaction.official_id)
        if owner is not None:
            resolved[owner.id] = owner
    for nm in names:
        off, conf = resolve_name(db, nm)
        if off is not None and conf >= 70:
            resolved.setdefault(off.id, off)

    ids = sorted(resolved)
    created = 0
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            _, was_new = upsert(
                db,
                from_id=a,
                to_id=b,
                type_=ConnectionType.WORKS_WITH,
                source=f"Co-mentioned in interaction #{interaction.id}",
                status=ConnectionStatus.SUGGESTED,
                source_interaction_id=interaction.id,
                confidence=55,
            )
            created += int(was_new)
    return created
