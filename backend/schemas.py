"""
schemas.py — Pydantic request/response models for TaxLens Zimbabwe.

WHAT CHANGED (Task 2 + 3, backward compatible):
  TaxResponse  — added optional "nssa" field (defaults to 0.0 so old callers unaffected)
  ExtractedValues — added optional "confidence_level" field (Task 3)
  AnalysisResponse — added optional "confidence_level" passthrough (Task 3)

WHAT DID NOT CHANGE:
  - All original fields in every model
  - Field names, types, defaults
  - ScrubRequest, ScrubResponse (untouched)
  - TaxRequest (untouched)
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
    # ── Original fields — unchanged ───────────────────────────────────────────
    gross_salary:   float
    currency:       str
    paye_tax:       float
    aids_levy:      float           # 3% of PAYE
    total_tax:      float           # PAYE + AIDS levy (does NOT include NSSA)
    net_salary:     float           # gross minus PAYE, AIDS levy, AND nssa
    tax_band:       str             # human-readable active band description
    effective_rate: float           # % of gross taken by all statutory deductions
    analysis_id:    Optional[int] = None

    # ── New field (Task 2) — optional, defaults 0.0 for backward compatibility ─
    nssa: float = 0.0              # NSSA employee contribution: min(gross,700)*4.5%

    disclaimer: str = (
        "This tool provides estimated tax calculations and is not affiliated with ZIMRA. "
        "Always consult a qualified tax professional for official guidance."
    )

    # Allow extra keys from calculate_paye() dict to be silently ignored
    model_config = {"extra": "ignore"}


# ─── Payslip Analyzer ──────────────────────────────────────────────────────────

class ExtractedValues(BaseModel):
    # ── Original fields — unchanged ───────────────────────────────────────────
    gross_salary:     Optional[float] = None
    paye:             Optional[float] = None
    aids_levy:        Optional[float] = None
    total_deductions: Optional[float] = None
    net_salary:       Optional[float] = None
    raw_text_snippet: Optional[str]   = None

    # ── New field (Task 3) — confidence scoring ───────────────────────────────
    confidence_level: Optional[str] = None   # "high" | "medium" | "low"


class AnalysisResponse(BaseModel):
    # ── Original fields — unchanged ───────────────────────────────────────────
    extracted_values: ExtractedValues
    expected_values:  Optional[TaxResponse] = None
    difference:       Optional[float] = None
    flag:             str = "Unknown"
    explanation:      str = ""
    analysis_id:      Optional[int] = None

    # ── New field (Task 3) — mirrors confidence from extracted_values ─────────
    confidence_level: Optional[str] = None   # "high" | "medium" | "low"

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
