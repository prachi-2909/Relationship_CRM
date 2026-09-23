"""Strategy registry and controlled experiments.

An unassigned relationship's agent behavior is completely unaffected by
anything here - get_effective_config() returns None unless a relationship
is explicitly part of a RUNNING experiment or a strategy has been promoted
to active. Promotion always requires an explicit admin action gated on a
minimum sample size (see promote()); nothing here is ever automatic.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.strategy import (
    Experiment,
    ExperimentArm,
    ExperimentAssignment,
    ExperimentStatus,
    Strategy,
    StrategyStatus,
    StrategyVersion,
    StrategyVersionStatus,
)
from ..models.user import User
from . import audit, outcomes

# The one strategy this codebase currently connects to actual agent
# behavior - see agent.py::evaluate_relationship. Adding another strategy
# id doesn't require new tables, only a new agent.py read site.
FOLLOWUP_TIMING_STRATEGY_ID = "task_followup_timing"

_MIN_EXPERIMENT_SAMPLE = 20


def create_strategy(db: Session, *, strategy_id: str, name: str, category: str, actor: User) -> Strategy:
    strategy = Strategy(strategy_id=strategy_id, name=name, category=category, status=StrategyStatus.DRAFT)
    db.add(strategy)
    db.flush()
    audit.record(
        db, action="strategy.create", entity_type="strategy", entity_id=strategy.id, actor_id=actor.id,
        after={"strategy_id": strategy_id, "name": name},
    )
    return strategy


def create_version(db: Session, *, strategy: Strategy, config: dict, actor: User) -> StrategyVersion:
    last = db.scalar(
        select(StrategyVersion.version)
        .where(StrategyVersion.strategy_id == strategy.id)
        .order_by(StrategyVersion.version.desc())
    )
    version = StrategyVersion(
        strategy_id=strategy.id,
        version=(last or 0) + 1,
        config=config,
        status=StrategyVersionStatus.DRAFT,
        created_by=actor.id,
    )
    db.add(version)
    db.flush()
    audit.record(
        db, action="strategy.version.create", entity_type="strategy_version", entity_id=version.id,
        actor_id=actor.id, after={"strategy_id": strategy.id, "version": version.version, "config": config},
    )
    return version


def create_experiment(
    db: Session,
    *,
    strategy: Strategy,
    control_version: StrategyVersion,
    treatment_version: StrategyVersion,
    relationship_ids: list[int],
    actor: User,
    minimum_sample_size: int = _MIN_EXPERIMENT_SAMPLE,
) -> Experiment:
    experiment = Experiment(
        strategy_id=strategy.id,
        control_version_id=control_version.id,
        treatment_version_id=treatment_version.id,
        status=ExperimentStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
        minimum_sample_size=minimum_sample_size,
        created_by=actor.id,
    )
    db.add(experiment)
    db.flush()
    control_version.status = StrategyVersionStatus.TESTING
    treatment_version.status = StrategyVersionStatus.TESTING
    strategy.status = StrategyStatus.TESTING

    now = datetime.now(timezone.utc)
    for rel_id in relationship_ids:
        # deterministic, reproducible split - no stored seed needed
        arm = ExperimentArm.TREATMENT if hash(rel_id) % 2 == 0 else ExperimentArm.CONTROL
        db.add(
            ExperimentAssignment(
                experiment_id=experiment.id, relationship_id=rel_id, arm=arm, assigned_at=now
            )
        )
    db.flush()
    audit.record(
        db, action="strategy.experiment.create", entity_type="experiment", entity_id=experiment.id,
        actor_id=actor.id, after={"strategy_id": strategy.id, "sample_size": len(relationship_ids)},
    )
    return experiment


def complete_experiment(db: Session, experiment: Experiment, actor: User) -> Experiment:
    control_ids = [a.relationship_id for a in experiment.assignments if a.arm == ExperimentArm.CONTROL]
    treatment_ids = [a.relationship_id for a in experiment.assignments if a.arm == ExperimentArm.TREATMENT]

    control_version = db.get(StrategyVersion, experiment.control_version_id)
    treatment_version = db.get(StrategyVersion, experiment.treatment_version_id)
    control_version.evaluation_metrics = outcomes.compute_metrics(db, relationship_ids=control_ids)
    treatment_version.evaluation_metrics = outcomes.compute_metrics(db, relationship_ids=treatment_ids)

    experiment.status = ExperimentStatus.COMPLETED
    experiment.ended_at = datetime.now(timezone.utc)
    db.flush()
    audit.record(
        db, action="strategy.experiment.complete", entity_type="experiment", entity_id=experiment.id,
        actor_id=actor.id,
        after={
            "control_metrics": control_version.evaluation_metrics,
            "treatment_metrics": treatment_version.evaluation_metrics,
        },
    )
    return experiment


def promote(db: Session, version: StrategyVersion, actor: User) -> StrategyVersion:
    """Promote a tested version to active. Never automatic - always one
    explicit admin action, and always gated on a completed experiment with
    enough sample in the treatment arm."""
    if version.status != StrategyVersionStatus.TESTING:
        raise ValueError("Only a version in 'testing' status can be promoted")

    experiment = db.scalar(
        select(Experiment)
        .where(Experiment.treatment_version_id == version.id)
        .where(Experiment.status == ExperimentStatus.COMPLETED)
    )
    if experiment is None:
        raise ValueError("No completed experiment found for this version")

    treatment_count = sum(1 for a in experiment.assignments if a.arm == ExperimentArm.TREATMENT)
    if treatment_count < experiment.minimum_sample_size:
        raise ValueError(
            f"Treatment arm has {treatment_count} relationships, needs at least "
            f"{experiment.minimum_sample_size} before promotion"
        )

    strategy = db.get(Strategy, version.strategy_id)
    if strategy.current_version_id is not None:
        old_active = db.get(StrategyVersion, strategy.current_version_id)
        if old_active is not None:
            old_active.status = StrategyVersionStatus.RETIRED

    version.status = StrategyVersionStatus.ACTIVE
    version.approved_by = actor.id
    version.approved_at = datetime.now(timezone.utc)
    strategy.current_version_id = version.id
    strategy.status = StrategyStatus.ACTIVE
    db.flush()
    audit.record(
        db, action="strategy.version.promote", entity_type="strategy_version", entity_id=version.id,
        actor_id=actor.id, after={"strategy_id": strategy.id, "version": version.version},
    )
    return version


def reject_version(db: Session, version: StrategyVersion, actor: User) -> StrategyVersion:
    version.status = StrategyVersionStatus.REJECTED
    audit.record(
        db, action="strategy.version.reject", entity_type="strategy_version", entity_id=version.id,
        actor_id=actor.id,
    )
    return version


def get_effective_config(db: Session, relationship_id: int, strategy_id: str = FOLLOWUP_TIMING_STRATEGY_ID) -> dict | None:
    """The config a relationship's agent run should use for this strategy,
    or None if nothing applies - in which case the caller uses today's
    hardcoded default, unchanged.

    Resolution order: an active experiment assignment for this relationship
    wins first (so a controlled trial is never silently overridden by the
    org default), then the strategy's promoted current_version_id.
    """
    strategy = db.scalar(select(Strategy).where(Strategy.strategy_id == strategy_id))
    if strategy is None:
        return None

    assignment = db.scalar(
        select(ExperimentAssignment)
        .join(Experiment, ExperimentAssignment.experiment_id == Experiment.id)
        .where(Experiment.strategy_id == strategy.id)
        .where(Experiment.status == ExperimentStatus.RUNNING)
        .where(ExperimentAssignment.relationship_id == relationship_id)
    )
    if assignment is not None:
        experiment = db.get(Experiment, assignment.experiment_id)
        version_id = (
            experiment.treatment_version_id if assignment.arm == ExperimentArm.TREATMENT
            else experiment.control_version_id
        )
        version = db.get(StrategyVersion, version_id)
        return version.config if version else None

    if strategy.current_version_id is not None:
        version = db.get(StrategyVersion, strategy.current_version_id)
        return version.config if version else None

    return None
