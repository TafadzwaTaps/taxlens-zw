"""
schemas.py — Pydantic request/response models for TaxLens Zimbabwe.
All monetary values are in the stated currency.
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


# ─── Tax Calculator ────────────────────────────────────────────────────────────

class TaxRequest(BaseModel):
    salary: float = Field(..., gt=0, description="Gross monthly salary (positive)")
    currency: Literal["USD", "ZiG"] = Field("USD", description="USD or ZiG")
    session_token: Optional[str] = Field(
        None,
        description="Optional random string you choose. Used later to delete your data."
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "salary": 1500.00,
                "currency": "USD",
                "session_token": "my-random-secret-token"
            }
        }
    }


class TaxResponse(BaseModel):
    gross_salary:   float
    currency:       str
    paye_tax:       float
    aids_levy:      float           # 3% of PAYE
    total_tax:      float           # PAYE + AIDS levy
    net_salary:     float
    tax_band:       str             # human-readable band description
    effective_rate: float           # percentage
    analysis_id:    Optional[int] = None    # DB row ID — returned so user can scrub later
    disclaimer: str = (
        "This tool provides estimates only and does not represent "
        "official ZIMRA calculations. Always consult a tax professional."
    )


# ─── Payslip Analyzer ──────────────────────────────────────────────────────────

class ExtractedValues(BaseModel):
    gross_salary:     Optional[float] = None
    paye:             Optional[float] = None
    aids_levy:        Optional[float] = None
    total_deductions: Optional[float] = None
    net_salary:       Optional[float] = None
    raw_text_snippet: Optional[str]   = None  # first 500 chars of OCR output


class AnalysisResponse(BaseModel):
    extracted_values: ExtractedValues
    expected_values:  Optional[TaxResponse] = None
    difference:       Optional[float] = None    # actual_paye - expected_paye
    flag:             str = "Unknown"
    explanation:      str = ""
    analysis_id:      Optional[int] = None      # for scrub requests
    disclaimer: str = (
        "Figures are estimates based on standard PAYE bands. "
        "Discrepancies may result from employer-specific deductions, "
        "pension contributions, or other legitimate adjustments. "
        "This is not an accusation of error or fraud."
    )


# ─── Privacy / Scrub ───────────────────────────────────────────────────────────

class ScrubRequest(BaseModel):
    session_token: str = Field(..., description="The token you provided when calculating")


class ScrubResponse(BaseModel):
    deleted_count: int
    message: str
