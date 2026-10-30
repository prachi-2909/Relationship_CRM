"""The dashboards: the admin sees everything and can narrow it, an RM sees only their own CSPs and calls, a DC only
their own SBI officials and calls. Whatever filter a non-admin sends is ignored."""

from datetime import datetime, timedelta, timezone

from app.models.call_intelligence import CallSession, CallSessionStatus, Direction
from app.models.csp import Csp, CspStatus
from app.models.relationship import Relationship
from app.models.user import Role


def _csp(db, rm, code):
    c = Csp(csp_id=code, name=f"CSP {code}", rm_name=rm.name, rm_user_id=rm.id, mobile="9000000055",
            category="Gold CSP", branch_name="BR", status=CspStatus.ACTIVE)
    db.add(c)
    db.commit()
    return c


def _call(db, user, *, csp=None, official=None, days_ago=1, status=CallSessionStatus.REVIEW_REQUIRED):
    started = datetime.now(timezone.utc) - timedelta(days=days_ago)
    c = CallSession(
        dc_user_id=user.id, direction=Direction.OUTBOUND, phone_ref="9876543210",
        csp_id=csp.id if csp else None, official_id=official.id if official else None,
        started_at=started, ended_at=started + timedelta(seconds=60), duration_seconds=60,
        processing_status=status,
    )
    db.add(c)
    db.commit()
    return c


def _world(db, make_user, make_official):
    admin = make_user(email="adm-cmd@example.com", password="secret123", role=Role.ADMIN, name="Admin")
    rm1 = make_user(email="rm1-cmd@example.com", password="secret123", role=Role.RELATIONSHIP_MANAGER, name="RM One")
    rm2 = make_user(email="rm2-cmd@example.com", password="secret123", role=Role.RELATIONSHIP_MANAGER, name="RM Two")
    dc = make_user(email="dc-cmd@example.com", password="secret123", role=Role.DC, name="DC One")
    c1, c2, c3 = _csp(db, rm1, "C1"), _csp(db, rm1, "C2"), _csp(db, rm2, "C3")
    _call(db, rm1, csp=c1)
    _call(db, rm1, csp=c1, days_ago=2)
    _call(db, rm2, csp=c3)
    _call(db, rm1, csp=c2, status=CallSessionStatus.CANCELLED)          # never placed: not a call
    off = make_official(name="Officer One", level="BRANCH")
    db.add(Relationship(official_id=off.id, owner_id=dc.id, score=30))
    db.commit()
    _call(db, dc, official=off)
    return admin, rm1, rm2, dc


def _get(client, login, who, **params):
    login(who.email, "secret123")
    resp = client.get("/api/v1/dashboard/command", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_the_admin_sees_every_rm_dc_official_and_call(client, db, make_user, make_official, login):
    admin, *_ = _world(db, make_user, make_official)

    d = _get(client, login, admin)

    assert d["scope"]["can_filter"] is True
    assert {r["name"] for r in d["rms"]} == {"RM One", "RM Two"}
    assert [r["csps"] for r in d["rms"] if r["name"] == "RM One"] == [2]
    assert d["calls"]["total"] == 4                                      # 3 RM calls + 1 DC call, not the cancelled one
    assert d["csp"]["active"] == 3
    assert d["officials"]["with_relationship"] == 1 and d["officials"]["needs_attention"][0]["name"] == "Officer One"
    assert [x["name"] for x in d["dcs"]] == ["DC One"] and d["dcs"][0]["at_risk"] >= 0
    assert {f["name"] for f in d["filters"]["rms"]} == {"RM One", "RM Two"}


def test_the_admin_can_narrow_to_one_rm(client, db, make_user, make_official, login):
    admin, rm1, *_ = _world(db, make_user, make_official)

    d = _get(client, login, admin, rm_id=rm1.id)

    assert d["calls"]["total"] == 2 and d["csp"]["active"] == 2
    assert [r["name"] for r in d["rms"]] == ["RM One"]


def test_an_rm_sees_only_their_own_work_whatever_they_ask_for(client, db, make_user, make_official, login):
    _, rm1, rm2, _ = _world(db, make_user, make_official)

    d = _get(client, login, rm1, rm_id=rm2.id)                          # asking for someone else's view

    assert d["scope"]["can_filter"] is False and d["scope"]["rm"]["id"] == rm1.id
    assert d["calls"]["total"] == 2 and d["csp"]["active"] == 2
    assert [r["name"] for r in d["rms"]] == ["RM One"]
    assert d["officials"] is None and d["dcs"] is None and d["filters"] is None


def test_a_dc_sees_only_their_own_officials_and_calls(client, db, make_user, make_official, login):
    _, _, _, dc = _world(db, make_user, make_official)

    d = _get(client, login, dc)

    assert d["calls"]["total"] == 1 and d["csp"] is None and d["rms"] is None
    assert d["officials"]["with_relationship"] == 1


def test_the_old_overview_is_also_scoped_for_an_rm(client, db, make_user, make_official, login):
    _, rm1, *_ = _world(db, make_user, make_official)
    login(rm1.email, "secret123")

    body = client.get("/api/v1/dashboard/overview").json()

    assert "RM Two" not in str(body)
