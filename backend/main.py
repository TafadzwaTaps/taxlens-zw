"""
main.py — TaxLens Zimbabwe FastAPI application.
All routes are defined here in one flat file for simplicity.
Database: Supabase (via supabase-py client, no SQLAlchemy).
Hosting:  Render.com

HOW TO RUN (from the backend/ folder):
    uvicorn main:app --reload --port 8000
                ^^^^
                NOT app.main — the file is main.py, flat in backend/
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import supabase_client
from schemas import (
    TaxRequest, TaxResponse,
    AnalysisResponse,
    ScrubRequest, ScrubResponse,
)
from tax_service import build_tax_response
from ocr_service import analyze_payslip

logger = logging.getLogger(__name__)

# ── Path resolution (works on Windows AND Linux/Render) ───────────────────────
# Path(__file__).resolve() always gives the real absolute path regardless of
# how uvicorn was invoked or whether --reload is active.
#
# Layout assumed:
#   taxlens-zw/
#     backend/   ← this file lives here
#     frontend/  ← templates and static assets live here

BACKEND_DIR  = Path(__file__).resolve().parent          # …/taxlens-zw/backend
PROJECT_ROOT = BACKEND_DIR.parent                       # …/taxlens-zw
FRONTEND_DIR = PROJECT_ROOT / "frontend"                # …/taxlens-zw/frontend

# ── App init ───────────────────────────────────────────────────────────────────
app = FastAPI(
    title="TaxLens Zimbabwe",
    description=(
        "Tax transparency and salary verification tool for Zimbabwean employees. "
        "Estimates only — not affiliated with ZIMRA."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files ───────────────────────────────────────────────────────────────
app.mount(
    "/static",
    StaticFiles(directory=str(FRONTEND_DIR / "static")),
    name="static",
)

# ── Templates ─────────────────────────────────────────────────────────────────
templates = Jinja2Templates(directory=str(FRONTEND_DIR / "templates"))


# ── Page routes ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def page_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/calculator", response_class=HTMLResponse, include_in_schema=False)
async def page_calculator(request: Request):
    return templates.TemplateResponse("calculator.html", {"request": request})


@app.get("/analyzer", response_class=HTMLResponse, include_in_schema=False)
async def page_analyzer(request: Request):
    return templates.TemplateResponse("analyzer.html", {"request": request})


# ── API: PAYE Calculator ───────────────────────────────────────────────────────

@app.post("/api/calculate-tax", response_model=TaxResponse, tags=["Tax"])
async def calculate_tax(request: TaxRequest):
    """
    Calculate monthly PAYE for a gross salary in USD or ZiG.

    Pass an optional `session_token` (any string you choose) to enable
    deleting this record later via **DELETE /api/scrub**.

    Returns gross, PAYE, AIDS levy, total deductions, net pay, and effective rate.
    All figures are **estimates** — not official ZIMRA assessments.
    """
    result = build_tax_response(request)

    # Persist anonymised record — gross salary IS stored for analysis purposes
    # but no name, email, or identity is ever saved.
    row = {
        "session_token": request.session_token,
        "gross_salary":  request.salary,
        "currency":      request.currency,
        "expected_paye": result.paye_tax,
        "actual_paye":   None,
        "difference":    None,
        "flag":          "calculator",
        "source":        "calculator",
    }
    try:
        resp = supabase_client.table("analyses").insert(row).execute()
        if resp.data:
            result.analysis_id = resp.data[0]["id"]
    except Exception as exc:
        # Non-fatal — the tax result is still returned to the user
        logger.warning("Supabase insert failed: %s", exc)

    return result


# ── API: Payslip Analyzer ──────────────────────────────────────────────────────

ALLOWED_TYPES = {
    "image/jpeg", "image/jpg", "image/png",
    "application/pdf", "image/tiff",
}


@app.post("/api/analyze-payslip", response_model=AnalysisResponse, tags=["Payslip"])
async def analyze_payslip_endpoint(
    file: UploadFile = File(..., description="Payslip image (JPG/PNG) or PDF, max 10MB"),
    session_token: Optional[str] = Form(None, description="Optional token for later data scrub"),
):
    """
    Upload a payslip image or PDF.

    - OCR extracts gross salary, PAYE, AIDS levy, deductions, net pay
    - Expected PAYE is calculated and compared to the extracted figure
    - A flag is returned: **OK**, **Possible over-deduction**, or **Possible under-deduction**

    **The uploaded file is never stored.** Only the anonymised numeric result is
    saved (and only if you supply a `session_token`).
    """
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{file.content_type}'. Upload JPG, PNG, or PDF.",
        )

    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1_048_576:
        raise HTTPException(status_code=413, detail="File exceeds 10MB limit.")

    # Analysis — file bytes stay in memory only, never written to disk
    result = await analyze_payslip(file_bytes, file.content_type or "image/jpeg")

    # Persist anonymised result only when extraction succeeded
    if result.extracted_values.gross_salary and result.expected_values:
        row = {
            "session_token": session_token,
            "gross_salary":  result.extracted_values.gross_salary,
            "currency":      "USD",
            "expected_paye": result.expected_values.paye_tax,
            "actual_paye":   result.extracted_values.paye,
            "difference":    result.difference,
            "flag":          result.flag,
            "source":        "payslip",
        }
        try:
            resp = supabase_client.table("analyses").insert(row).execute()
            if resp.data:
                result.analysis_id = resp.data[0]["id"]
        except Exception as exc:
            logger.warning("Supabase insert failed: %s", exc)

    return result


# ── API: Scrub (privacy delete) ────────────────────────────────────────────────

@app.delete("/api/scrub", response_model=ScrubResponse, tags=["Privacy"])
async def scrub_data(request: ScrubRequest):
    """
    Permanently delete all analysis records associated with your session token.

    - Supply the same token you used when calculating
    - All matching rows are hard-deleted from the database
    - This action is irreversible
    - If no records exist for that token, a count of 0 is returned
    """
    try:
        resp = (
            supabase_client
            .table("analyses")
            .delete()
            .eq("session_token", request.session_token)
            .execute()
        )
        count = len(resp.data) if resp.data else 0
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Scrub failed: {exc}")

    return ScrubResponse(
        deleted_count=count,
        message=(
            f"{count} record(s) permanently deleted. Your data is gone."
            if count else
            "No records found for that token. Nothing was deleted."
        ),
    )
