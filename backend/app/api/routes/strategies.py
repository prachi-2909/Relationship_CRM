"""Strategy registry and controlled experiments - admin-only throughout.
This changes what the agent's rule parameters resolve to for specific
relationships (see agent.py::evaluate_relationship); it never bypasses the
agent's own human-approval gate, and nothing here promotes automatically.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...db import get_db
from ...models.strategy import Experiment, Strategy, StrategyVersion
from ...models.user import Role, User
from ...schemas.strategy import (
    ExperimentCreate,
    ExperimentOut,
    StrategyCreate,
    StrategyOut,
    StrategyVersionCreate,
    StrategyVersionOut,
)
from ...security.deps import require_roles
from ...services import strategy as strategy_svc

router = APIRouter(prefix="/strategies", tags=["strategies"])

_ADMIN = require_roles(Role.ADMIN)


def _load_strategy(db: Session, strategy_pk: int) -> Strategy:
    strategy = db.get(Strategy, strategy_pk)
    if strategy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Strategy not found")
    return strategy


def _load_version(db: Session, version_id: int) -> StrategyVersion:
    version = db.get(StrategyVersion, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Strategy version not found")
    return version


def _load_experiment(db: Session, experiment_id: int) -> Experiment:
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Experiment not found")
    return experiment


@router.get("", response_model=list[StrategyOut])
def list_strategies(db: Session = Depends(get_db), _: User = Depends(_ADMIN)):
    return [StrategyOut.of(s) for s in db.query(Strategy).all()]


@router.get("/experiments", response_model=list[ExperimentOut])
def list_experiments(db: Session = Depends(get_db), _: User = Depends(_ADMIN)):
    return [ExperimentOut.of(e) for e in db.query(Experiment).all()]


@router.post("", response_model=StrategyOut, status_code=status.HTTP_201_CREATED)
def create_strategy(payload: StrategyCreate, db: Session = Depends(get_db), actor: User = Depends(_ADMIN)):
    strategy = strategy_svc.create_strategy(
        db, strategy_id=payload.strategy_id, name=payload.name, category=payload.category, actor=actor
    )
    db.commit()
    db.refresh(strategy)
    return StrategyOut.of(strategy)


@router.post("/{strategy_pk}/versions", response_model=StrategyVersionOut, status_code=status.HTTP_201_CREATED)
def create_version(
    strategy_pk: int, payload: StrategyVersionCreate, db: Session = Depends(get_db), actor: User = Depends(_ADMIN)
):
    strategy = _load_strategy(db, strategy_pk)
    version = strategy_svc.create_version(db, strategy=strategy, config=payload.config, actor=actor)
    db.commit()
    db.refresh(version)
    return StrategyVersionOut.of(version)


@router.post("/{strategy_pk}/versions/{version_id}/experiments", response_model=ExperimentOut, status_code=status.HTTP_201_CREATED)
def create_experiment(
    strategy_pk: int,
    version_id: int,
    payload: ExperimentCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(_ADMIN),
):
    strategy = _load_strategy(db, strategy_pk)
    control = _load_version(db, payload.control_version_id)
    treatment = _load_version(db, payload.treatment_version_id)
    if control.strategy_id != strategy.id or treatment.strategy_id != strategy.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Both versions must belong to this strategy")
    experiment = strategy_svc.create_experiment(
        db, strategy=strategy, control_version=control, treatment_version=treatment,
        relationship_ids=payload.relationship_ids, actor=actor, minimum_sample_size=payload.minimum_sample_size,
    )
    db.commit()
    db.refresh(experiment)
    return ExperimentOut.of(experiment)


@router.post("/experiments/{experiment_id}/complete", response_model=ExperimentOut)
def complete_experiment(experiment_id: int, db: Session = Depends(get_db), actor: User = Depends(_ADMIN)):
    experiment = _load_experiment(db, experiment_id)
    strategy_svc.complete_experiment(db, experiment, actor)
    db.commit()
    db.refresh(experiment)
    return ExperimentOut.of(experiment)


@router.post("/versions/{version_id}/promote", response_model=StrategyVersionOut)
def promote_version(version_id: int, db: Session = Depends(get_db), actor: User = Depends(_ADMIN)):
    version = _load_version(db, version_id)
    try:
        strategy_svc.promote(db, version, actor)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    db.commit()
    db.refresh(version)
    return StrategyVersionOut.of(version)


@router.post("/versions/{version_id}/reject", response_model=StrategyVersionOut)
def reject_version(version_id: int, db: Session = Depends(get_db), actor: User = Depends(_ADMIN)):
    version = _load_version(db, version_id)
    strategy_svc.reject_version(db, version, actor)
    db.commit()
    db.refresh(version)
    return StrategyVersionOut.of(version)
