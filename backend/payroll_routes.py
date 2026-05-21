"""
payroll_routes.py — Payroll history and run management routes.
NEW FILE. Mounted in main.py.

Routes:
  GET /payroll-history         (page)
  GET /dashboard               (page)
  GET /api/payroll/history
  GET /api/payroll/history/{id}
  POST /api/payroll/runs
  GET  /api/payroll/runs
  GET  /api/dashboard/stats
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from database import supabase_client
from auth_service import get_current_user, plan_allows
from schemas_payroll import PayrollHistoryOut, PayrollRunCreate, PayrollRunOut, DashboardStats
from tax_service import calculate_paye   # reuses existing engine

logger = logging.getLogger(__name__)
router = APIRouter()

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
templates = Jinja2Templates(directory=str(FRONTEND_DIR / "templates"))


# ── Page routes ───────────────────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def page_dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/payroll-history", response_class=HTMLResponse, include_in_schema=False)
async def page_payroll_history(request: Request):
    return templates.TemplateResponse("payroll_history.html", {"request": request})


# ── API: Payroll history (read) ───────────────────────────────────────────────

@router.get("/api/payroll/history", response_model=List[PayrollHistoryOut], tags=["Payroll"])
async def get_payroll_history(
    current_user: dict = Depends(get_current_user),
    month: Optional[int]  = Query(None, ge=1, le=12),
    year:  Optional[int]  = Query(None, ge=2020),
    employee_name: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """
    Return paginated payroll history for the authenticated user.
    Filters: month, year, employee_name (partial match).
    Requires pro or accountant plan for full history.
    """
    if not plan_allows({"plan": current_user.get("plan", "free")}, "history"):
        raise HTTPException(
            status_code=403,
            detail="Payroll history requires a Pro or Accountant plan. Please upgrade.",
        )
    try:
        query = (
            supabase_client.table("tl_payroll_history")
            .select("*")
            .eq("owner_id", current_user["sub"])
            .order("created_at", desc=True)
            .limit(limit)
        )
        if month:
            query = query.eq("period_month", month)
        if year:
            query = query.eq("period_year", year)
        if employee_name:
            query = query.ilike("employee_name", f"%{employee_name}%")

        resp = query.execute()
        return [PayrollHistoryOut(**r) for r in (resp.data or [])]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"History fetch failed: {exc}")


# ── API: Single history record ────────────────────────────────────────────────

@router.get("/api/payroll/history/{record_id}", response_model=PayrollHistoryOut, tags=["Payroll"])
async def get_history_record(
    record_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        resp = (
            supabase_client.table("tl_payroll_history")
            .select("*")
            .eq("id", record_id)
            .eq("owner_id", current_user["sub"])
            .limit(1)
            .execute()
        )
        if not resp.data:
            raise HTTPException(status_code=404, detail="Record not found.")
        return PayrollHistoryOut(**resp.data[0])
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── API: Create payroll run (bulk calculate all employees) ────────────────────

@router.post("/api/payroll/runs", response_model=PayrollRunOut, tags=["Payroll"])
async def create_payroll_run(
    body: PayrollRunCreate,
    current_user: dict = Depends(get_current_user),
):
    """
    Run payroll for all employees of the authenticated user for a given period.
    Creates one tl_payroll_history row per employee, and one tl_payroll_runs summary.
    """
    user_id = current_user["sub"]

    # Fetch all employees
    try:
        emp_resp = (
            supabase_client.table("tl_employees")
            .select("*")
            .eq("owner_id", user_id)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not fetch employees: {exc}")

    employees = emp_resp.data or []
    if not employees:
        raise HTTPException(
            status_code=400,
            detail="No employees found. Add employees before running payroll."
        )

    run_id       = str(uuid.uuid4())
    now          = datetime.now(timezone.utc).isoformat()
    history_rows = []
    totals       = {"gross": 0.0, "paye": 0.0, "nssa": 0.0, "aids": 0.0, "net": 0.0}

    for emp in employees:
        calc = calculate_paye(emp["gross_salary"], emp.get("currency", "USD"))
        row  = {
            "id":            str(uuid.uuid4()),
            "run_id":        run_id,
            "owner_id":      user_id,
            "employee_id":   emp["id"],
            "employee_name": emp["full_name"],
            "gross_salary":  calc["gross_salary"],
            "paye_tax":      calc["paye_tax"],
            "aids_levy":     calc["aids_levy"],
            "nssa":          calc.get("nssa", 0.0),
            "net_salary":    calc["net_salary"],
            "currency":      emp.get("currency", "USD"),
            "period_month":  body.period_month,
            "period_year":   body.period_year,
            "source":        "payroll_run",
            "created_at":    now,
        }
        history_rows.append(row)
        totals["gross"] += calc["gross_salary"]
        totals["paye"]  += calc["paye_tax"]
        totals["nssa"]  += calc.get("nssa", 0.0)
        totals["aids"]  += calc["aids_levy"]
        totals["net"]   += calc["net_salary"]

    # Insert history rows
    try:
        supabase_client.table("tl_payroll_history").insert(history_rows).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"History insert failed: {exc}")

    # Insert run summary
    run_row = {
        "id":             run_id,
        "owner_id":       user_id,
        "period_month":   body.period_month,
        "period_year":    body.period_year,
        "total_gross":    round(totals["gross"], 2),
        "total_paye":     round(totals["paye"],  2),
        "total_nssa":     round(totals["nssa"],  2),
        "total_aids_levy": round(totals["aids"], 2),
        "total_net":      round(totals["net"],   2),
        "employee_count": len(employees),
        "notes":          body.notes,
        "created_at":     now,
    }
    try:
        resp = supabase_client.table("tl_payroll_runs").insert(run_row).execute()
        return PayrollRunOut(**resp.data[0])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Run summary failed: {exc}")


# ── API: List payroll runs ────────────────────────────────────────────────────

@router.get("/api/payroll/runs", response_model=List[PayrollRunOut], tags=["Payroll"])
async def list_payroll_runs(
    current_user: dict = Depends(get_current_user),
    limit: int = Query(12, le=60),
):
    try:
        resp = (
            supabase_client.table("tl_payroll_runs")
            .select("*")
            .eq("owner_id", current_user["sub"])
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [PayrollRunOut(**r) for r in (resp.data or [])]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── API: Dashboard stats ──────────────────────────────────────────────────────

@router.get("/api/dashboard/stats", response_model=DashboardStats, tags=["Dashboard"])
async def dashboard_stats(current_user: dict = Depends(get_current_user)):
    """Return summary stats for the authenticated user's dashboard."""
    user_id = current_user["sub"]
    plan    = current_user.get("plan", "free")
    from auth_service import PLAN_LIMITS, get_user_by_id

    user = get_user_by_id(user_id) or {}
    scans_used  = user.get("scans_used", 0)
    scans_limit = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])["scans"]

    # Employee count + salary totals
    try:
        emp_resp = (
            supabase_client.table("tl_employees")
            .select("gross_salary, currency")
            .eq("owner_id", user_id)
            .execute()
        )
        employees = emp_resp.data or []
    except Exception:
        employees = []

    total_gross = sum(e["gross_salary"] for e in employees)
    total_paye  = 0.0
    total_nssa  = 0.0
    total_net   = 0.0
    for emp in employees:
        c = calculate_paye(emp["gross_salary"], emp.get("currency", "USD"))
        total_paye += c["paye_tax"]
        total_nssa += c.get("nssa", 0.0)
        total_net  += c["net_salary"]

    # Analyses this month
    now = datetime.now(timezone.utc)
    try:
        an_resp = (
            supabase_client.table("analyses")
            .select("id", count="exact")
            .gte("created_at", now.replace(day=1).isoformat())
            .execute()
        )
        analyses_count = an_resp.count or 0
    except Exception:
        analyses_count = 0

    # Recent payroll runs
    try:
        run_resp = (
            supabase_client.table("tl_payroll_runs")
            .select("*")
            .eq("owner_id", user_id)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )
        recent_runs = [PayrollRunOut(**r) for r in (run_resp.data or [])]
    except Exception:
        recent_runs = []

    return DashboardStats(
        employee_count=len(employees),
        total_monthly_gross=round(total_gross, 2),
        total_monthly_paye=round(total_paye, 2),
        total_monthly_nssa=round(total_nssa, 2),
        total_monthly_net=round(total_net, 2),
        analyses_this_month=analyses_count,
        recent_runs=recent_runs,
        plan=plan,
        scans_used=scans_used,
        scans_limit=scans_limit,
    )
