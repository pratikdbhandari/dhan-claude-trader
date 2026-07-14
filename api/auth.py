"""Supabase JWT verification. Every route except /health requires a valid bearer
token signed with the project's JWT secret (HS256, audience 'authenticated'),
verified locally — no per-request network call to Supabase."""
from __future__ import annotations
import os

import jwt
from fastapi import Header, HTTPException


class AuthError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=401, detail=detail)


def decode_token(token: str, secret: str) -> str:
    """Verify signature/expiry/audience; return the Supabase user id (sub claim)."""
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"], audience="authenticated")
    except jwt.ExpiredSignatureError:
        raise AuthError("token expired")
    except jwt.InvalidTokenError:
        raise AuthError("invalid token")
    return payload["sub"]


def require_user(authorization: str = Header(default="")) -> str:
    """FastAPI dependency: parse 'Bearer <jwt>', verify it, return the user id."""
    if not authorization.startswith("Bearer "):
        raise AuthError("missing bearer token")
    token = authorization.removeprefix("Bearer ")
    secret = os.environ.get("SUPABASE_JWT_SECRET", "")
    if not secret:
        raise AuthError("server misconfigured: SUPABASE_JWT_SECRET not set")
    return decode_token(token, secret)
