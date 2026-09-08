def test_health_ok(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] is True


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["api"] == "/api/v1"
