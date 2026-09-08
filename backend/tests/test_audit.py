from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.user import Role


def _actions(db):
    return [row.action for row in db.scalars(select(AuditLog).order_by(AuditLog.id))]


def test_login_writes_audit_row(client, db, make_user, login):
    make_user(email="ann@example.com", password="secret123")
    login("ann@example.com", "secret123")
    assert "auth.login" in _actions(db)


def test_user_create_and_update_write_audit_rows(client, db, make_user, login):
    make_user(email="admin@example.com", password="secret123", role=Role.ADMIN)
    login("admin@example.com", "secret123")

    created = client.post(
        "/api/v1/users",
        json={"name": "New", "email": "new@example.com", "password": "secret123"},
    )
    new_id = created.json()["id"]
    client.patch(f"/api/v1/users/{new_id}", json={"role": "approver_viewer"})

    rows = db.scalars(select(AuditLog).order_by(AuditLog.id)).all()
    actions = [r.action for r in rows]
    assert "user.create" in actions
    assert "user.update" in actions

    update_row = next(r for r in rows if r.action == "user.update")
    assert update_row.before["role"] == "relationship_manager"
    assert update_row.after["role"] == "approver_viewer"
    assert update_row.entity_id == str(new_id)
