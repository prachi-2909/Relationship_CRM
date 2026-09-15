from app.models.user import Role


def _admin(make_user, login):
    make_user(email="admin@example.com", password="secret123", role=Role.ADMIN)
    login("admin@example.com", "secret123")


CSV = """Name,Level,Designation,Email,Location
Anil Verma,DGM,Deputy General Manager,anil.verma@partner.example,Patna
Anil Verma,DGM,Deputy General Manager,anil.verma@partner.example,Patna
Sunita Rao,AGM,Assistant General Manager,,Bhagalpur
,,,x@x.com,Nowhere
"""


def test_stage_dedupes_and_flags_bad_rows(client, make_user, login):
    _admin(make_user, login)
    resp = client.post(
        "/api/v1/imports", json={"filename": "batch.csv", "csv_text": CSV}
    )
    assert resp.status_code == 201
    summary = resp.json()
    assert summary["row_count"] == 4
    assert summary["accepted_count"] == 2  # Anil (first) + Sunita
    assert summary["rejected_count"] == 2  # duplicate Anil + nameless row
    assert summary["status"] == "pending"

    preview = client.get(f"/api/v1/imports/{summary['id']}/preview").json()
    by_row = {r["row_number"]: r for r in preview["rows"]}
    assert by_row[1]["action"] == "create"
    assert by_row[2]["action"] == "skip"
    assert "duplicate" in by_row[2]["error"]
    assert by_row[4]["action"] == "skip"
    assert by_row[4]["error"] == "missing name"
    # a worked sample for the CREATE row
    assert any(s["action"] == "create" for s in preview["samples"])


def test_commit_creates_and_merges(client, make_user, login):
    _admin(make_user, login)
    # an existing official to merge onto (matched by email)
    client.post(
        "/api/v1/officials",
        json={"name": "Existing Person", "email": "exist@partner.example"},
    )

    csv = (
        "Name,Email,Designation,Level\n"
        "Existing Person,exist@partner.example,Chief Manager,CM\n"
        "Brand New,new@partner.example,Manager,Scale II\n"
    )
    di = client.post(
        "/api/v1/imports", json={"filename": "m.csv", "csv_text": csv}
    ).json()

    preview = client.get(f"/api/v1/imports/{di['id']}/preview").json()
    actions = {r["row_number"]: r["action"] for r in preview["rows"]}
    assert actions[1] == "merge"
    assert actions[2] == "create"

    committed = client.post(f"/api/v1/imports/{di['id']}/commit")
    assert committed.status_code == 200
    assert committed.json()["status"] == "committed"

    # merge filled the empty designation on the existing official
    found = client.get("/api/v1/officials", params={"q": "Existing Person"}).json()
    assert found["items"][0]["designation"] == "Chief Manager"
    # new official exists
    assert client.get("/api/v1/officials", params={"q": "Brand New"}).json()["total"] == 1

    # cannot commit twice
    assert client.post(f"/api/v1/imports/{di['id']}/commit").status_code == 409


def test_name_only_match_is_low_confidence(client, make_user, login):
    _admin(make_user, login)
    client.post("/api/v1/officials", json={"name": "Common Name", "level": "AGM"})

    csv = "Name,Level\nCommon Name,DGM\n"
    di = client.post(
        "/api/v1/imports", json={"filename": "n.csv", "csv_text": csv}
    ).json()
    preview = client.get(f"/api/v1/imports/{di['id']}/preview").json()
    row = preview["rows"][0]
    assert row["action"] == "merge"
    assert row["confidence"] == 55
    assert "review before commit" in row["error"]


def test_relationship_manager_cannot_commit(client, make_user, login):
    make_user(email="admin@example.com", password="secret123", role=Role.ADMIN)
    make_user(email="rm@example.com", password="secret123", role=Role.RELATIONSHIP_MANAGER)

    login("rm@example.com", "secret123")
    di = client.post(
        "/api/v1/imports",
        json={"filename": "x.csv", "csv_text": "Name\nSomeone\n"},
    ).json()
    assert client.post(f"/api/v1/imports/{di['id']}/commit").status_code == 403

    login("admin@example.com", "secret123")
    assert client.post(f"/api/v1/imports/{di['id']}/commit").status_code == 200


def test_upload_csv_stages_rows(client, make_user, login):
    _admin(make_user, login)
    resp = client.post(
        "/api/v1/imports/upload",
        files={"file": ("team.csv", CSV.encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["filename"] == "team.csv"
    assert body["row_count"] == 4
    assert body["accepted_count"] == 2


def test_upload_xlsx_stages_rows(client, make_user, login):
    from io import BytesIO

    from openpyxl import Workbook

    _admin(make_user, login)
    wb = Workbook()
    ws = wb.active
    ws.append(["Name", "Level", "Designation", "Email"])
    ws.append(["Meena Pillai", "AGM", "Assistant General Manager", "meena@partner.example"])
    buf = BytesIO()
    wb.save(buf)

    resp = client.post(
        "/api/v1/imports/upload",
        files={
            "file": (
                "team.xlsx",
                buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["row_count"] == 1
    assert body["accepted_count"] == 1

    preview = client.get(f"/api/v1/imports/{body['id']}/preview").json()
    assert preview["rows"][0]["normalized"]["name"] == "Meena Pillai"


def test_upload_rejects_unsupported_extension(client, make_user, login):
    _admin(make_user, login)
    resp = client.post(
        "/api/v1/imports/upload",
        files={"file": ("team.txt", b"Name\nSomeone\n", "text/plain")},
    )
    assert resp.status_code == 415


def test_upload_requires_editor_role(client, make_user, login):
    make_user(email="viewer@example.com", password="secret123", role=Role.APPROVER_VIEWER)
    login("viewer@example.com", "secret123")
    resp = client.post(
        "/api/v1/imports/upload",
        files={"file": ("x.csv", b"Name\nSomeone\n", "text/csv")},
    )
    assert resp.status_code == 403


def test_phone_column_is_recognised_and_committed(client, make_user, login):
    _admin(make_user, login)
    csv = (
        "Name,Phone Number,Email\n"
        "Ravi Menon,98765 43210,ravi.menon@partner.example\n"
    )
    staged = client.post(
        "/api/v1/imports", json={"filename": "phones.csv", "csv_text": csv}
    ).json()

    preview = client.get(f"/api/v1/imports/{staged['id']}/preview").json()
    assert preview["rows"][0]["normalized"]["phone"] == "98765 43210"
    assert preview["samples"][0]["writes"]["phone"] == "98765 43210"

    client.post(f"/api/v1/imports/{staged['id']}/commit")
    officials = client.get("/api/v1/officials", params={"q": "Ravi Menon"}).json()
    assert officials["items"][0]["phone"] == "98765 43210"
