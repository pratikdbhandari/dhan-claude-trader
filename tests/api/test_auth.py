import time
import jwt
import pytest
from fastapi import HTTPException

from api.auth import decode_token, require_user

SECRET = "test-secret"


def _token(sub="user-1", exp_offset=3600, secret=SECRET, aud="authenticated"):
    payload = {"sub": sub, "aud": aud, "exp": time.time() + exp_offset}
    return jwt.encode(payload, secret, algorithm="HS256")


def test_decode_token_returns_sub_for_valid_token():
    token = _token(sub="user-42")
    assert decode_token(token, SECRET) == "user-42"


def test_decode_token_rejects_expired_token():
    token = _token(exp_offset=-10)
    with pytest.raises(HTTPException) as exc_info:
        decode_token(token, SECRET)
    assert exc_info.value.status_code == 401


def test_decode_token_rejects_wrong_signature():
    token = _token(secret="wrong-secret")
    with pytest.raises(HTTPException) as exc_info:
        decode_token(token, SECRET)
    assert exc_info.value.status_code == 401


def test_require_user_rejects_missing_bearer(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    with pytest.raises(HTTPException) as exc_info:
        require_user(authorization="")
    assert exc_info.value.status_code == 401


def test_require_user_accepts_valid_bearer(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    token = _token(sub="user-7")
    assert require_user(authorization=f"Bearer {token}") == "user-7"


def test_require_user_rejects_when_secret_not_configured(monkeypatch):
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    token = _token()
    with pytest.raises(HTTPException) as exc_info:
        require_user(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401
