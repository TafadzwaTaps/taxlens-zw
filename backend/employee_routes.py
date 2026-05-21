"""
employee_routes.py — Employee management routes for TaxLens Zimbabwe.
NEW FILE. Mounted in main.py.

Routes:
  GET  /employees               (page)
  GET  /employees/{id}          (page)
  POST   /api/employees
  GET    /api/employees
  GET    /api/employees/{id}
  PUT    /api/employees/{id}
  DELETE /api/employees/{id}
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import List
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from database import supabase_client
from auth_service import get_current_user, plan_allows, PLAN_LIMITS
from schemas_payroll import EmployeeCreate, EmployeeUpdate, EmployeeOut

logger = logging.getLogger(__name__)
router = APIRouter()

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
templates = Jinja2Templates(directory=str(FRONTEND_DIR / "templates"))


# ── Page routes ───────────────────────────────────────────────────────────────

@router.get("/employees", response_class=HTMLResponse, include_in_schema=False)
async def page_employees(request: Request):
    return templates.TemplateResponse("employees.html", {"request": request})


@router.get("/employees/{employee_id}", response_class=HTMLResponse, include_in_schema=False)
async def page_employee_detail(request: Request, employee_id: str):
    return templates.TemplateResponse(
        "employees.html", {"request": request, "selected_id": employee_id}
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _check_employee_limit(user_id: str, plan: str) -> None:
    """Raise 403 if the user has hit their plan's employee limit."""
    limit = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])["employees"]
    try:
        resp = (
            supabase_client.table("tl_employees")
            .select("id", count="exact")
            .eq("owner_id", user_id)
            .execute()
        )
        count = resp.count or 0
        if count >= limit:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Your {plan} plan supports up to {limit} employee(s). "
                    "Upgrade to add more."
                ),
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Employee limit check failed: %s", exc)


# ── API: Create employee ──────────────────────────────────────────────────────

@router.post("/api/employees", response_model=EmployeeOut, tags=["Employees"])
async def create_employee(
    body: EmployeeCreate,
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["sub"]
    plan    = current_user.get("plan", "free")
    _check_employee_limit(user_id, plan)

    row = {
        "id":           str(uuid.uuid4()),
        "owner_id":     user_id,
        "full_name":    body.full_name,
        "employee_id":  body.employee_id,
        "department":   body.department,
        "position":     body.position,
        "gross_salary": body.gross_salary,
        "currency":     body.currency,
        "tax_number":   body.tax_number,
        "nssa_number":  body.nssa_number,
        "created_at":   datetime.now(timezone.utc).isoformat(),
    }
    try:
        resp = supabase_client.table("tl_employees").insert(row).execute()
        return EmployeeOut(**resp.data[0])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not create employee: {exc}")


# ── API: List employees ───────────────────────────────────────────────────────

@router.get("/api/employees", response_model=List[EmployeeOut], tags=["Employees"])
async def list_employees(current_user: dict = Depends(get_current_user)):
    try:
        resp = (
            supabase_client.table("tl_employees")
            .select("*")
            .eq("owner_id", current_user["sub"])
            .order("full_name")
            .execute()
        )
        return [EmployeeOut(**r) for r in (resp.data or [])]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not fetch employees: {exc}")


# ── API: Get single employee ──────────────────────────────────────────────────

@router.get("/api/employees/{employee_id}", response_model=EmployeeOut, tags=["Employees"])
async def get_employee(
    employee_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        resp = (
            supabase_client.table("tl_employees")
            .select("*")
            .eq("id", employee_id)
            .eq("owner_id", current_user["sub"])
            .limit(1)
            .execute()
        )
        if not resp.data:
            raise HTTPException(status_code=404, detail="Employee not found.")
        return EmployeeOut(**resp.data[0])
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Fetch failed: {exc}")


# ── API: Update employee ──────────────────────────────────────────────────────

@router.put("/api/employees/{employee_id}", response_model=EmployeeOut, tags=["Employees"])
async def update_employee(
    employee_id: str,
    body: EmployeeUpdate,
    current_user: dict = Depends(get_current_user),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update.")
    try:
        resp = (
            supabase_client.table("tl_employees")
            .update(updates)
            .eq("id", employee_id)
            .eq("owner_id", current_user["sub"])
            .execute()
        )
        if not resp.data:
            raise HTTPException(status_code=404, detail="Employee not found.")
        return EmployeeOut(**resp.data[0])
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Update failed: {exc}")


# ── API: Delete employee ──────────────────────────────────────────────────────

@router.delete("/api/employees/{employee_id}", tags=["Employees"])
async def delete_employee(
    employee_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        supabase_client.table("tl_employees").delete().eq(
            "id", employee_id
        ).eq("owner_id", current_user["sub"]).execute()
        return {"message": "Employee deleted successfully."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Delete failed: {exc}")
