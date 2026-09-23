from app.models.relationship import Relationship
from app.models.semantic_memory import SemanticVerificationState
from app.models.user import Role, User
from app.services import semantic_memory as semantic_memory_svc


def _as(make_user, login, role: Role, email: str):
    make_user(email=email, password="secret123", role=role)
    login(email, "secret123")


def _official(client, name: str) -> int:
    return client.post("/api/v1/officials", json={"name": name}).json()["id"]


# --- extraction: offline stub never invents facts -------------------------


def test_stub_extraction_returns_no_facts_offline():
    assert semantic_memory_svc.extract_facts("He prefers email over calls.") == []


def test_extraction_disabled_returns_nothing(monkeypatch):
    monkeypatch.setattr(semantic_memory_svc.settings, "enable_semantic_memory", False)
    monkeypatch.setattr(semantic_memory_svc.settings, "llm_base_url", "http://fake")
    assert semantic_memory_svc.extract_facts("anything") == []


# --- upsert_fact conflict rules --------------------------------------------


def test_new_fact_inserts_as_unverified(db, make_official):
    official = make_official(name="A")
    fact = semantic_memory_svc.upsert_fact(
        db, official_id=official.id, fact_text="Prefers email", fact_key="preferred_channel", confidence=60,
        source_type="interaction",
    )
    db.commit()
    assert fact is not None
    assert fact.verification_state == SemanticVerificationState.UNVERIFIED


def test_human_edit_inserts_as_confirmed(db, make_official, make_user):
    official = make_official(name="B")
    user = make_user(email="u1@example.com")
    fact = semantic_memory_svc.upsert_fact(
        db, official_id=official.id, fact_text="Prefers calls", fact_key="preferred_channel",
        confidence=100, source_type="human_edit", created_by=user.id,
    )
    db.commit()
    assert fact.verification_state == SemanticVerificationState.HUMAN_CONFIRMED


def test_confirmed_fact_is_never_overwritten_by_lower_trust_write(db, make_official, make_user):
    official = make_official(name="C")
    user = make_user(email="u2@example.com")
    confirmed = semantic_memory_svc.upsert_fact(
        db, official_id=official.id, fact_text="Prefers calls", fact_key="preferred_channel",
        confidence=100, source_type="human_edit", created_by=user.id,
    )
    db.commit()

    result = semantic_memory_svc.upsert_fact(
        db, official_id=official.id, fact_text="Prefers email", fact_key="preferred_channel",
        confidence=90, source_type="interaction",
    )
    db.commit()
    db.refresh(confirmed)
    assert result is None
    assert confirmed.verification_state == SemanticVerificationState.HUMAN_CONFIRMED
    assert confirmed.fact_text == "Prefers calls"


def test_human_edit_supersedes_a_confirmed_fact(db, make_official, make_user):
    official = make_official(name="D")
    user = make_user(email="u3@example.com")
    original = semantic_memory_svc.upsert_fact(
        db, official_id=official.id, fact_text="Prefers calls", fact_key="preferred_channel",
        confidence=100, source_type="human_edit", created_by=user.id,
    )
    db.commit()

    updated = semantic_memory_svc.upsert_fact(
        db, official_id=official.id, fact_text="Actually prefers email", fact_key="preferred_channel",
        confidence=100, source_type="human_edit", created_by=user.id,
    )
    db.commit()
    db.refresh(original)
    assert updated is not None
    assert updated.verification_state == SemanticVerificationState.HUMAN_CONFIRMED
    assert original.verification_state == SemanticVerificationState.SUPERSEDED
    assert original.superseded_by_id == updated.id


def test_unverified_fact_replaced_only_if_confidence_not_lower(db, make_official):
    official = make_official(name="E")
    low = semantic_memory_svc.upsert_fact(
        db, official_id=official.id, fact_text="Maybe prefers email", fact_key="preferred_channel",
        confidence=40, source_type="interaction",
    )
    db.commit()

    weaker = semantic_memory_svc.upsert_fact(
        db, official_id=official.id, fact_text="Maybe prefers calls", fact_key="preferred_channel",
        confidence=20, source_type="interaction",
    )
    db.commit()
    db.refresh(low)
    assert weaker is None
    assert low.fact_text == "Maybe prefers email"

    stronger = semantic_memory_svc.upsert_fact(
        db, official_id=official.id, fact_text="Confirmed prefers calls", fact_key="preferred_channel",
        confidence=70, source_type="interaction",
    )
    db.commit()
    assert stronger is not None
    assert stronger.fact_text == "Confirmed prefers calls"


def test_no_fact_key_always_inserts_new(db, make_official):
    official = make_official(name="F")
    a = semantic_memory_svc.upsert_fact(db, official_id=official.id, fact_text="Fact one", source_type="interaction")
    b = semantic_memory_svc.upsert_fact(db, official_id=official.id, fact_text="Fact two", source_type="interaction")
    db.commit()
    assert a is not None and b is not None
    assert a.id != b.id


def test_provenanced_field_name_is_rejected(db, make_official):
    official = make_official(name="G")
    result = semantic_memory_svc.upsert_fact(
        db, official_id=official.id, fact_text="Some designation text", fact_key="designation",
        confidence=80, source_type="interaction",
    )
    db.commit()
    assert result is None


def test_facts_for_official_excludes_rejected_and_superseded(db, make_official, make_user):
    official = make_official(name="H")
    user = make_user(email="u4@example.com")
    keep = semantic_memory_svc.upsert_fact(
        db, official_id=official.id, fact_text="Keep me", fact_key="k1", confidence=80, source_type="interaction",
    )
    rejected = semantic_memory_svc.upsert_fact(
        db, official_id=official.id, fact_text="Reject me", fact_key="k2", confidence=80, source_type="interaction",
    )
    db.commit()
    semantic_memory_svc.reject_fact(db, rejected, user)
    db.commit()

    visible = semantic_memory_svc.facts_for_official(db, official.id)
    ids = {f.id for f in visible}
    assert keep.id in ids
    assert rejected.id not in ids


# --- API / RBAC -------------------------------------------------------------


def test_facts_route_requires_auth(client):
    resp = client.get("/api/v1/officials/1/facts")
    assert resp.status_code == 401


def test_approver_viewer_can_read_but_not_write_facts(client, make_user, login):
    off_id = 0
    _as(make_user, login, Role.ADMIN, "admin2@example.com")
    off_id = _official(client, "Reader Target")
    client.post("/api/v1/auth/logout")

    _as(make_user, login, Role.APPROVER_VIEWER, "viewer@example.com")
    resp = client.get(f"/api/v1/officials/{off_id}/facts")
    assert resp.status_code == 200

    resp = client.post(f"/api/v1/officials/{off_id}/facts", json={"fact_text": "New fact"})
    assert resp.status_code == 403


def test_create_and_verify_fact_via_api(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin3@example.com")
    off_id = _official(client, "API Target")

    resp = client.post(f"/api/v1/officials/{off_id}/facts", json={"fact_text": "Likes early morning calls"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["verification_state"] == "human_confirmed"  # human-entered facts land confirmed

    resp = client.get(f"/api/v1/officials/{off_id}/facts")
    assert resp.status_code == 200
    assert any(f["id"] == body["id"] for f in resp.json())
