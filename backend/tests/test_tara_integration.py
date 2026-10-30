"""TARA (through Kiosk KAI) is the source of truth for a CSP's figures, and the call brief and the Supervisor use it.

What must hold: the model can only reach read-only, CSP-bound tools; the CSP code always comes from the CRM and
never from the model; a user can never pull another RM's CSP; and with no key everything behaves as before."""

import json
from datetime import datetime, timezone

import pytest

from app.models.call_intelligence import CallSession
from app.models.csp import Csp, CspStatus
from app.models.interaction import Direction
from app.models.user import Role
from app.services import call_intelligence as call_svc
from app.services import kiosk_kai, llm, tara_check

PHONE = "9000000088"
FACTS = [{"tool": "tara.csp_performance", "as_of": "2026-10-30", "source": "tara",
          "caveats": None, "data": {"PMJJBY": {"target": 10, "achieved": 4, "remaining": 6}}}]


# ---------------------------------------------------------------- the lookups the model may ask for

def test_the_model_can_only_pick_read_only_csp_tools_with_safe_arguments(monkeypatch):
    plan = {"calls": [{"tool": "tara.call_outcomes",
                       "args": {"days": 9999, "outcome": "answered", "csp_code": "SOMEONE-ELSE", "rm": "Another RM"}},
                      {"tool": "tara.command_center", "args": {}},          # business-wide: not allowed
                      {"tool": "tara.insights", "args": {"days": 7}}]}      # a second call: over the limit
    monkeypatch.setattr(llm, "chat", lambda *a, **k: json.dumps(plan))

    got = tara_check.plan_extra("how did the last calls go?")

    assert got == [("tara.call_outcomes", {"days": tara_check.MAX_DAYS, "outcome": "answered"})]   # clamped, stripped


@pytest.mark.parametrize("reply", [None, "not json at all", '{"calls": "nope"}', '{"calls": [{"tool": "os.system"}]}',
                                   '{"calls": [{"tool": "tara.my_csps"}]}'])
def test_a_bad_or_unsafe_plan_means_no_extra_lookup(monkeypatch, reply):
    monkeypatch.setattr(llm, "chat", lambda *a, **k: reply)
    assert tara_check.plan_extra("anything") == []


def test_a_period_must_look_like_a_month(monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda *a, **k: json.dumps(
        {"calls": [{"tool": "tara.csp_performance", "args": {"period": "last month; drop table"}}]}))
    # csp_performance is a base tool, so it is never a planned extra
    assert tara_check.plan_extra("q") == []
    assert tara_check._clean_args("tara.csp_performance", {"period": "2026-09"}) == {"period": "2026-09"}
    assert tara_check._clean_args("tara.csp_performance", {"period": "2026-13"}) == {}
    assert tara_check._clean_args("tara.csp_performance", {"period": "x"}) == {}


def test_the_csp_code_always_comes_from_the_crm(monkeypatch):
    sent = []

    def fake_call(tool, **args):
        sent.append((tool, args))
        return {"data": {"ok": 1}, "as_of": "2026-10-30", "source": "tara", "caveats": None}

    monkeypatch.setattr(kiosk_kai, "configured", lambda: True)
    monkeypatch.setattr(kiosk_kai, "call", fake_call)
    monkeypatch.setattr(tara_check, "plan_extra", lambda q: [("tara.call_outcomes", {"days": 14})])

    results = tara_check.gather("how are the calls going?", "1A850899")

    assert [t for t, _ in sent] == ["tara.csp_performance", "tara.csp_profile", "tara.call_outcomes"]
    assert all(args["csp_code"] == "1A850899" for _, args in sent)
    assert sent[2][1] == {"csp_code": "1A850899", "days": 14}
    assert [r["tool"] for r in results] == ["tara.csp_performance", "tara.csp_profile", "tara.call_outcomes"]


def test_nothing_is_called_without_a_key(monkeypatch):
    monkeypatch.setattr(kiosk_kai.settings, "kiosk_kai_app_key", None)
    monkeypatch.setattr(kiosk_kai, "call", lambda *a, **k: (_ for _ in ()).throw(AssertionError("called without a key")))
    assert tara_check.base_facts("1A850899") == []
    assert tara_check.gather("q", "1A850899") == []


def test_when_tara_does_not_answer_there_are_no_facts(monkeypatch):
    monkeypatch.setattr(kiosk_kai, "configured", lambda: True)
    monkeypatch.setattr(kiosk_kai, "call", lambda *a, **k: None)
    assert tara_check.gather("q", "1A850899") == []


def test_a_huge_answer_is_cut_so_it_cannot_flood_the_prompt():
    big = {"rows": ["x" * 100] * 500}
    shrunk = tara_check._shrink(big)
    assert shrunk["truncated"] is True and len(shrunk["text"]) == tara_check.MAX_CHARS
    assert tara_check._shrink({"a": 1}) == {"a": 1}


# ---------------------------------------------------------------- the call brief

def _csp_call(db, make_user, email="rm-tara-brief@example.com"):
    rm = make_user(email=email, password="secret123", role=Role.RELATIONSHIP_MANAGER)
    csp = Csp(csp_id="1A850899", name="Deepak Dhawan", rm_name="RM", rm_user_id=rm.id, mobile=PHONE,
              category="Gold CSP", branch_name="BR", status=CspStatus.ACTIVE)
    db.add(csp)
    db.commit()
    call = CallSession(dc_user_id=rm.id, direction=Direction.OUTBOUND, phone_ref=PHONE,
                       started_at=datetime.now(timezone.utc), csp_id=csp.id)
    db.add(call)
    db.commit()
    return rm, csp, call


def _capture_chat(monkeypatch, reply):
    seen = {}

    def fake(system, user, **k):
        seen.update(system=system, user=user)
        return reply

    monkeypatch.setattr(llm, "chat", fake)
    return seen


def test_the_brief_is_given_tara_as_the_source_of_truth(db, make_user, monkeypatch):
    _, csp, call = _csp_call(db, make_user)
    asked = []
    monkeypatch.setattr(tara_check, "base_facts", lambda code: asked.append(code) or FACTS)
    seen = _capture_chat(monkeypatch, json.dumps({
        "summary": "s", "highlights": ["TARA check: PMJJBY remaining 6 (TARA, as of 2026-10-30), matches the call"]}))

    brief = call_svc.generate_brief(db, call, "CSP said 6 PMJJBY remaining.")

    assert asked == ["1A850899"]                                   # the CSP of THIS call, from the CRM
    assert "SOURCE OF TRUTH" in seen["system"] and "TARA check: " in seen["system"]
    assert seen["user"].startswith("CSP said 6 PMJJBY remaining.")        # the transcript is untouched
    assert "=== TARA (source of truth" in seen["user"] and '"remaining": 6' in seen["user"]
    assert brief["highlights"] == ["TARA check: PMJJBY remaining 6 (TARA, as of 2026-10-30), matches the call"]


def test_the_brief_is_unchanged_when_tara_gives_nothing(db, make_user, monkeypatch):
    _, _, call = _csp_call(db, make_user, email="rm-tara-none@example.com")
    monkeypatch.setattr(tara_check, "base_facts", lambda code: [])
    seen = _capture_chat(monkeypatch, json.dumps({"summary": "s", "highlights": []}))

    call_svc.generate_brief(db, call, "CSP said 6 PMJJBY remaining.")

    assert "SOURCE OF TRUTH" not in seen["system"] and "TARA" not in seen["user"]
    assert seen["user"] == "CSP said 6 PMJJBY remaining."


def test_a_call_that_is_not_with_a_csp_never_asks_tara(db, make_user, monkeypatch):
    dc = make_user(email="dc-tara-brief@example.com", password="secret123", role=Role.DC)
    call = CallSession(dc_user_id=dc.id, direction=Direction.OUTBOUND, phone_ref=PHONE,
                       started_at=datetime.now(timezone.utc))
    db.add(call)
    db.commit()
    monkeypatch.setattr(tara_check, "base_facts", lambda code: (_ for _ in ()).throw(AssertionError("asked TARA")))
    _capture_chat(monkeypatch, json.dumps({"summary": "s", "highlights": []}))

    call_svc.generate_brief(db, call, "Spoke to the branch manager.")


# ---------------------------------------------------------------- the Supervisor

def _ask(client, login, email, question):
    client.post("/api/v1/auth/logout")
    login(email, "secret123")
    return client.post("/api/v1/ask", json={"question": question})


def _two_rms(db, make_user):
    rm_a = make_user(email="rm-a-tara@example.com", password="secret123", role=Role.RELATIONSHIP_MANAGER)
    rm_b = make_user(email="rm-b-tara@example.com", password="secret123", role=Role.RELATIONSHIP_MANAGER)
    for rm, code, name in ((rm_a, "1A850899", "Deepak Dhawan"), (rm_b, "1A850111", "Mohan Verma")):
        db.add(Csp(csp_id=code, name=name, rm_name="RM", rm_user_id=rm.id, mobile=PHONE, category="Gold CSP",
                   branch_name="BR", status=CspStatus.ACTIVE))
    db.commit()


def test_the_supervisor_attaches_tara_to_the_csp_asked_about(client, db, make_user, login, monkeypatch):
    _two_rms(db, make_user)
    asked = []
    monkeypatch.setattr(tara_check, "gather", lambda q, code: asked.append(code) or FACTS)
    seen = _capture_chat(monkeypatch, "Deepak Dhawan: TARA shows 6 PMJJBY remaining (as of 2026-10-30).")

    body = _ask(client, login, "rm-a-tara@example.com", "Deepak Dhawan ka PMJJBY kitna baaki hai?").json()

    assert asked == ["1A850899"]
    assert "tara_source_of_truth" in seen["user"] and '"remaining": 6' in seen["user"]
    assert "SOURCE OF TRUTH" in seen["system"]
    assert "TARA shows 6 PMJJBY remaining" in body["answer"]


def test_an_rm_cannot_reach_another_rms_csp_through_tara(client, db, make_user, login, monkeypatch):
    _two_rms(db, make_user)
    asked = []
    monkeypatch.setattr(tara_check, "gather", lambda q, code: asked.append(code) or FACTS)
    _capture_chat(monkeypatch, "nothing on record")

    _ask(client, login, "rm-a-tara@example.com", "Mohan Verma ka PMJJBY kitna baaki hai?")

    assert asked == []                                              # RM A may not see RM B's CSP: no lookup at all


def test_the_supervisor_is_unchanged_when_tara_gives_nothing(client, db, make_user, login, monkeypatch):
    _two_rms(db, make_user)
    monkeypatch.setattr(tara_check, "gather", lambda q, code: [])
    seen = _capture_chat(monkeypatch, "answer")

    _ask(client, login, "rm-a-tara@example.com", "Deepak Dhawan ke baare mein batao")

    assert "tara_source_of_truth" not in seen["user"] and "SOURCE OF TRUTH" not in seen["system"]
