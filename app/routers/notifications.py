from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from app.services.db import upsert_fcm_token

router = APIRouter(prefix="/notifications", tags=["Notifications"])

class TokenRequest(BaseModel):
    fcm_token: str
    user_id: Optional[str] = None      # pass null for anonymous users
    lottery_name: Optional[str] = None  # subscribe to one lottery, or None = all

@router.post("/register-token")
def register_token(body: TokenRequest):
    """Register or refresh an FCM token. Safe to call on every app launch."""
    upsert_fcm_token(body.fcm_token, body.user_id, body.lottery_name)
    return {"status": "registered"}