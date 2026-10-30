"""TARA's figures for one CSP, laid out for an RM, and the two score signals read from them.

Pure functions over what `tara.csp_performance` and `tara.csp_profile` return (the real shapes, seen on the live
server). Nothing here calls the network and nothing uses AI: every number is copied from TARA as it is, with the
month and the as_of it belongs to, so an RM never reads a figure the CRM invented. Anything TARA leaves out, or
sets to 0 because "targets are not set there", is shown as missing, not as 0.

Every key is read defensively: TARA adds and drops fields over time, and a missing one must never break a page.
"""

from __future__ import annotations

from datetime import date, datetime

CORE_SCHEMES = ("pmjdy", "pmjjby", "pmsby", "apy")     # the four that decide the DFS slab
SCHEME_NAMES = {"pmjdy": "PMJDY", "pmjjby": "PMJJBY", "pmsby": "PMSBY", "apy": "APY"}
SLAB_BASIS = "from_sbi_daily_sum"                       # SBI's daily data: the freshest of TARA's three sources
MAX_LEVERS = 4
MAX_CAVEATS = 6


def _d(value) -> dict:
    return value if isinstance(value, dict) else {}


def _l(value) -> list:
    return value if isinstance(value, list) else []


def _num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _positive(value):
    n = _num(value)
    return n if n and n > 0 else None


def _achieved(product: dict):
    a = _d(product.get("achieved"))
    for key in ("sbi_daily_sum", "sbi_monthly"):
        if _num(a.get(key)) is not None:
            return a[key], key
    return None, None


def _slab(perf: dict) -> dict | None:
    dfs = _d(perf.get("dfs_slab"))
    if not dfs:
        return None
    basis = _d(dfs.get(SLAB_BASIS))
    nxt = _d(basis.get("next"))
    sheet = _d(dfs.get("calling_sheet"))
    return {
        "rule": dfs.get("rule"),
        "reached": _d(basis.get("reached")).get("name") if isinstance(basis.get("reached"), dict) else basis.get("reached"),
        "reached_in_calling_sheet": sheet.get("reached_label"),
        "target_in_calling_sheet": sheet.get("target_label"),
        "basis": "SBI daily data",
        "next": {
            "name": nxt.get("name"),
            "incentive_inr": nxt.get("incentive_inr"),
            "already": nxt.get("already"),
            "schemes": [
                {"scheme": SCHEME_NAMES.get(s.get("scheme"), str(s.get("scheme") or "").upper()),
                 "have": s.get("have"), "threshold": s.get("threshold"), "more": s.get("more")}
                for s in _l(nxt.get("schemes")) if isinstance(s, dict)
            ],
            "closest_three": [SCHEME_NAMES.get(p, str(p).upper()) for p in _l(nxt.get("pick"))],
            "extra_total": nxt.get("extra_total"),
        } if nxt else None,
    }


def _products(perf: dict) -> list[dict]:
    products = _d(perf.get("products"))
    goals = {g.get("product"): g for g in _l(perf.get("tara_goals")) if isinstance(g, dict)}
    rows = []
    for code in CORE_SCHEMES:
        p = _d(products.get(code))
        goal = _d(goals.get(code))
        achieved, basis = _achieved(p)
        sbi_target = _positive(_d(p.get("target")).get("sbi"))
        rows.append({
            "code": code,
            "name": SCHEME_NAMES[code],
            "achieved": achieved,
            "achieved_basis": basis,
            "sbi_target": sbi_target,                      # None when SBI has no target set (it sends 0)
            "tara_goal": _positive(goal.get("target")),
            "agent_target": _positive(goal.get("agent_target")),
            "progress": goal.get("progress"),
            "progress_pct": goal.get("progress_pct"),
            "pace_status": goal.get("pace_status"),
        })
    return rows


def _earnings(perf: dict) -> dict | None:
    growth = _d(perf.get("growth"))
    com = _d(growth.get("commission_inr"))
    posted = _d(_d(perf.get("commission")).get("latest_posted_month"))
    if not com and not posted:
        return None
    return {
        "month": com.get("month"),
        "value_inr": com.get("value"),
        "usual_inr": com.get("usual"),
        "growth_pct": com.get("growth_pct"),
        "status": com.get("status"),
        "rank_in_district": com.get("rank_in_district"),
        "of_in_district": com.get("of"),
        "latest_posted_commission": {"label": posted.get("label"), "inr": posted.get("commission_inr")} if posted else None,
        "month_target_inr": _positive(_d(perf.get("commission")).get("target_inr")),
    }


def build_panel(perf_body: dict | None, profile_body: dict | None) -> dict:
    """The panel an RM reads before a call. {"available": False} when TARA gave nothing for the CSP."""
    perf = _d(_d(perf_body).get("data"))
    prof = _d(_d(profile_body).get("data"))
    if not perf and not prof:
        return {"available": False}

    tx = _d(perf.get("transactions"))
    count = _d(tx.get("count"))
    gtv = _d(tx.get("gtv_inr"))
    month = _d(perf.get("calling_sheet_month"))
    terminals = _d(prof.get("terminals"))
    call_list = _d(perf.get("rm_call_list"))
    balance = _d(perf.get("balance"))
    levers = [i for i in _l(_d(perf.get("levers")).get("items")) if isinstance(i, dict)]

    caveats: list[str] = []
    for body in (perf_body, profile_body):
        for c in _l(_d(body).get("caveats")):
            if isinstance(c, str) and c not in caveats:
                caveats.append(c)

    return {
        "available": True,
        "source": "TARA, through Kiosk KAI",
        "as_of": _d(perf_body).get("as_of") or _d(profile_body).get("as_of"),
        "month": _d(perf.get("period")).get("month"),
        "slab": _slab(perf),
        "products": _products(perf),
        "transactions": {
            "count": count.get("sbi_daily_sum") if _num(count.get("sbi_daily_sum")) is not None else count.get("sbi_monthly"),
            "gtv_inr": gtv.get("sbi_daily_sum") if _num(gtv.get("sbi_daily_sum")) is not None else gtv.get("sbi_monthly"),
            "days_with_data": tx.get("days_with_data"),
            "last_day_with_data": tx.get("last_day_with_data"),
        } if tx else None,
        "earnings": _earnings(perf),
        "activity": {
            "login_days_this_month": month.get("login_days"),
            "days_without_activity": month.get("inactivity_days"),
            "last_login_date": prof.get("last_login_date"),
            "terminal_status": terminals.get("terminal_status"),
            "matm_status": terminals.get("matm_status"),
            "passbook_printer_status": terminals.get("passbook_printer_status"),
            "gps_dongle_status": terminals.get("gps_dongle_status"),
        } if (month or prof) else None,
        "opportunities": [
            {"lever": i.get("lever"), "monthly_inr": i.get("monthly_inr"), "detail": i.get("detail")}
            for i in levers[:MAX_LEVERS]
        ],
        "call_priority": {
            "priority": call_list.get("priority"),
            "rank": call_list.get("rank"),
            "daily_target_txns": call_list.get("daily_target_txns"),
            "daily_target_inr": call_list.get("daily_target_inr"),
        } if call_list else None,
        "balance": {
            "total_accounts": balance.get("total_accounts"),
            "deposit_for_higher_slab_inr": balance.get("deposit_for_higher_slab_inr"),
        } if balance else None,
        "caveats": caveats[:MAX_CAVEATS],
    }


# ---------------------------------------------------------------- the two score signals

def _as_date(value) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def performance_signal(perf: dict | None, today: date) -> tuple[float | None, str]:
    """How the CSP stands on the four core schemes against TARA's goals, allowing for how much of the month has
    gone: 100 means on or ahead of pace for every scheme, 0 means nothing done with the month nearly over."""
    scores: list[float] = []
    parts: list[str] = []
    elapsed_pct = None
    for goal in _l(_d(perf).get("tara_goals")):
        if not isinstance(goal, dict) or goal.get("product") not in CORE_SCHEMES:
            continue
        target, progress = _positive(goal.get("target")), _num(goal.get("progress"))
        start, end = _as_date(goal.get("period_start")), _as_date(goal.get("period_end"))
        if target is None or progress is None or start is None or end is None or end < start:
            continue
        span = (end - start).days + 1
        elapsed = min(1.0, max(0.0, ((today - start).days + 1) / span))
        elapsed_pct = round(elapsed * 100)
        attained = progress / target
        scores.append(100.0 if elapsed <= 0 else min(100.0, attained / elapsed * 100.0))
        parts.append(f"{SCHEME_NAMES[goal['product']]} {progress:g} of {target:g}")
    if not scores:
        return None, ""
    value = round(sum(scores) / len(scores), 1)
    return value, f"TARA goals this month: {', '.join(parts)} ({elapsed_pct}% of the month gone)."


def _trend_value(entry: dict) -> float | None:
    growth = _num(entry.get("growth_pct"))
    if growth is not None:
        return max(0.0, min(100.0, 50.0 + growth * 2.0))        # 0% = 50, +25% or more = 100, -25% or less = 0
    status = entry.get("status")
    if status in ("grow", "stable", "degrow") and ((_num(entry.get("usual")) or 0) > 0 or (_num(entry.get("value")) or 0) > 0):
        return {"grow": 75.0, "stable": 50.0, "degrow": 25.0}[status]
    return None


def trend_signal(perf: dict | None) -> tuple[float | None, str]:
    """Earnings and transactions against the CSP's own usual, from TARA's growth figures."""
    growth = _d(_d(perf).get("growth"))
    values: list[float] = []
    note = ""
    for key in ("commission_inr", "transactions"):
        entry = _d(growth.get(key))
        v = _trend_value(entry)
        if v is not None:
            values.append(v)
        if key == "commission_inr" and entry.get("month") is not None and _num(entry.get("value")) is not None:
            usual = entry.get("usual")
            pct = _num(entry.get("growth_pct"))
            tail = f" ({pct:+.0f}%)" if pct is not None else ""
            usual_text = f" against a usual {usual:,.0f}" if _num(usual) is not None else ""
            note = f"Earnings for {entry['month']}: Rs {entry['value']:,.0f}{usual_text}{tail}."
    if not values:
        return None, ""
    return round(sum(values) / len(values), 1), note
