from app.models.user import Role
from app.services.supervisor import _looks_like_followup


def _as(make_user, login, role: Role, email: str):
    make_user(email=email, password="secret123", role=role)
    login(email, "secret123")


def _official(client, name: str, level: str | None = None) -> int:
    return client.post("/api/v1/officials", json={"name": name, "level": level}).json()[
        "id"
    ]


def _rel(client, official_id: int) -> int:
    return client.post(
        "/api/v1/relationships", json={"official_id": official_id}
    ).json()["id"]


def test_ask_without_conversation_id_starts_one(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    off = _official(client, "Ganesh Kumar", "GM")
    _rel(client, off)

    resp = client.post("/api/v1/ask", json={"question": "What is going on with Ganesh Kumar?"})
    assert resp.status_code == 200
    conv_id = resp.json()["conversation_id"]
    assert isinstance(conv_id, int)

    detail = client.get(f"/api/v1/ask/conversations/{conv_id}").json()
    assert detail["title"] == "What is going on with Ganesh Kumar?"
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][0]["content"] == "What is going on with Ganesh Kumar?"
    assert detail["messages"][1]["scope"] == "targeted"


def test_second_question_with_same_id_continues_the_conversation(
    client, make_user, login
):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    off = _official(client, "Ganesh Kumar", "GM")
    _rel(client, off)

    first = client.post(
        "/api/v1/ask", json={"question": "What is going on with Ganesh Kumar?"}
    ).json()
    conv_id = first["conversation_id"]

    second = client.post(
        "/api/v1/ask",
        json={"question": "Anything else I should know?", "conversation_id": conv_id},
    ).json()
    assert second["conversation_id"] == conv_id

    detail = client.get(f"/api/v1/ask/conversations/{conv_id}").json()
    assert len(detail["messages"]) == 4
    # title is set from the FIRST question only
    assert detail["title"] == "What is going on with Ganesh Kumar?"


def test_followup_pronoun_carries_forward_previous_subject(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    ganesh = _official(client, "Ganesh Kumar", "GM")
    _rel(client, ganesh)
    # an unrelated relationship so a portfolio fallback would clearly differ
    other = _official(client, "Meera Iyer", "AGM")
    _rel(client, other)

    first = client.post(
        "/api/v1/ask", json={"question": "What is going on with Ganesh Kumar?"}
    ).json()
    assert first["scope"] == "targeted"
    conv_id = first["conversation_id"]

    followup = client.post(
        "/api/v1/ask",
        json={"question": "What about his stakeholders?", "conversation_id": conv_id},
    ).json()
    assert followup["scope"] == "targeted"
    assert followup["considered"] == [
        {"relationship_id": first["considered"][0]["relationship_id"], "official_name": "Ganesh Kumar"}
    ]


def test_non_followup_question_falls_back_to_portfolio_even_mid_conversation(
    client, make_user, login
):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    ganesh = _official(client, "Ganesh Kumar", "GM")
    _rel(client, ganesh)

    first = client.post(
        "/api/v1/ask", json={"question": "What is going on with Ganesh Kumar?"}
    ).json()
    conv_id = first["conversation_id"]

    # no pronoun, no name -> a genuinely portfolio-shaped question should
    # NOT be silently narrowed to whoever was discussed last
    second = client.post(
        "/api/v1/ask",
        json={"question": "What should I focus on this week?", "conversation_id": conv_id},
    ).json()
    assert second["scope"] == "portfolio"


def test_conversation_is_scoped_to_its_owner(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    off = _official(client, "Ganesh Kumar", "GM")
    _rel(client, off)
    conv_id = client.post(
        "/api/v1/ask", json={"question": "What is going on with Ganesh Kumar?"}
    ).json()["conversation_id"]

    _as(make_user, login, Role.RELATIONSHIP_MANAGER, "rm@example.com")
    assert client.get(f"/api/v1/ask/conversations/{conv_id}").status_code == 404
    assert (
        client.post(
            "/api/v1/ask",
            json={"question": "Continue please", "conversation_id": conv_id},
        ).status_code
        == 404
    )


def test_unknown_conversation_id_is_404(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    resp = client.get("/api/v1/ask/conversations/999999")
    assert resp.status_code == 404


def test_list_conversations_returns_only_the_caller_s_own(client, make_user, login):
    _as(make_user, login, Role.ADMIN, "admin@example.com")
    off = _official(client, "Ganesh Kumar", "GM")
    _rel(client, off)
    client.post("/api/v1/ask", json={"question": "What is going on with Ganesh Kumar?"})

    _as(make_user, login, Role.RELATIONSHIP_MANAGER, "rm@example.com")
    client.post("/api/v1/ask", json={"question": "What should I focus on this week?"})

    mine = client.get("/api/v1/ask/conversations").json()
    assert len(mine) == 1
    assert mine[0]["title"] == "What should I focus on this week?"


def test_looks_like_followup_matches_pronouns_only():
    assert _looks_like_followup("What about his stakeholders?")
    assert _looks_like_followup("Unke connections kya hain?")
    assert not _looks_like_followup("What should I focus on this week?")
    assert not _looks_like_followup("What is going on with Ganesh Kumar?")
