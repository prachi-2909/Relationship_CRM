"""The Supervisor (/ask) also answers about CSPs (kiosk operators), from the RM's recorded calls with them.

Before this it only knew SBI officials, so a question about a CSP the RM had just called came back empty. The
hard part is the boundary: an RM may only ever get answers about their OWN CSPs."""

from datetime import datetime, timezone

from app.models.call_intelligence import CallAIAnalysis, CallSession
from app.models.csp import Csp, CspStatus
from app.models.interaction import Direction
from app.models.user import Role
from app.services import commitments as commitments_svc
from app.services import supervisor

PHONE = "9000000077"


def _csp(db, rm, code, name, status=CspStatus.ACTIVE):
    c = Csp(csp_id=code, name=name, rm_name="RM", rm_user_id=rm.id, mobile=PHONE, category="Gold CSP",
            branch_name="BR", status=status)
    db.add(c)
    db.commit()
    return c


def _call(db, rm, csp, summary, *, performance=None, commitments=None):
    call = CallSession(dc_user_id=rm.id, direction=Direction.OUTBOUND, phone_ref=PHONE,
                       started_at=datetime.now(timezone.utc), csp_id=csp.id)
    db.add(call)
    db.flush()
    brief = {"summary": summary, "highlights": [summary], "commitments": commitments or []}
    if performance:
        brief["performance"] = performance
    db.add(CallAIAnalysis(call_session_id=call.id, analysis_json=brief))
    db.commit()
    db.refresh(call)
    commitments_svc.extract_from_call(db, call)
    db.commit()
    return call


def _world(db, make_user):
    rm_a = make_user(email="rm-a-ask@example.com", password="secret123", role=Role.RELATIONSHIP_MANAGER)
    rm_b = make_user(email="rm-b-ask@example.com", password="secret123", role=Role.RELATIONSHIP_MANAGER)
    mine = _csp(db, rm_a, "1A850899", "Deepak Dhawan")
    theirs = _csp(db, rm_b, "1A850111", "Mohan Verma")
    _call(db, rm_a, mine, "Footfall is low at Deepak Dhawan's kiosk.",
          performance={"what": ["26 PMSBY against a target of 50"], "why": ["Low footfall in the second half"],
                       "should_be": ["50 enrolments by month end"]},
          commitments=["CSP to share the sales report by 2026-12-01."])
    _call(db, rm_b, theirs, "Mohan Verma wants a new device.")
    return rm_a, rm_b, mine, theirs


def _ask(client, login, email, question, **extra):
    client.post("/api/v1/auth/logout")
    login(email, "secret123")
    return client.post("/api/v1/ask", json={"question": question, **extra})


def test_an_rm_gets_an_answer_about_their_own_csp_from_the_call_record(client, db, make_user, login):
    _, _, mine, _ = _world(db, make_user)
    body = _ask(client, login, "rm-a-ask@example.com", "Deepak Dhawan ke baare mein batao").json()

    assert body["scope"] == "targeted"
    assert body["considered"] == [
        {"relationship_id": None, "official_name": "Deepak Dhawan", "kind": "csp", "csp_pk": mine.id}
    ]
    answer = body["answer"]
    assert "Deepak Dhawan" in answer and "1A850899" in answer
    assert "Footfall is low" in answer                                   # the last call's summary
    assert "26 PMSBY against a target of 50" in answer                   # the RM's own performance review
    assert "CSP to share the sales report" in answer                     # what the CSP promised
    assert PHONE not in answer                                           # phone numbers are not needed


def test_the_csp_can_also_be_found_by_its_code(client, db, make_user, login):
    _world(db, make_user)
    body = _ask(client, login, "rm-a-ask@example.com", "what is the status of 1A850899?").json()
    assert body["scope"] == "targeted" and body["considered"][0]["kind"] == "csp"


def test_an_rm_gets_nothing_about_another_rms_csp(client, db, make_user, login):
    _world(db, make_user)
    body = _ask(client, login, "rm-a-ask@example.com", "Mohan Verma ke baare mein batao").json()
    assert body["scope"] == "portfolio"                                   # not matched at all for this RM
    assert all(c["kind"] != "csp" for c in body["considered"])
    assert "Mohan Verma" not in body["answer"] and "new device" not in body["answer"]


def test_an_admin_can_ask_about_any_csp(client, db, make_user, login):
    _world(db, make_user)
    make_user(email="admin-ask@example.com", password="secret123", role=Role.ADMIN)
    body = _ask(client, login, "admin-ask@example.com", "Mohan Verma ke baare mein batao").json()
    assert body["scope"] == "targeted" and "new device" in body["answer"]


def test_a_follow_up_stays_on_the_same_csp(client, db, make_user, login):
    _world(db, make_user)
    first = _ask(client, login, "rm-a-ask@example.com", "Deepak Dhawan ke baare mein batao").json()
    second = client.post("/api/v1/ask", json={"question": "what did unhone commit?",
                                              "conversation_id": first["conversation_id"]}).json()
    assert second["scope"] == "targeted"
    assert [c["csp_pk"] for c in second["considered"]] == [c["csp_pk"] for c in first["considered"]]
    assert "CSP to share the sales report" in second["answer"]


def test_a_forged_earlier_turn_cannot_pull_in_someone_elses_csp(db, make_user):
    """The carried-forward subject comes from a stored turn, so it is re-checked against the asker's scope."""
    rm_a, _, _, theirs = _world(db, make_user)
    forged = [{"relationship_id": None, "official_name": "Mohan Verma", "kind": "csp", "csp_pk": theirs.id}]
    result = supervisor.answer(db, rm_a, "what about him?", prior_considered=forged)
    assert result["scope"] == "portfolio"
    assert "Mohan Verma" not in result["answer"] and "new device" not in result["answer"]


def test_a_csp_with_no_recorded_call_says_so_plainly(client, db, make_user, login):
    rm = make_user(email="rm-c-ask@example.com", password="secret123", role=Role.RELATIONSHIP_MANAGER)
    _csp(db, rm, "1A850222", "Sunita Rao")
    body = _ask(client, login, "rm-c-ask@example.com", "Sunita Rao kaisi hai?").json()
    assert body["scope"] == "targeted"
    assert "no RM call is on record" in body["answer"]


def test_an_inactive_csp_is_not_matched(client, db, make_user, login):
    rm = make_user(email="rm-d-ask@example.com", password="secret123", role=Role.RELATIONSHIP_MANAGER)
    _csp(db, rm, "1A850333", "Ravi Anand", status=CspStatus.INACTIVE)
    body = _ask(client, login, "rm-d-ask@example.com", "Ravi Anand ke baare mein batao").json()
    assert all(c["kind"] != "csp" for c in body["considered"])


def test_a_surname_alone_does_not_match_a_csp(client, db, make_user, login):
    _world(db, make_user)
    body = _ask(client, login, "rm-a-ask@example.com", "Dhawan ka kya haal hai").json()
    assert all(c["kind"] != "csp" for c in body["considered"])
