"""
schemas_payroll.py — Employee, payroll history, import duty, dashboard models.
NEW FILE — does not touch existing schemas.py.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime, date


# ── Employee ──────────────────────────────────────────────────────────────────

class EmployeeCreate(BaseModel):
    full_name: str
    employee_id: str
    department: Optional[str] = None
    position: Optional[str] = None
    gross_salary: float = Field(..., gt=0)
    currency: Literal["USD", "ZiG"] = "USD"
    tax_number: Optional[str] = None
    nssa_number: Optional[str] = None


class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    department: Optional[str] = None
    position: Optional[str] = None
    gross_salary: Optional[float] = None
    currency: Optional[str] = None
    tax_number: Optional[str] = None
    nssa_number: Optional[str] = None


class EmployeeOut(BaseModel):
    id: str
    owner_id: str
    full_name: str
    employee_id: str
    department: Optional[str] = None
    position: Optional[str] = None
    gross_salary: float
    currency: str
    tax_number: Optional[str] = None
    nssa_number: Optional[str] = None
    created_at: Optional[datetime] = None


# ── Payroll run ───────────────────────────────────────────────────────────────

class PayrollRunCreate(BaseModel):
    period_month: int = Field(..., ge=1, le=12)
    period_year: int = Field(..., ge=2020)
    notes: Optional[str] = None


class PayrollRunOut(BaseModel):
    id: str
    owner_id: str
    period_month: int
    period_year: int
    total_gross: float
    total_paye: float
    total_nssa: float
    total_aids_levy: float
    total_net: float
    employee_count: int
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


# ── Payroll history entry ─────────────────────────────────────────────────────

class PayrollHistoryOut(BaseModel):
    id: str
    run_id: Optional[str] = None
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    gross_salary: float
    paye_tax: float
    aids_levy: float
    nssa: float
    net_salary: float
    currency: str
    period_month: int
    period_year: int
    source: str    # 'calculator' | 'payslip' | 'payroll_run'
    created_at: Optional[datetime] = None


# ── Import duty ───────────────────────────────────────────────────────────────

class ImportDutyRequest(BaseModel):
    category: Literal[
        "electronics", "clothing", "vehicle",
        "furniture", "food", "cosmetics", "other"
    ]
    item_value_usd: float = Field(..., gt=0, description="CIF value in USD")
    shipping_usd: float = Field(0.0, ge=0)
    insurance_usd: float = Field(0.0, ge=0)


class ImportDutyResponse(BaseModel):
    category: str
    cif_value: float           # item + shipping + insurance
    duty_rate: float           # percentage
    duty_amount: float
    vat_rate: float            # 14.5% standard ZW VAT
    vat_amount: float
    surtax_amount: float       # category-specific
    total_import_cost: float   # CIF + duty + VAT + surtax
    total_landed_cost: float   # total_import_cost + original item value
    breakdown: dict
    disclaimer: str = (
        "These are estimates only. Actual duties are determined by ZIMRA at point of entry. "
        "Always verify with a licensed customs agent."
    )


# ── Dashboard ─────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    employee_count: int
    total_monthly_gross: float
    total_monthly_paye: float
    total_monthly_nssa: float
    total_monthly_net: float
    analyses_this_month: int
    recent_runs: List[PayrollRunOut] = []
    plan: str
    scans_used: int
    scans_limit: int


# ── Subscription ──────────────────────────────────────────────────────────────

class SubscriptionStatus(BaseModel):
    plan: Literal["free", "pro", "accountant"]
    scans_used: int
    scans_limit: int
    pdf_exports: bool
    payroll_history: bool
    employee_management: bool
    advanced_reports: bool
    can_upgrade: bool
