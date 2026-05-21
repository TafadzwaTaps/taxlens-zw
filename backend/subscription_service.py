"""
subscription_service.py — Subscription plan management for TaxLens Zimbabwe.
NEW FILE.

Handles:
  - Plan feature gating
  - Usage limit enforcement
  - Upgrade prompt generation
  - Payment placeholder (PayPal / Paynow Zimbabwe / Stripe)
"""

from fastapi import HTTPException
from auth_service import PLAN_LIMITS, get_user_by_id
from database import supabase_client
from schemas_payroll import SubscriptionStatus
import logging

logger = logging.getLogger(__name__)

# ── Plan pricing (USD/month) ──────────────────────────────────────────────────
PLAN_PRICES = {
    "free":       {"usd": 0,    "label": "Free"},
    "pro":        {"usd": 9,    "label": "Pro"},
    "accountant": {"usd": 25,   "label": "Accountant"},
}

# ── Feature descriptions for upgrade prompts ──────────────────────────────────
PLAN_FEATURES = {
    "free": [
        "5 payslip scans/month",
        "Manual PAYE calculator",
        "Import duty estimator",
        "Up to 3 employees",
    ],
    "pro": [
        "Unlimited payslip scans",
        "Full payroll history",
        "PDF export (payslips + summaries)",
        "Up to 50 employees",
        "Payroll run automation",
        "Advanced analytics dashboard",
    ],
    "accountant": [
        "Everything in Pro",
        "Unlimited employees",
        "Multi-company support (coming soon)",
        "Bulk payroll imports (coming soon)",
        "Priority support",
    ],
}


def get_subscription_status(user: dict) -> SubscriptionStatus:
    """Return the current subscription status for a user dict."""
    plan  = user.get("plan", "free")
    used  = user.get("scans_used", 0)
    limit = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])

    return SubscriptionStatus(
        plan=plan,
        scans_used=used,
        scans_limit=limit["scans"],
        pdf_exports=limit["pdf"],
        payroll_history=limit["history"],
        employee_management=True,   # all plans
        advanced_reports=plan in ("pro", "accountant"),
        can_upgrade=plan != "accountant",
    )


def enforce_scan_limit(user_id: str) -> None:
    """
    Check + increment the user's scan counter.
    Raises HTTP 403 if the monthly limit is reached.
    Guest users (user_id=None) get a default 3-scan allowance tracked by session.
    """
    user  = get_user_by_id(user_id) if user_id else None
    if not user:
        return  # guests — no enforcement (rely on session token rate limit)

    plan  = user.get("plan", "free")
    used  = user.get("scans_used", 0)
    limit = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])["scans"]

    if used >= limit:
        raise HTTPException(
            status_code=403,
            detail=(
                f"You have used all {limit} scans on your {plan.title()} plan this month. "
                "Upgrade to Pro for unlimited scans."
            ),
        )
    # Increment
    try:
        supabase_client.table("tl_users").update(
            {"scans_used": used + 1}
        ).eq("id", user_id).execute()
    except Exception as exc:
        logger.warning("scan count update failed: %s", exc)


def upgrade_plan(user_id: str, new_plan: str) -> dict:
    """
    Upgrade a user's plan in the database.
    In production: validate payment before calling this.
    """
    if new_plan not in PLAN_LIMITS:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {new_plan}")
    try:
        supabase_client.table("tl_users").update(
            {"plan": new_plan}
        ).eq("id", user_id).execute()
        return {
            "message": f"Plan upgraded to {new_plan.title()} successfully.",
            "plan": new_plan,
            "features": PLAN_FEATURES[new_plan],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Upgrade failed: {exc}")


def get_upgrade_prompt(current_plan: str, blocked_feature: str) -> dict:
    """Return a structured upgrade prompt for display in the UI."""
    next_plan = "pro" if current_plan == "free" else "accountant"
    return {
        "current_plan":    current_plan,
        "next_plan":       next_plan,
        "next_plan_price": PLAN_PRICES[next_plan]["usd"],
        "blocked_feature": blocked_feature,
        "next_features":   PLAN_FEATURES[next_plan],
        "payment_options": [
            {"name": "PayPal",           "enabled": False, "coming_soon": True},
            {"name": "Paynow Zimbabwe",  "enabled": False, "coming_soon": True},
            {"name": "Stripe",           "enabled": False, "coming_soon": True},
        ],
        "message": (
            f"This feature requires the {next_plan.title()} plan "
            f"(${PLAN_PRICES[next_plan]['usd']}/month). "
            "Payment integration coming soon — contact us to upgrade manually."
        ),
    }
