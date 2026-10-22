"""CSP endpoints: RM-wise grouping and an RM's own list."""

from app.models.csp import Csp, CspStatus
from app.models.user import Role


def _rm(make_user, email: str, name: str):
    return make_user(email=email, name=name, role=Role.RELATIONSHIP_MANAGER)


def _csp(db, *, csp_id, name, rm_name, rm_user_id, mobile="9000000000", alt=None, status=CspStatus.ACTIVE):
    c = Csp(
        csp_id=csp_id, name=name, rm_name=rm_name, rm_user_id=rm_user_id,
        mobile=mobile, alternate_mobile=alt, category="Gold CSP",
        branch_name="BR", district="D", state="S", status=status,
    )
    db.add(c)
    db.commit()
    return c


def test_csps_by_rm_groups_active_only(client, db, make_user, login):
    rm_a = _rm(make_user, "rm-a@example.com", "Amuda")
    rm_v = _rm(make_user, "rm-v@example.com", "Vandana")
    _csp(db, csp_id="C1", name="Agent One", rm_name="Amuda", rm_user_id=rm_a.id, alt="9111111111")
    _csp(db, csp_id="C2", name="Agent Two", rm_name="Vandana", rm_user_id=rm_v.id)
    _csp(db, csp_id="C3", name="Gone", rm_name="Vandana", rm_user_id=rm_v.id, status=CspStatus.INACTIVE)

    make_user(email="admin-csp@example.com", role=Role.ADMIN)
    login("admin-csp@example.com", "password123")

    resp = client.get("/api/v1/csps/by-rm")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2  # the inactive CSP is excluded
    groups = {g["rm_name"]: g for g in body["groups"]}
    assert groups["Amuda"]["count"] == 1
    assert groups["Vandana"]["count"] == 1
    assert groups["Amuda"]["csps"][0]["alternate_mobile"] == "9111111111"


def test_my_csps_returns_only_the_logged_in_rms_csps(client, db, make_user, login):
    rm_a = _rm(make_user, "rm-mine-a@example.com", "Amuda")
    rm_v = _rm(make_user, "rm-mine-v@example.com", "Vandana")
    _csp(db, csp_id="M1", name="Mine", rm_name="Amuda", rm_user_id=rm_a.id)
    _csp(db, csp_id="M2", name="Theirs", rm_name="Vandana", rm_user_id=rm_v.id)

    login("rm-mine-a@example.com", "password123")
    resp = client.get("/api/v1/csps/mine")
    assert resp.status_code == 200
    rows = resp.json()
    assert [r["name"] for r in rows] == ["Mine"]


def _sheet_csv(data_rows: list[list[str]]) -> str:
    import csv
    import io

    fields = [
        "CSP ID", "CSP Name", "CSP Mobile number", "Alternative Mobile Number",
        "CSP Category", "Relationship Manager", "Terminal Status", "Branch Name",
        "District", "State", "Circle (LHO)",
    ]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([""] * len(fields))  # row 0: merged group labels (ignored)
    w.writerow(fields)              # row 1: field names
    for r in data_rows:
        w.writerow(r)
    return buf.getvalue()


def test_sync_upserts_active_and_deactivates_missing(db, make_user, monkeypatch):
    from app.services import csp_sync

    rm = _rm(make_user, "rm-sync@example.com", "Vandana")
    # Pre-existing CSPs: one that will stay active (number changes), one that vanishes from the sheet.
    _csp(db, csp_id="S1", name="Old Name", rm_name="Vandana", rm_user_id=rm.id, mobile="9000000001")
    _csp(db, csp_id="S2", name="Leaving", rm_name="Vandana", rm_user_id=rm.id, mobile="9000000002")

    csv_text = _sheet_csv([
        # S1 stays active with a new number + alt; a brand-new S3 appears; S2 is absent.
        ["S1", "New Name", "9111111111", "9222222222", "Gold CSP", "Vandana", "Active", "BR", "D", "Bihar", "Patna"],
        ["S3", "Fresh CSP", "9333333333", "", "Silver CSP", "Vandana", "Active", "BR2", "D2", "Bihar", "Patna"],
        ["S4", "Inactive one", "9444444444", "", "Basic CSP", "Vandana", "Inactive", "BR3", "D3", "Bihar", "Patna"],
    ])
    monkeypatch.setattr(csp_sync, "_fetch_csv", lambda: csv_text)

    summary = csp_sync.sync_csps_from_sheet(db)
    db.commit()

    assert summary["created"] == 1          # S3
    assert summary["updated"] == 1          # S1 (name + number changed)
    assert summary["deactivated"] == 1      # S2 (gone from sheet)
    assert summary["active_in_sheet"] == 2  # S1 + S3 (S4 is Inactive, not counted)

    from app.models.csp import Csp, CspStatus
    from sqlalchemy import select

    s1 = db.scalar(select(Csp).where(Csp.csp_id == "S1"))
    assert s1.name == "New Name" and s1.mobile == "9111111111" and s1.alternate_mobile == "9222222222"
    s2 = db.scalar(select(Csp).where(Csp.csp_id == "S2"))
    assert s2.status == CspStatus.INACTIVE
    assert db.scalar(select(Csp).where(Csp.csp_id == "S3")).rm_user_id == rm.id
