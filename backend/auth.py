"""Supabase-backed authentication helpers for the private family API."""

import os
import secrets
from typing import Annotated

import httpx
from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from database import get_db
from models import FamilyAccount


class SetupRequest(BaseModel):
    setup_code: str = Field(min_length=12, max_length=256)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


def _supabase_url() -> str:
    value = os.getenv("SUPABASE_URL", "").rstrip("/")
    if not value:
        raise HTTPException(status_code=503, detail="Authentication is not configured")
    return value


def _publishable_key() -> str:
    value = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
    if not value:
        raise HTTPException(status_code=503, detail="Authentication is not configured")
    return value


def require_family_user(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> str:
    """Verify a Supabase token and ensure it is the approved family account."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required")

    token = authorization.split(" ", 1)[1].strip()
    try:
        response = httpx.get(
            f"{_supabase_url()}/auth/v1/user",
            headers={"Authorization": f"Bearer {token}", "apikey": _publishable_key()},
            timeout=8.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Authentication service unavailable") from exc

    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    user_id = response.json().get("id")
    if not user_id or not db.query(FamilyAccount).filter(FamilyAccount.user_id == user_id).first():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is not approved")
    return user_id


def create_first_family_account(payload: SetupRequest, db: Session) -> dict:
    if db.query(FamilyAccount).first():
        raise HTTPException(status_code=409, detail="Family setup has already been completed")
    expected = os.getenv("FAMILY_SETUP_CODE", "")
    secret_key = os.getenv("SUPABASE_SECRET_KEY", "")
    if not expected or not secret_key:
        raise HTTPException(status_code=503, detail="Initial setup is not configured")
    if not secrets.compare_digest(expected, payload.setup_code):
        raise HTTPException(status_code=401, detail="Invalid setup code")

    try:
        response = httpx.post(
            f"{_supabase_url()}/auth/v1/admin/users",
            headers={"Authorization": f"Bearer {secret_key}", "apikey": secret_key},
            json={"email": payload.email, "password": payload.password, "email_confirm": True},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Unable to create the family account") from exc
    if response.status_code not in (200, 201):
        detail = response.json().get("message", "Unable to create the family account")
        raise HTTPException(status_code=400, detail=detail)

    payload_json = response.json()
    user_id = payload_json.get("id") or payload_json.get("user", {}).get("id")
    if not user_id:
        raise HTTPException(status_code=502, detail="Authentication service returned no user identifier")
    db.add(FamilyAccount(user_id=user_id))
    db.commit()
    return {"user_id": user_id, "email": payload.email}


def get_owned_child(db: Session, child_id: int, user_id: str):
    """Return a child only when it belongs to the authenticated family user."""
    from models import Child

    return db.query(Child).filter(Child.id == child_id, Child.owner_id == user_id).first()
