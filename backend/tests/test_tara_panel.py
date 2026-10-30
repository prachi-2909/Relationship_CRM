"""TARA's figures laid out for an RM, and the two score signals read from them.

The fixtures below are cut down from TARA's real answers for two live CSPs (a weak one and a quiet one whose
targets are not set), so the code is tested against the shapes TARA really sends."""

import json
from datetime import date, datetime, timezone

import pytest

from app.models.csp import Csp, CspStatus
from app.models.user import Role
from app.services import csp_scoring, kiosk_kai, tara_check, tara_panel

SLAB_NEXT = {
    "name": "Slab-1", "incentive_inr": 1200, "abm_commission_pct": 85, "already": False,
    "schemes": [
        {"scheme": "pmjdy", "have": 0, "threshold": 8, "more": 8},
        {"scheme": "pmjjby", "have": 0, "threshold": 12, "more": 12},
        {"scheme": "pmsby", "have": 0, "threshold": 20, "more": 20},
        {"scheme": "apy", "have": 0, "threshold": 3, "more": 3},
    ],
    "pick": ["apy", "pmjdy", "pmjjby"], "extra_total": 23,
}


def _goal(product, target, progress=0, agent=None, pace="at_risk"):
    return {"product": product, "name": product.upper(), "metric": "txn_count", "unit": "count", "target": target,
            "agent_target": agent, "progress": progress, "progress_pct": 0, "pace_status": pace,
            "period_start": "2026-10-01", "period_end": "2026-10-31"}


def _product(target, achieved=0):
    return {"achieved": {"sbi_monthly": achieved, "sbi_daily_sum": achieved, "calling_sheet": 0},
            "target": {"sbi": target}}


WEAK = {   # 1A851916
    "as_of": "2026-10-30T10:10:29+05:30",
    "caveats": ["Growth in earnings is for Sep-26, the newest month SBI has posted commission for."],
    "data": {
        "csp_code": "1A851916", "period": {"month": "2026-10", "is_current_month": True},
        "transactions": {"count": {"sbi_daily_sum": 0, "sbi_monthly": 0}, "gtv_inr": {"sbi_daily_sum": 0, "sbi_monthly": 0.0},
                         "days_with_data": 29, "last_day_with_data": "2026-10-29", "by_type": [],
                         "by_day": [{"date": f"2026-10-{d:02d}", "txn_count": 0, "txn_gtv": 0.0} for d in range(1, 30)]},
        "products": {"pmjdy": _product(10), "pmjjby": _product(5), "pmsby": _product(5), "apy": _product(5)},
        "tara_goals": [_goal("pmjdy", 10, agent=13), _goal("pmjjby", 5), _goal("pmsby", 5, agent=6), _goal("apy", 5),
                       _goal("login-days", 21)],
        "commission": {"month_total_inr": None, "target_inr": 7056.0, "by_product": [],
                       "latest_posted_month": {"label": "Aug-26", "commission_inr": 1131.52, "products": 9, "txns": 87}},
        "dfs_slab": {"rule": "A slab is reached when at least 3 of the 4 schemes meet that slab's column.",
                     "from_sbi_daily_sum": {"counts": {}, "reached": None, "next": SLAB_NEXT},
                     "calling_sheet": {"reached_label": "No Slab", "target_label": "Slab-2 (₹1,500)"}},
        "growth": {"commission_inr": {"month": "Sep-26", "value": 0, "usual": 4066, "growth_pct": -100.0,
                                      "status": "degrow", "rank_in_district": 1, "of": 1},
                   "transactions": {"month": "Oct-26", "value": 0, "usual": 0, "growth_pct": None, "status": "stable"}},
        "levers": {"as_of": "2026-10-30", "items": [{"lever": "pmjjby", "monthly_inr": 112, "detail": {"remaining": 5}},
                                                    {"lever": "dfs_slab", "monthly_inr": 1500, "detail": {}}]},
        "citations": {"name": "app.db:x"},
    },
}
WEAK_PROFILE = {
    "as_of": "2026-10-30T10:10:29+05:30",
    "caveats": ["Name, mobile and email are masked (restricted personal data)."],
    "data": {"csp_code": "1A851916", "identity": {"name": "A*** K*** Y***", "mobile": "96XXXXXX38"},
             "terminals": {"terminal_status": "Inactive", "matm_status": "Yes", "passbook_printer_status": "No",
                           "gps_dongle_status": "Yes"},
             "last_login_date": "2026-08-05"},
}
QUIET = {   # 1A850044: targets are not set in SBI's data
    "as_of": "2026-10-30T10:10:29+05:30",
    "caveats": ["Every SBI target for Oct-26 is 0 in csp_data.db monthly_targets: targets are not set there."],
    "data": {
        "csp_code": "1A850044", "period": {"month": "2026-10"},
        "transactions": {"count": {"sbi_daily_sum": 0, "sbi_monthly": 0}, "gtv_inr": {"sbi_daily_sum": 0, "sbi_monthly": 0.0},
                         "days_with_data": 29, "last_day_with_data": "2026-10-29"},
        "products": {"pmjdy": _product(0), "pmjjby": _product(0), "pmsby": _product(0), "apy": _product(0)},
        "tara_goals": [_goal("login-days", 21)],
        "commission": {"target_inr": 0.0, "latest_posted_month": {"label": "Sep-26", "commission_inr": 1000.0}},
        "dfs_slab": {"from_sbi_daily_sum": {"reached": None, "next": SLAB_NEXT},
                     "calling_sheet": {"reached_label": "No Slab", "target_label": "—"}},
        "growth": {"commission_inr": {"month": "Sep-26", "value": 1000, "usual": 0, "growth_pct": None, "status": "grow"},
                   "transactions": {"month": "Oct-26", "value": 0, "usual": 0, "growth_pct": None, "status": "stable"}},
        "levers": None,
        "rm_call_list": {"plan_date": "2026-10-30", "rm": "Shiwani", "priority": "urgent", "rank": 20,
                         "daily_target_txns": 21, "daily_target_inr": 571.43},
        "calling_sheet_month": {"login_days": 0, "inactivity_days": 91},
        "balance": {"total_accounts": 56, "deposit_for_higher_slab_inr": 150000},
    },
}


# ---------------------------------------------------------------- the panel

def test_the_panel_copies_tara_figures_as_they_are():
    p = tara_panel.build_panel(WEAK, WEAK_PROFILE)

    assert p["available"] is True and p["as_of"] == "2026-10-30T10:10:29+05:30" and p["month"] == "2026-10"
    assert p["slab"]["reached_in_calling_sheet"] == "No Slab" and p["slab"]["target_in_calling_sheet"] == "Slab-2 (₹1,500)"
    nxt = p["slab"]["next"]
    assert (nxt["name"], nxt["incentive_inr"], nxt["extra_total"]) == ("Slab-1", 1200, 23)
    assert nxt["closest_three"] == ["APY", "PMJDY", "PMJJBY"]
    assert {"scheme": "PMJJBY", "have": 0, "threshold": 12, "more": 12} in nxt["schemes"]

    jdy = next(r for r in p["products"] if r["code"] == "pmjdy")
    assert (jdy["achieved"], jdy["achieved_basis"], jdy["sbi_target"], jdy["tara_goal"], jdy["agent_target"]) == \
        (0, "sbi_daily_sum", 10, 10, 13)
    assert jdy["pace_status"] == "at_risk"
    assert [r["name"] for r in p["products"]] == ["PMJDY", "PMJJBY", "PMSBY", "APY"]      # the four core schemes only

    e = p["earnings"]
    assert (e["month"], e["value_inr"], e["usual_inr"], e["growth_pct"], e["status"]) == ("Sep-26", 0, 4066, -100.0, "degrow")
    assert e["latest_posted_commission"] == {"label": "Aug-26", "inr": 1131.52}
    assert p["activity"]["last_login_date"] == "2026-08-05" and p["activity"]["terminal_status"] == "Inactive"
    assert [o["lever"] for o in p["opportunities"]] == ["pmjjby", "dfs_slab"]
    assert p["transactions"]["days_with_data"] == 29 and p["transactions"]["last_day_with_data"] == "2026-10-29"
    assert len(p["caveats"]) == 2                                                          # both sources', no repeats


def test_a_target_sbi_has_not_set_is_missing_not_zero():
    p = tara_panel.build_panel(QUIET, None)
    for row in p["products"]:
        assert row["sbi_target"] is None and row["tara_goal"] is None
    assert p["earnings"]["month_target_inr"] is None
    assert p["opportunities"] == []                                  # levers was null
    assert p["call_priority"]["priority"] == "urgent" and p["balance"]["deposit_for_higher_slab_inr"] == 150000


def test_when_tara_gave_nothing_the_panel_says_so():
    assert tara_panel.build_panel(None, None) == {"available": False}
    assert tara_panel.build_panel({}, {}) == {"available": False}


def test_a_missing_or_odd_field_never_breaks_the_panel():
    odd = {"as_of": "x", "data": {"products": "nope", "tara_goals": {"a": 1}, "dfs_slab": [], "growth": None,
                                  "transactions": {"count": None}}}
    p = tara_panel.build_panel(odd, None)
    assert p["available"] is True and p["slab"] is None and p["earnings"] is None


# ---------------------------------------------------------------- the two score signals

def test_performance_allows_for_how_much_of_the_month_has_gone():
    # 29 days of 31 gone, nothing done on any core scheme: 0, and the note says exactly what and why
    value, note = tara_panel.performance_signal(WEAK["data"], date(2026, 10, 29))
    assert value == 0.0
    assert note == "TARA goals this month: PMJDY 0 of 10, PMJJBY 0 of 5, PMSBY 0 of 5, APY 0 of 5 (94% of the month gone)."

    # halfway through the month, 2 of 5 done = 40% against 50% expected = 80
    data = {"tara_goals": [dict(_goal("pmjjby", 5, progress=2), period_start="2026-10-01", period_end="2026-10-30")]}
    value, _ = tara_panel.performance_signal(data, date(2026, 10, 15))
    assert value == 80.0

    # on or ahead of pace is capped at 100
    data = {"tara_goals": [_goal("apy", 5, progress=5)]}
    assert tara_panel.performance_signal(data, date(2026, 10, 10))[0] == 100.0


def test_performance_ignores_non_core_goals_and_goals_without_a_target():
    data = {"tara_goals": [_goal("login-days", 21), _goal("pmjdy", None), {"product": "apy", "target": 5}]}
    assert tara_panel.performance_signal(data, date(2026, 10, 20)) == (None, "")
    assert tara_panel.performance_signal(None, date(2026, 10, 20)) == (None, "")


def test_trend_reads_earnings_growth_against_the_usual():
    value, note = tara_panel.trend_signal(WEAK["data"])
    assert value == 0.0                                             # -100% earnings; transactions have no usual to compare
    assert note == "Earnings for Sep-26: Rs 0 against a usual 4,066 (-100%)."

    def with_growth(pct):
        return {"growth": {"commission_inr": {"month": "Sep-26", "value": 1, "usual": 1, "growth_pct": pct}}}

    assert tara_panel.trend_signal(with_growth(0))[0] == 50.0
    assert tara_panel.trend_signal(with_growth(10))[0] == 70.0
    assert tara_panel.trend_signal(with_growth(40))[0] == 100.0      # capped
    assert tara_panel.trend_signal(with_growth(-40))[0] == 0.0       # floored


def test_trend_falls_back_to_tara_status_only_when_there_is_something_to_compare():
    value, _ = tara_panel.trend_signal(QUIET["data"])               # earnings 1000, no usual, status grow
    assert value == 75.0
    nothing = {"growth": {"commission_inr": {"month": "Sep-26", "value": 0, "usual": 0, "growth_pct": None, "status": "stable"}}}
    assert tara_panel.trend_signal(nothing) == (None, "")           # stable at 0 against 0 says nothing


# ---------------------------------------------------------------- what the model is given

def test_a_long_per_day_table_cannot_push_the_figures_that_matter_out_of_the_prompt(monkeypatch):
    def fake_call(tool, **args):
        return WEAK if tool == "tara.csp_performance" else WEAK_PROFILE

    monkeypatch.setattr(kiosk_kai, "configured", lambda: True)
    monkeypatch.setattr(kiosk_kai, "call", fake_call)
    monkeypatch.setattr(kiosk_kai.settings, "ai_data_processing_enabled", True)
    monkeypatch.setattr(tara_check.settings, "ai_data_processing_enabled", True)

    perf = tara_check.base_facts("1A851916")[0]["data"]

    assert "products" in perf and "dfs_slab" in perf and "tara_goals" in perf          # not cut off
    assert "by_day" not in perf["transactions"] and len(perf["transactions"]["last_7_days"]) == 7
    assert "citations" not in perf
    assert len(json.dumps(perf)) < tara_check.MAX_CHARS
    profile = tara_check.base_facts("1A851916")[1]["data"]
    assert "identity" not in profile                                                     # masked, but still not sent


def test_the_ai_master_switch_keeps_tara_away_from_the_model(monkeypatch):
    monkeypatch.setattr(kiosk_kai, "configured", lambda: True)
    monkeypatch.setattr(kiosk_kai, "call", lambda *a, **k: (_ for _ in ()).throw(AssertionError("called")))
    monkeypatch.setattr(tara_check.settings, "ai_data_processing_enabled", False)
    assert tara_check.base_facts("1A851916") == []


# ---------------------------------------------------------------- the briefing

def _rm_csp(db, make_user):
    rm = make_user(email="rm-panel@example.com", password="secret123", role=Role.RELATIONSHIP_MANAGER)
    csp = Csp(csp_id="1A851916", name="Panel CSP", rm_name="RM", rm_user_id=rm.id, mobile="9000000066",
              category="Gold CSP", branch_name="BR", status=CspStatus.ACTIVE)
    db.add(csp)
    db.commit()
    return csp


def test_the_briefing_carries_the_panel_and_a_score_that_includes_tara(client, db, make_user, login, monkeypatch):
    csp = _rm_csp(db, make_user)
    monkeypatch.setattr(kiosk_kai, "configured", lambda: True)
    monkeypatch.setattr(kiosk_kai, "call", lambda tool, **a: WEAK if tool == "tara.csp_performance" else WEAK_PROFILE)
    login("rm-panel@example.com", "secret123")

    body = client.get(f"/api/v1/csps/{csp.id}/pre-call").json()

    assert body["tara"]["available"] is True and body["tara"]["slab"]["next"]["name"] == "Slab-1"
    assert body["score"]["tara_included"] is True and body["score"]["business"] is not None
    assert any("TARA goals this month" in r or "Earnings for Sep-26" in r for r in body["score"]["reasons"])


def test_the_briefing_has_no_tara_part_when_tara_is_off(client, db, make_user, login, monkeypatch):
    csp = _rm_csp(db, make_user)
    monkeypatch.setattr(kiosk_kai.settings, "kiosk_kai_app_key", None)
    login("rm-panel@example.com", "secret123")

    body = client.get(f"/api/v1/csps/{csp.id}/pre-call").json()

    assert body["tara"] is None and body["score"]["tara_included"] is False


def test_the_briefing_still_loads_when_tara_does_not_answer(client, db, make_user, login, monkeypatch):
    csp = _rm_csp(db, make_user)
    monkeypatch.setattr(kiosk_kai, "configured", lambda: True)
    monkeypatch.setattr(kiosk_kai, "call", lambda tool, **a: None)
    login("rm-panel@example.com", "secret123")

    resp = client.get(f"/api/v1/csps/{csp.id}/pre-call")

    assert resp.status_code == 200
    assert resp.json()["tara"] == {"available": False} and resp.json()["score"]["tara_included"] is False
