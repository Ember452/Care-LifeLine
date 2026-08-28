from __future__ import annotations

from fastapi import HTTPException
from fastapi.testclient import TestClient

from care_lifeline.api.app import app
from care_lifeline.api.security import (
    create_access_token,
    decode_access_token,
    get_current_user,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    stored = hash_password("s3cret")
    assert verify_password("s3cret", stored)
    assert not verify_password("wrong", stored)
    assert stored != hash_password("s3cret")


def test_token_roundtrip_carries_subject() -> None:
    token = create_access_token("user:7", expires_minutes=5)
    payload = decode_access_token(token)
    assert payload["sub"] == "user:7"


def test_decode_rejects_garbage() -> None:
    import jwt

    bogus = jwt.encode({"sub": "user:1"}, "wrong-secret", algorithm="HS256")
    try:
        decode_access_token(bogus)
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("expected 401")


def test_get_current_user_parses_bearer() -> None:
    token = create_access_token("user:42", expires_minutes=5)
    user = get_current_user(token)
    assert user.user_id == 42


def test_login_accepts_demo_credentials(tmp_path, monkeypatch) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path.as_posix()}/auth.db"
    monkeypatch.setenv("CARE_DATABASE_URL", url)
    from care_lifeline.config import get_settings
    from care_lifeline.db.engine import reset_state_for_testing

    get_settings.cache_clear()
    reset_state_for_testing()
    with TestClient(app) as client:
        resp = client.post("/v1/auth/login", data={"username": "demo", "password": "demo123"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["username"] == "demo"

        bad = client.post("/v1/auth/login", data={"username": "demo", "password": "nope"})
        assert bad.status_code == 401
