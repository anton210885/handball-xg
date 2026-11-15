import pytest
from fastapi.testclient import TestClient

from app import auth
from app.main import app


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_PASSWORD", "geheim-123")
    monkeypatch.setenv("APP_SECRET", "test-secret")
    auth._fails.clear()
    return TestClient(app)


def test_without_password_everything_is_open(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    c = TestClient(app)
    assert c.get("/api/auth").json() == {"required": False, "logged_in": True}
    assert c.get("/api/version").status_code == 200


def test_login_required_and_cookie_grants_access(client):
    assert client.get("/api/strategies").status_code == 401
    assert client.get("/api/auth").json() == {"required": True, "logged_in": False}
    assert client.post("/api/login", json={"password": "falsch"}).status_code == 401
    r = client.post("/api/login", json={"password": "geheim-123"})
    assert r.status_code == 200 and auth.COOKIE in r.cookies
    assert client.get("/api/auth").json()["logged_in"] is True
    assert client.get("/api/strategies").status_code == 200
    client.post("/api/logout")
    client.cookies.clear()
    assert client.get("/api/strategies").status_code == 401


def test_tokens_expire_and_change_with_password(client, monkeypatch):
    t = auth.make_token(now=1000)
    assert auth.valid_token(t, now=1001)
    assert not auth.valid_token(t, now=1000 + auth.MAX_AGE + 1)
    assert not auth.valid_token(t.split(".")[0] + ".abc", now=1001)
    monkeypatch.setenv("APP_PASSWORD", "neu")
    assert not auth.valid_token(t, now=1001)


def test_too_many_failures_block(client):
    for _ in range(auth.MAX_FAILS):
        client.post("/api/login", json={"password": "x"})
    assert client.post("/api/login", json={"password": "geheim-123"}).status_code == 429
