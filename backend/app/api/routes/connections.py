"""The stakeholder graph: edges between officials, manual or system-suggested."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models.connection import Connection, ConnectionStatus
from ...models.interaction import Interaction
from ...models.official import Official
from ...models.user import Role, User
from ...schemas.connection import (
    ConnectionCreate,
    ConnectionOut,
    ConnectionUpdate,
    Neighbor,
    OfficialGraph,
)
from ...security.deps import get_current_user, require_roles
from ...services import audit
from ...services import connections as svc

router = APIRouter(tags=["connections"])

_EDITORS = require_roles(Role.ADMIN, Role.RELATIONSHIP_MANAGER)


def _official_or_404(db: Session, official_id: int) -> Official:
    official = db.get(Official, official_id)
    if official is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Official not found")
    return official


@router.get("/officials/{official_id}/connections", response_model=OfficialGraph)
def official_connections(
    official_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _official_or_404(db, official_id)
    rows = svc.neighbors(
        db,
        official_id,
        statuses=(ConnectionStatus.CONFIRMED, ConnectionStatus.SUGGESTED),
    )
    return OfficialGraph(
        official_id=official_id,
        confirmed=[Neighbor(**r) for r in rows if r["status"] == "confirmed"],
        suggested=[Neighbor(**r) for r in rows if r["status"] == "suggested"],
    )


@router.post(
    "/connections",
    response_model=ConnectionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_connection(
    payload: ConnectionCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    _official_or_404(db, payload.from_official_id)
    _official_or_404(db, payload.to_official_id)

    conn, created = svc.upsert(
        db,
        from_id=payload.from_official_id,
        to_id=payload.to_official_id,
        type_=payload.type,
        source="Manual entry",
        status=ConnectionStatus.CONFIRMED,
        actor_id=actor.id,
        note=payload.note,
        confidence=100,
    )
    audit.record(
        db,
        action="connection.create" if created else "connection.confirm",
        entity_type="connection",
        entity_id=conn.id,
        actor_id=actor.id,
        after={
            "from": conn.from_official_id,
            "to": conn.to_official_id,
            "type": conn.type.value,
            "status": conn.status.value,
            "source": conn.source,
        },
    )
    db.commit()
    db.refresh(conn)
    return ConnectionOut.model_validate(conn)


@router.patch("/connections/{connection_id}", response_model=ConnectionOut)
def update_connection(
    connection_id: int,
    payload: ConnectionUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    conn = db.get(Connection, connection_id)
    if conn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found")

    before = {"status": conn.status.value, "note": conn.note}
    if payload.status is not None and payload.status is not conn.status:
        svc.set_status(db, conn, payload.status, actor_id=actor.id)
    if payload.note is not None:
        conn.note = payload.note or None

    audit.record(
        db,
        action="connection.update",
        entity_type="connection",
        entity_id=conn.id,
        actor_id=actor.id,
        before=before,
        after={"status": conn.status.value, "note": conn.note},
    )
    db.commit()
    db.refresh(conn)
    return ConnectionOut.model_validate(conn)


@router.delete(
    "/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_connection(
    connection_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    conn = db.get(Connection, connection_id)
    if conn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found")
    audit.record(
        db,
        action="connection.delete",
        entity_type="connection",
        entity_id=conn.id,
        actor_id=actor.id,
        before={
            "from": conn.from_official_id,
            "to": conn.to_official_id,
            "type": conn.type.value,
        },
    )
    db.delete(conn)
    db.commit()


@router.post(
    "/officials/{official_id}/connections/rescan", response_model=OfficialGraph
)
def rescan_connections(
    official_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    """Re-run co-mention suggestions across every interaction on this official's
    relationship. Useful for backfilling data loaded before this feature."""
    official = _official_or_404(db, official_id)
    interactions = db.scalars(
        select(Interaction).where(Interaction.official_id == official.id)
    ).all()
    made = sum(svc.suggest_from_interaction(db, obj) for obj in interactions)
    if made:
        audit.record(
            db,
            action="connection.rescan",
            entity_type="official",
            entity_id=official.id,
            actor_id=actor.id,
            after={"suggested": made},
        )
    db.commit()

    rows = svc.neighbors(
        db,
        official_id,
        statuses=(ConnectionStatus.CONFIRMED, ConnectionStatus.SUGGESTED),
    )
    return OfficialGraph(
        official_id=official_id,
        confirmed=[Neighbor(**r) for r in rows if r["status"] == "confirmed"],
        suggested=[Neighbor(**r) for r in rows if r["status"] == "suggested"],
    )
