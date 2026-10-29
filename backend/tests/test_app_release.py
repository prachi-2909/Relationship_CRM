from app.models.user import Role


def _as(make_user, login, role: Role, email: str):
    make_user(email=email, password="secret123", role=role)
    login(email, "secret123")


def test_version_requires_auth(client):
    assert client.get("/api/v1/app/version").status_code == 401


def test_version_returns_configured_values(client, make_user, login):
    _as(make_user, login, Role.DC, "dc-rel@example.com")
    resp = client.get("/api/v1/app/version")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version_code"] >= 1
    assert body["download_url"].endswith("/app/download")


def test_download_404_when_nothing_published(client):
    resp = client.get("/api/v1/app/download")
    assert resp.status_code == 404


# ---- publishing a release (admin only) and the phones being offered it

import pytest

from app.services import app_release as release_svc

_APK = b"PK" + b"fake apk contents" * 50


@pytest.fixture
def release_dir(tmp_path, monkeypatch):
    # An absolute path wins over the database folder, so tests never write into the repo.
    monkeypatch.setattr(release_svc.settings, "android_release_dir", str(tmp_path / "releases"))
    return tmp_path / "releases"


def _publish(client, code, name="1.5", payload=_APK):
    return client.post(
        "/api/v1/app/release",
        files={"apk": ("app.apk", payload, "application/octet-stream")},
        data={"version_code": str(code), "version_name": name},
    )


def test_an_admin_can_publish_and_phones_are_then_offered_it(client, make_user, login, release_dir):
    _as(make_user, login, Role.ADMIN, "admin-rel@example.com")
    resp = _publish(client, 5, "1.5")
    assert resp.status_code == 201 and resp.json()["version_code"] == 5

    seen = client.get("/api/v1/app/version").json()                 # no env edit, no restart
    assert (seen["version_code"], seen["version_name"]) == (5, "1.5")
    download = client.get("/api/v1/app/download")
    assert download.status_code == 200 and download.content == _APK


def test_only_an_admin_can_publish(client, make_user, login, release_dir):
    _as(make_user, login, Role.DC, "dc-pub@example.com")
    assert _publish(client, 9).status_code == 403
    assert client.get("/api/v1/app/download").status_code == 404     # nothing was stored


def test_a_release_can_only_go_up(client, make_user, login, release_dir):
    _as(make_user, login, Role.ADMIN, "admin-up@example.com")
    assert _publish(client, 7, "1.7").status_code == 201
    assert _publish(client, 7, "1.7b").status_code == 409            # same code
    assert _publish(client, 3, "0.3").status_code == 409             # lower code
    assert client.get("/api/v1/app/version").json()["version_code"] == 7


def test_a_file_that_is_not_an_apk_is_refused(client, make_user, login, release_dir):
    _as(make_user, login, Role.ADMIN, "admin-bad@example.com")
    assert _publish(client, 4, payload=b"<html>not an apk</html>").status_code == 422
    assert _publish(client, 4, payload=b"").status_code == 422
    assert client.get("/api/v1/app/download").status_code == 404


def test_version_falls_back_to_the_settings_when_nothing_was_published(client, make_user, login, release_dir):
    _as(make_user, login, Role.DC, "dc-fallback@example.com")
    body = client.get("/api/v1/app/version").json()
    assert body["version_code"] == release_svc.settings.android_latest_version_code
