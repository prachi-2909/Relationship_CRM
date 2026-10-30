"""The Birthday Wishes page lists drafts for many CSPs at once. With a real LLM behind it, writing each one with a
model call made the page end in a gateway time-out; the list must never wait on the model."""

import json
from datetime import date, timedelta

import pytest

from app.models.csp import Csp, CspStatus
from app.models.user import Role
from app.services import birthdays, llm


@pytest.fixture(autouse=True)
def _clean_cache():
    birthdays._draft_cache.clear()
    yield
    birthdays._draft_cache.clear()


def _csp(db, rm, code, name, *, days_ahead):
    dob = date.today() + timedelta(days=days_ahead)
    c = Csp(csp_id=code, name=name, rm_name="RM", rm_user_id=rm.id, mobile="9000000044", category="Gold CSP",
            branch_name="BR", status=CspStatus.ACTIVE, date_of_birth=date(1990, dob.month, dob.day),
            email=f"{code.lower()}@example.com")
    db.add(c)
    db.commit()
    return c


def _llm(monkeypatch, calls):
    def fake(system, user, **k):
        calls.append(user)
        return json.dumps({"subject": "Happy Birthday!", "hindi": "जन्मदिन मुबारक", "english": "Happy birthday!"})

    monkeypatch.setattr(llm, "chat", fake)


def test_the_preview_never_waits_on_the_model(client, db, make_user, login, monkeypatch):
    admin = make_user(email="admin-bday@example.com", password="secret123", role=Role.ADMIN)
    for i in range(5):
        _csp(db, admin, f"B{i}", f"Birthday CSP {i}", days_ahead=i + 1)
    monkeypatch.setattr(llm, "chat", lambda *a, **k: (_ for _ in ()).throw(AssertionError("the page called the model")))
    login("admin-bday@example.com", "secret123")

    resp = client.get("/api/v1/csps/birthday-wishes/preview")

    assert resp.status_code == 200
    items = resp.json()["upcoming"] if "upcoming" in resp.json() else resp.json()
    flat = json.dumps(items)
    assert "Birthday CSP 0" in flat and '"generated_by": "template"' in flat


def test_a_draft_the_model_wrote_is_remembered_and_shown_by_the_list(db, make_user, monkeypatch):
    rm = make_user(email="rm-bday@example.com", password="secret123", role=Role.RELATIONSHIP_MANAGER)
    csp = _csp(db, rm, "B-ONE", "Remembered CSP", days_ahead=3)
    calls: list = []
    _llm(monkeypatch, calls)

    first = birthdays.personalize(db, csp)                       # a send: the model writes it
    assert calls and first["generated_by"] != "template"

    again = birthdays.personalize(db, csp, use_llm=False)        # a list: the same draft, no second model call
    assert again == first and len(calls) == 1


def test_a_list_falls_back_to_the_template_when_nothing_was_written_yet(db, make_user, monkeypatch):
    rm = make_user(email="rm-bday2@example.com", password="secret123", role=Role.RELATIONSHIP_MANAGER)
    csp = _csp(db, rm, "B-TWO", "Fresh CSP", days_ahead=4)
    monkeypatch.setattr(llm, "chat", lambda *a, **k: (_ for _ in ()).throw(AssertionError("called")))

    draft = birthdays.personalize(db, csp, use_llm=False)

    assert draft["generated_by"] == "template"
    assert "Gold CSP" in draft["message"] and "Happy birthday" not in draft["message"]      # built from the CSP's facts
