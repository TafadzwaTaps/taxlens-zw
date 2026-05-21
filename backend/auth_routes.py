"""
auth_routes.py — Authentication API routes for TaxLens Zimbabwe.
NEW FILE. Mounted in main.py under /api/auth prefix.

Routes:
  POST /api/auth/signup
  POST /api/auth/login
  GET  /api/auth/me
  PUT  /api/auth/me
  POST /api/auth/change-password
  POST /api/auth/forgot-password
  GET  /auth/login   (page)
  GET  /auth/signup  (page)
  GET  /auth/profile (page)
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from database import supabase_client
from auth_service import (
    hash_password, verify_password,
    create_access_token, get_current_user,
    get_user_by_email, get_user_by_id,
)
from schemas_auth import (
    SignupRequest, LoginRequest, TokenResponse,
    UserProfile, PasswordResetRequest, PasswordChangeRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
templates = Jinja2Templates(directory=str(FRONTEND_DIR / "templates"))


# ── Page routes ───────────────────────────────────────────────────────────────

@router.get("/auth/login", response_class=HTMLResponse, include_in_schema=False)
async def page_login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/auth/signup", response_class=HTMLResponse, include_in_schema=False)
async def page_signup(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})


@router.get("/auth/profile", response_class=HTMLResponse, include_in_schema=False)
async def page_profile(request: Request):
    return templates.TemplateResponse("profile.html", {"request": request})


# ── API: Signup ───────────────────────────────────────────────────────────────

@router.post("/api/auth/signup", response_model=TokenResponse, tags=["Auth"])
async def signup(body: SignupRequest):
    """
    Register a new user. Stores hashed password — never plaintext.
    Returns a JWT on success.
    """
    email = body.email.lower().strip()

    # Check duplicate
    existing = get_user_by_email(email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered.")

    user_id      = str(uuid.uuid4())
    hashed_pw    = hash_password(body.password)
    now          = datetime.now(timezone.utc).isoformat()

    row = {
        "id":           user_id,
        "email":        email,
        "full_name":    body.full_name,
        "password_hash": hashed_pw,
        "role":         body.role,
        "plan":         "free",
        "scans_used":   0,
        "created_at":   now,
    }

    try:
        supabase_client.table("tl_users").insert(row).execute()
    except Exception as exc:
        logger.error("Signup insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Registration failed. Please try again.")

    token = create_access_token(user_id, email, body.role, "free")
    return TokenResponse(
        access_token=token,
        user_id=user_id,
        email=email,
        full_name=body.full_name,
        role=body.role,
        plan="free",
    )


# ── API: Login ────────────────────────────────────────────────────────────────

@router.post("/api/auth/login", response_model=TokenResponse, tags=["Auth"])
async def login(body: LoginRequest):
    """Authenticate and return a JWT token."""
    email = body.email.lower().strip()
    user  = get_user_by_email(email)

    if not user or not verify_password(body.password, user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    token = create_access_token(
        user["id"], user["email"], user["role"], user["plan"]
    )
    return TokenResponse(
        access_token=token,
        user_id=user["id"],
        email=user["email"],
        full_name=user["full_name"],
        role=user["role"],
        plan=user["plan"],
    )


# ── API: Get current user ─────────────────────────────────────────────────────

@router.get("/api/auth/me", response_model=UserProfile, tags=["Auth"])
async def get_me(current_user: dict = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    user = get_user_by_id(current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    from auth_service import PLAN_LIMITS
    plan = user.get("plan", "free")

    return UserProfile(
        id=user["id"],
        email=user["email"],
        full_name=user["full_name"],
        role=user["role"],
        plan=plan,
        created_at=user.get("created_at"),
        scans_used=user.get("scans_used", 0),
        scans_limit=PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])["scans"],
    )


# ── API: Update profile ───────────────────────────────────────────────────────

@router.put("/api/auth/me", tags=["Auth"])
async def update_profile(
    body: dict,
    current_user: dict = Depends(get_current_user),
):
    """Update full_name only (email changes require re-verification)."""
    allowed = {k: v for k, v in body.items() if k in ("full_name",)}
    if not allowed:
        raise HTTPException(status_code=400, detail="No updatable fields provided.")
    try:
        supabase_client.table("tl_users").update(allowed).eq("id", current_user["sub"]).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Update failed: {exc}")
    return {"message": "Profile updated successfully."}


# ── API: Change password ──────────────────────────────────────────────────────

@router.post("/api/auth/change-password", tags=["Auth"])
async def change_password(
    body: PasswordChangeRequest,
    current_user: dict = Depends(get_current_user),
):
    user = get_user_by_id(current_user["sub"])
    if not user or not verify_password(body.old_password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    new_hash = hash_password(body.new_password)
    try:
        supabase_client.table("tl_users").update(
            {"password_hash": new_hash}
        ).eq("id", current_user["sub"]).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Password change failed: {exc}")
    return {"message": "Password changed successfully."}


# ── API: Forgot password (placeholder) ───────────────────────────────────────

@router.post("/api/auth/forgot-password", tags=["Auth"])
async def forgot_password(body: PasswordResetRequest):
    """
    Placeholder — in production, send a password-reset email.
    Returns 200 regardless to prevent email enumeration.
    """
    logger.info("Password reset requested for: %s", body.email)
    return {
        "message": (
            "If that email is registered, you will receive reset instructions. "
            "(Email sending not yet configured — contact support.)"
        )
    }
