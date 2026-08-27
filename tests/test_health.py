from fastapi.testclient import TestClient

from controlplane.main import app

client = TestClient(app)


def test_liveness():
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "alive"}


def test_readiness():
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["configuration"] == "ok"
