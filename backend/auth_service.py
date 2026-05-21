"""
auth_service.py — Authentication helpers for TaxLens Zimbabwe.
NEW FILE. Does not modify existing files.

Provides:
  - password hashing / verification (bcrypt via passlib)
  - JWT creation / decoding
  - current_user dependency for protected routes
  - subscription plan helpers
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext

from config import settings
from database import supabase_client

logger = logging.getLogger(__name__)

# ── Crypto setup ──────────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)

# JWT config — pulled from settings / env
JWT_SECRET    = getattr(settings, "jwt_secret", "taxlens-dev-secret-change-in-prod")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24 * 7   # 7-day tokens


# ── Plan definitions ──────────────────────────────────────────────────────────
PLAN_LIMITS = {
    "free":        {"scans": 5,         "pdf": False, "history": False, "employees": 3},
    "pro":         {"scans": 999,       "pdf": True,  "history": True,  "employees": 50},
    "accountant":  {"scans": 9999,      "pdf": True,  "history": True,  "employees": 9999},
}


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(user_id: str, email: str, role: str, plan: str) -> str:
    """Create a signed JWT with a 7-day expiry."""
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {
        "sub":   user_id,
        "email": email,
        "role":  role,
        "plan":  plan,
        "exp":   expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises HTTPException on failure."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token. Please log in again.",
        ) from exc


# ── FastAPI dependency ────────────────────────────────────────────────────────

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    """
    FastAPI dependency — inject into any route that requires authentication.
    Returns the decoded JWT payload dict.
    Guest / unauthenticated requests are rejected with 401.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
        )
    return decode_token(credentials.credentials)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[dict]:
    """
    Like get_current_user but returns None instead of raising — allows
    guest access alongside authenticated access (preserves guest mode).
    """
    if not credentials:
        return None
    try:
        return decode_token(credentials.credentials)
    except HTTPException:
        return None


def require_role(*roles: str):
    """Factory for role-based route dependencies."""
    async def check(user: dict = Depends(get_current_user)):
        if user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of these roles: {', '.join(roles)}",
            )
        return user
    return check


# ── Supabase user helpers ─────────────────────────────────────────────────────

def get_user_by_email(email: str) -> Optional[dict]:
    """Fetch a user row from Supabase by email. Returns None if not found."""
    try:
        resp = (
            supabase_client.table("tl_users")
            .select("*")
            .eq("email", email.lower().strip())
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None
    except Exception as exc:
        logger.warning("get_user_by_email failed: %s", exc)
        return None


def get_user_by_id(user_id: str) -> Optional[dict]:
    """Fetch a user row from Supabase by primary key."""
    try:
        resp = (
            supabase_client.table("tl_users")
            .select("*")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None
    except Exception as exc:
        logger.warning("get_user_by_id failed: %s", exc)
        return None


def increment_scan_count(user_id: str) -> bool:
    """Increment scans_used for a user. Returns False if limit reached."""
    user = get_user_by_id(user_id)
    if not user:
        return True   # guest — always allow
    plan   = user.get("plan", "free")
    used   = user.get("scans_used", 0)
    limit  = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])["scans"]
    if used >= limit:
        return False
    try:
        supabase_client.table("tl_users").update(
            {"scans_used": used + 1}
        ).eq("id", user_id).execute()
    except Exception as exc:
        logger.warning("increment_scan_count failed: %s", exc)
    return True


def plan_allows(user: Optional[dict], feature: str) -> bool:
    """Check if the user's plan allows a feature (pdf, history, employees)."""
    if not user:
        return False
    plan = user.get("plan", "free")
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"]).get(feature, False)
