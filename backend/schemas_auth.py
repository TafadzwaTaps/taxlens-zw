"""
schemas_auth.py — Auth, user, and subscription Pydantic models.
NEW FILE — does not touch existing schemas.py.
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Literal
from datetime import datetime


# ── Auth ──────────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="Min 8 characters")
    full_name: str = Field(..., description="Full display name")
    role: Literal["user", "accountant", "admin"] = "user"


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    full_name: str
    role: str
    plan: str


class UserProfile(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    plan: str
    created_at: Optional[datetime] = None
    scans_used: int = 0
    scans_limit: int = 5


class PasswordResetRequest(BaseModel):
    email: str


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8)
