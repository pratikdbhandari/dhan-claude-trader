"""POST /push/register — the phone tells us which FCM token belongs to the
logged-in device, stored in Supabase's push_tokens table."""
from __future__ import annotations
from fastapi import APIRouter, Depends

from api import supabase_client
from api.auth import require_user
from api.schemas import PushTokenIn

router = APIRouter(prefix="/push", tags=["push"])


@router.post("/register")
def register(body: PushTokenIn, user_id: str = Depends(require_user)):
    supabase_client.register_push_token(user_id, body.token)
    return {"ok": True}
