"""
main.py — TaxLens Zimbabwe FastAPI application.
WHAT CHANGED: New routers included, new API endpoints added.
WHAT DID NOT CHANGE: All original routes, APIs, middleware, imports.
"""

import logging
from pathlib import Path
from typing import Optional
import io

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import supabase_client
from schemas import TaxRequest, TaxResponse, AnalysisResponse, ScrubRequest, ScrubResponse
from tax_service import build_tax_response, calculate_paye
from ocr_service import analyze_payslip

from auth_routes        import router as auth_router
from employee_routes    import router as employee_router
from payroll_routes     import router as payroll_router
from import_duty_routes import router as import_duty_router
from ai_explanation_service import explain_tax_breakdown
from pdf_service            import generate_payslip_pdf
from subscription_service   import get_subscription_status, get_upgrade_prompt, upgrade_plan
from auth_service           import get_optional_user, get_current_user

logger = logging.getLogger(__name__)

BACKEND_DIR  = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"

app = FastAPI(
    title="TaxLens Zimbabwe",
    description="Zimbabwe Payroll, Payslip Verification & Tax Compliance SaaS. Estimates only.",
    version="2.0.0",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(FRONTEND_DIR / "templates"))

app.include_router(auth_router)
app.include_router(employee_router)
app.include_router(payroll_router)
app.include_router(import_duty_router)


# ── ORIGINAL ROUTES — UNCHANGED ───────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def page_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/calculator", response_class=HTMLResponse, include_in_schema=False)
async def page_calculator(request: Request):
    return templates.TemplateResponse("calculator.html", {"request": request})

@app.get("/analyzer", response_class=HTMLResponse, include_in_schema=False)
async def page_analyzer(request: Request):
    return templates.TemplateResponse("analyzer.html", {"request": request})

ALLOWED_TYPES = {"image/jpeg","image/jpg","image/png","application/pdf","image/tiff"}

@app.post("/api/calculate-tax", response_model=TaxResponse, tags=["Tax"])
async def calculate_tax(request: TaxRequest):
    result = build_tax_response(request)
    row = {"session_token": request.session_token, "gross_salary": request.salary,
           "currency": request.currency, "expected_paye": result.paye_tax,
           "actual_paye": None, "difference": None, "flag": "calculator", "source": "calculator"}
    try:
        resp = supabase_client.table("analyses").insert(row).execute()
        if resp.data:
            result.analysis_id = resp.data[0]["id"]
    except Exception as exc:
        logger.warning("Supabase insert failed: %s", exc)
    return result

@app.post("/api/analyze-payslip", response_model=AnalysisResponse, tags=["Payslip"])
async def analyze_payslip_endpoint(
    file: UploadFile = File(...),
    session_token: Optional[str] = Form(None),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported file type '{file.content_type}'.")
    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1_048_576:
        raise HTTPException(status_code=413, detail="File exceeds 10MB limit.")
    result = await analyze_payslip(file_bytes, file.content_type or "image/jpeg")
    if result.extracted_values.gross_salary and result.expected_values:
        row = {"session_token": session_token,
               "gross_salary": result.extracted_values.gross_salary, "currency": "USD",
               "expected_paye": result.expected_values.paye_tax,
               "actual_paye": result.extracted_values.paye,
               "difference": result.difference, "flag": result.flag, "source": "payslip"}
        try:
            resp = supabase_client.table("analyses").insert(row).execute()
            if resp.data:
                result.analysis_id = resp.data[0]["id"]
        except Exception as exc:
            logger.warning("Supabase insert failed: %s", exc)
    return result

@app.delete("/api/scrub", response_model=ScrubResponse, tags=["Privacy"])
async def scrub_data(request: ScrubRequest):
    try:
        resp = supabase_client.table("analyses").delete().eq("session_token", request.session_token).execute()
        count = len(resp.data) if resp.data else 0
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Scrub failed: {exc}")
    return ScrubResponse(
        deleted_count=count,
        message=f"{count} record(s) permanently deleted." if count else "No records found for that token."
    )


# ── NEW API ENDPOINTS ─────────────────────────────────────────────────────────

@app.post("/api/explain", tags=["AI"])
async def explain_deductions(request: TaxRequest):
    """Rule-based plain-English explanations for tax deductions + WhatsApp message."""
    calc = calculate_paye(request.salary, request.currency)
    return {"calculations": calc, "explanations": explain_tax_breakdown(
        gross_salary=calc["gross_salary"], paye_tax=calc["paye_tax"],
        aids_levy=calc["aids_levy"], nssa=calc.get("nssa", 0.0),
        net_salary=calc["net_salary"], effective_rate=calc["effective_rate"],
        tax_band=calc["tax_band"], currency=request.currency,
    )}

@app.post("/api/pdf/payslip", tags=["PDF"])
async def export_payslip_pdf(
    request: TaxRequest,
    current_user: Optional[dict] = Depends(get_optional_user),
    employee_name: Optional[str] = None,
    company_name:  Optional[str] = "Your Company",
    period:        Optional[str] = None,
):
    """Download a professional payslip PDF (Pro/Accountant plan required)."""
    from subscription_service import PLAN_LIMITS
    if current_user:
        plan = current_user.get("plan", "free")
        if not PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])["pdf"]:
            raise HTTPException(status_code=403, detail=get_upgrade_prompt(plan, "PDF exports")["message"])
    calc = calculate_paye(request.salary, request.currency)
    try:
        pdf_bytes = generate_payslip_pdf(
            gross_salary=calc["gross_salary"], paye_tax=calc["paye_tax"],
            aids_levy=calc["aids_levy"], nssa=calc.get("nssa", 0.0),
            total_tax=calc["total_tax"], net_salary=calc["net_salary"],
            effective_rate=calc["effective_rate"], tax_band=calc["tax_band"],
            currency=request.currency, employee_name=employee_name,
            period=period, company_name=company_name,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=taxlens_payslip.pdf"})

@app.get("/api/subscription/status", tags=["Subscription"])
async def subscription_status(current_user: dict = Depends(get_current_user)):
    from auth_service import get_user_by_id
    return get_subscription_status(get_user_by_id(current_user["sub"]) or {})

@app.post("/api/subscription/upgrade", tags=["Subscription"])
async def upgrade_subscription(plan: str, current_user: dict = Depends(get_current_user)):
    return upgrade_plan(current_user["sub"], plan)

@app.get("/api/subscription/plans", tags=["Subscription"])
async def list_plans():
    from subscription_service import PLAN_PRICES, PLAN_FEATURES, PLAN_LIMITS
    return {p: {"price_usd": PLAN_PRICES[p]["usd"], "label": PLAN_PRICES[p]["label"],
                "features": PLAN_FEATURES[p], **PLAN_LIMITS[p]} for p in PLAN_PRICES}
