"""Firebase Cloud Messaging push notifications (HTTP v1 API). Failures are logged
and swallowed — a missed push must never affect the trading pipeline."""
from __future__ import annotations
import logging
import os

import httpx
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account

log = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]
_credentials = None


def _default_get_access_token() -> str:
    global _credentials
    if _credentials is None:
        key_path = os.environ["FCM_SERVICE_ACCOUNT_JSON_PATH"]
        _credentials = service_account.Credentials.from_service_account_file(
            key_path, scopes=_SCOPES)
    if not _credentials.valid:
        _credentials.refresh(GoogleAuthRequest())
    return _credentials.token


def send_push(token: str, title: str, body: str, data: dict | None = None, *,
             get_access_token=_default_get_access_token, post=httpx.post) -> bool:
    """Send one FCM message. Returns True on success, False on any failure (logged),
    never raises — callers must be able to fire-and-forget this."""
    try:
        project_id = os.environ["FCM_PROJECT_ID"]
        access_token = get_access_token()
        message = {"message": {
            "token": token,
            "notification": {"title": title, "body": body},
            "data": {k: str(v) for k, v in (data or {}).items()},
        }}
        resp = post(
            f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send",
            json=message, headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
        resp.raise_for_status()
        return True
    except Exception:                                      # noqa: BLE001
        log.exception("FCM push failed")
        return False
