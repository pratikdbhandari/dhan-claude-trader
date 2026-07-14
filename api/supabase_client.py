"""Thin wrapper over Supabase's PostgREST API for the push_tokens table. No ORM —
one table, two operations. Trading data is NOT stored in Supabase; the SQLite
journal remains the single source of truth (see data/journal.py)."""
from __future__ import annotations
import os

import httpx


def _headers() -> dict:
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {"apikey": key, "Authorization": f"Bearer {key}",
           "Content-Type": "application/json"}


def register_push_token(user_id: str, token: str, *, post=httpx.post) -> None:
    """Upsert one row keyed by user_id — one device token per logged-in user."""
    url = os.environ["SUPABASE_URL"] + "/rest/v1/push_tokens"
    resp = post(url, json={"user_id": user_id, "token": token},
               headers={**_headers(), "Prefer": "resolution=merge-duplicates"},
               timeout=10)
    resp.raise_for_status()


def list_push_tokens(*, get=httpx.get) -> list[str]:
    """Return every registered device token."""
    url = os.environ["SUPABASE_URL"] + "/rest/v1/push_tokens?select=token"
    resp = get(url, headers=_headers(), timeout=10)
    resp.raise_for_status()
    return [row["token"] for row in resp.json()]
