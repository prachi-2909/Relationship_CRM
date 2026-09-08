from datetime import datetime, timedelta, timezone

from app.models.interaction import Direction, Interaction, InteractionType
from app.models.relationship import Relationship, RiskLevel
from app.services import scoring


def _rel(db, make_official):
    official = make_official(name="Scoring Official")
    rel = Relationship(official_id=official.id)
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return rel


def _interaction(db, rel, *, days_ago: int, itype=InteractionType.NOTE, direction=Direction.INTERNAL):
    db.add(
        Interaction(
            relationship_id=rel.id,
            official_id=rel.official_id,
            type=itype,
            direction=direction,
            occurred_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
            raw_notes="x",
        )
    )
    db.commit()


def test_no_interactions_scores_zero_and_high_risk(db, make_official):
    rel = _rel(db, make_official)
    entry = scoring.recompute_and_store(db, rel, reason="test")
    db.commit()
    assert rel.score == 0
    assert rel.risk_level is RiskLevel.HIGH
    assert entry.weights_version == scoring.WEIGHTS_VERSION
    # followup signal is not active yet -> not stored
    assert "followup" not in entry.components
    assert "recency" in entry.components


def test_recent_frequent_contact_scores_well(db, make_official):
    rel = _rel(db, make_official)
    for d in (1, 4, 8, 15, 22, 30):
        _interaction(db, rel, days_ago=d)
    _interaction(db, rel, days_ago=3, itype=InteractionType.MEETING)
    _interaction(db, rel, days_ago=20, itype=InteractionType.MEETING)
    _interaction(db, rel, days_ago=2, direction=Direction.INBOUND)
    _interaction(db, rel, days_ago=6, direction=Direction.INBOUND)

    scoring.recompute_and_store(db, rel, reason="test")
    db.commit()
    assert rel.score >= 55
    assert rel.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM)
    assert rel.last_interaction_at is not None


def test_stale_contact_decays(db, make_official):
    rel = _rel(db, make_official)
    _interaction(db, rel, days_ago=120)
    scoring.recompute_and_store(db, rel, reason="test")
    db.commit()
    assert rel.score < 20


def test_band_thresholds():
    assert scoring.band(85)[1] is RiskLevel.LOW
    assert scoring.band(65)[1] is RiskLevel.LOW
    assert scoring.band(50)[1] is RiskLevel.MEDIUM
    assert scoring.band(10)[1] is RiskLevel.HIGH
