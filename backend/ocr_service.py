"""
ocr_service.py — Payslip OCR and analysis pipeline.

WHAT CHANGED (Task 3 + 4 + 5, non-destructive):
  Task 3 — _normalize_amount(): strips currency symbols + commas before parsing
            extract_values(): expanded regex patterns for broader payslip coverage
            _score_confidence(): NEW — scores extraction quality as high/medium/low
            ExtractedValues now carries confidence_level
  Task 4 — _flag_and_explain(): REPLACED fixed-dollar threshold with
            percentage-based logic (< 5% = OK, 5–15% = Minor discrepancy,
            > 15% = Possible discrepancy). Neutral wording preserved.
  Task 5 — inline comments added throughout.

WHAT DID NOT CHANGE:
  - All function names and signatures
  - run_ocr(), _pdf_first_page_to_image(), _to_greyscale_image()
  - analyze_payslip() pipeline (OCR → extract → compare → flag)
  - _find_amount() (extended only — original patterns kept, new ones appended)
  - File never stored — still memory-only processing

The uploaded file bytes are NEVER written to disk or stored.
"""

import re
import io
import logging
from typing import Optional

from PIL import Image
import pytesseract
import fitz                              # PyMuPDF

from schemas import ExtractedValues, AnalysisResponse, TaxResponse
from tax_service import calculate_paye

logger = logging.getLogger(__name__)

# ── Flag labels (Task 4) ──────────────────────────────────────────────────────
# Changed from fixed-dollar thresholds to percentage-based thresholds.
# Labels use neutral language — no accusatory wording.
OK_LABEL              = "OK"
MINOR_DISCREPANCY     = "Minor discrepancy"           # new (Task 4)
POSSIBLE_DISCREPANCY  = "Possible discrepancy"        # replaces OVER/UNDER labels

# Percentage thresholds (Task 4) — applied to expected_paye as the reference
PCT_OK_THRESHOLD      = 0.05   # within 5%  → OK
PCT_MINOR_THRESHOLD   = 0.15   # within 15% → Minor discrepancy
                                # above 15%  → Possible discrepancy


# ── Image helpers — UNCHANGED ─────────────────────────────────────────────────

def _pdf_first_page_to_image(pdf_bytes: bytes) -> Image.Image:
    """Rasterise the first page of a PDF at 2× zoom for better OCR accuracy."""
    doc  = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    pix  = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
    return Image.open(io.BytesIO(pix.tobytes("png")))


def _to_greyscale_image(file_bytes: bytes, content_type: str) -> Image.Image:
    """Return a greyscale PIL image regardless of input format."""
    if "pdf" in content_type:
        img = _pdf_first_page_to_image(file_bytes)
    else:
        img = Image.open(io.BytesIO(file_bytes))
    return img.convert("L")


# ── OCR — UNCHANGED ───────────────────────────────────────────────────────────

def run_ocr(file_bytes: bytes, content_type: str) -> str:
    """Run Tesseract on the image and return raw text."""
    img = _to_greyscale_image(file_bytes, content_type)
    return pytesseract.image_to_string(img, config="--psm 6")


# ── Value extraction ──────────────────────────────────────────────────────────

def _normalize_amount(raw: str) -> str:
    """
    NEW (Task 3) — strip noise before float conversion.
    Removes: commas, dollar signs, ZiG prefix, spaces, USD text.
    Example: "ZiG 1,234.56" → "1234.56" | "$1,200" → "1200"
    """
    raw = raw.replace(",", "")          # remove thousand separators
    raw = re.sub(r"[Uu][Ss][Dd]", "", raw)   # remove "USD" text
    raw = re.sub(r"[Zz][Ii][Gg]", "", raw)   # remove "ZiG" prefix
    raw = re.sub(r"[$Z]", "", raw)      # remove $ and Z currency symbols
    return raw.strip()


def _find_amount(patterns: list, text: str) -> Optional[float]:
    """
    Try each regex pattern; return the first numeric match as float.
    CHANGED (Task 3): raw value now passed through _normalize_amount()
    before float conversion, handling currency symbols and comma separators.
    Original patterns are kept; new ones appended in extract_values().
    """
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            raw = _normalize_amount(m.group(1))   # CHANGED: normalise first
            try:
                return float(raw)
            except ValueError:
                continue
    return None


def extract_values(text: str) -> ExtractedValues:
    """
    Parse OCR text and extract payslip fields.

    CHANGED (Task 3):
      - Additional regex patterns appended to each field's list
        to handle more payslip layouts (tabular, colon-free, ZiG prefix)
      - confidence_level computed via _score_confidence() and stored
    Original patterns are kept unchanged at the top of each list.
    """

    # ── Gross salary ──────────────────────────────────────────────────────────
    gross = _find_amount([
        # Original patterns
        r"gross\s*(?:salary|pay|earnings)\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
        r"basic\s*(?:salary|pay)\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
        r"gross\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
        # NEW: tabular layout — "Gross Salary   1,500.00" (no colon)
        r"gross\s+salary\s+([0-9,]+(?:\.\d{1,2})?)",
        r"basic\s+salary\s+([0-9,]+(?:\.\d{1,2})?)",
        # NEW: ZiG prefix
        r"gross\s*[:\-]?\s*ZiG\s*([0-9,]+(?:\.\d{1,2})?)",
    ], text)

    # ── PAYE ──────────────────────────────────────────────────────────────────
    paye = _find_amount([
        # Original patterns
        r"p\.?a\.?y\.?e\.?\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
        r"income\s*tax\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
        r"tax\s*deducted\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
        r"paye\s*tax\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
        # NEW: tabular (no colon)
        r"p\.?a\.?y\.?e\.?\s+([0-9,]+(?:\.\d{1,2})?)",
        r"income\s+tax\s+([0-9,]+(?:\.\d{1,2})?)",
        # NEW: "withholding tax"
        r"withholding\s*tax\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
    ], text)

    # ── AIDS levy ─────────────────────────────────────────────────────────────
    aids = _find_amount([
        # Original patterns
        r"aids\s*levy\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
        r"hiv\s*levy\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
        # NEW: tabular
        r"aids\s+levy\s+([0-9,]+(?:\.\d{1,2})?)",
        r"aids\s*[:\-]\s*([0-9,]+(?:\.\d{1,2})?)",
    ], text)

    # ── Total deductions ──────────────────────────────────────────────────────
    total_deductions = _find_amount([
        # Original patterns
        r"total\s*deductions?\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
        r"deductions?\s*total\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
        # NEW: tabular
        r"total\s+deductions?\s+([0-9,]+(?:\.\d{1,2})?)",
        r"total\s*deduct\s*[:\-]?\s*([0-9,]+(?:\.\d{1,2})?)",
    ], text)

    # ── Net salary ────────────────────────────────────────────────────────────
    net = _find_amount([
        # Original patterns
        r"net\s*(?:pay|salary)\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
        r"take[\s\-]?home\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
        r"net\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
        # NEW: tabular
        r"net\s+pay\s+([0-9,]+(?:\.\d{1,2})?)",
        r"net\s+salary\s+([0-9,]+(?:\.\d{1,2})?)",
    ], text)

    # ── Confidence scoring (Task 3) ───────────────────────────────────────────
    confidence = _score_confidence(gross, paye, aids, net)

    return ExtractedValues(
        gross_salary=gross,
        paye=paye,
        aids_levy=aids,
        total_deductions=total_deductions,
        net_salary=net,
        raw_text_snippet=text[:500].strip(),
        confidence_level=confidence,          # NEW (Task 3)
    )


def _score_confidence(
    gross: Optional[float],
    paye:  Optional[float],
    aids:  Optional[float],
    net:   Optional[float],
) -> str:
    """
    NEW (Task 3) — Rate extraction quality based on how many key fields
    were successfully parsed.

    Scoring:
      4 fields found → "high"    (gross + paye + aids + net)
      2–3 fields     → "medium"
      0–1 fields     → "low"

    Only the four primary financial fields are counted; total_deductions
    is supplementary and not included in the score.
    """
    found = sum(1 for v in [gross, paye, aids, net] if v is not None)
    if found >= 4:
        return "high"
    if found >= 2:
        return "medium"
    return "low"


# ── Comparison — REPLACED with percentage logic (Task 4) ──────────────────────

def _flag_and_explain(difference: float, expected_paye: float) -> tuple[str, str]:
    """
    Map a PAYE difference to a flag label and plain-English explanation.

    CHANGED (Task 4): replaced fixed-dollar threshold ($5) with
    percentage-based thresholds relative to expected_paye:
      |diff| / expected_paye < 5%  → OK
      |diff| / expected_paye < 15% → Minor discrepancy
      |diff| / expected_paye >= 15%→ Possible discrepancy

    Neutral language only — no accusatory wording.
    Falls back to OK if expected_paye is zero (avoids division by zero).
    """
    abs_diff = abs(difference)

    # Guard: if expected is zero we cannot compute a percentage
    if expected_paye == 0:
        return (
            OK_LABEL,
            "No PAYE is expected at this salary level. Your deductions look correct."
        )

    pct_diff = abs_diff / expected_paye  # e.g. 0.04 = 4%

    if pct_diff < PCT_OK_THRESHOLD:
        # Within 5% — within normal rounding and timing tolerance
        return (
            OK_LABEL,
            f"The PAYE on your payslip is within {pct_diff*100:.1f}% of the estimate "
            f"(${abs_diff:.2f} difference) — within normal rounding tolerance."
        )

    if pct_diff < PCT_MINOR_THRESHOLD:
        # 5–15% difference — flag but use measured language
        direction = "higher" if difference > 0 else "lower"
        return (
            MINOR_DISCREPANCY,
            f"The PAYE on your payslip is {pct_diff*100:.1f}% {direction} than the estimate "
            f"(${abs_diff:.2f} difference). This may reflect employer-specific allowances, "
            "timing adjustments, or rounding differences. We recommend confirming with "
            "your payroll department."
        )

    # Above 15% — possible discrepancy, still neutral
    direction = "higher" if difference > 0 else "lower"
    return (
        POSSIBLE_DISCREPANCY,
        f"The PAYE on your payslip is {pct_diff*100:.1f}% {direction} than the estimate "
        f"(${abs_diff:.2f} difference). This is a possible discrepancy. Common reasons "
        "include additional taxable benefits, pension adjustments, or a different gross "
        "salary basis. Please verify with your employer or a qualified tax advisor. "
        "This tool provides estimates only and is not affiliated with ZIMRA."
    )


# ── Public entry point — UNCHANGED signature ──────────────────────────────────

async def analyze_payslip(file_bytes: bytes, content_type: str) -> AnalysisResponse:
    """
    Full pipeline: OCR → extract → calculate → compare → flag.
    File bytes are never persisted — memory only.

    Pipeline unchanged; _flag_and_explain() now receives expected_paye
    for percentage-based comparison (Task 4).
    """
    # Step 1 — OCR (unchanged)
    try:
        raw_text = run_ocr(file_bytes, content_type)
    except Exception as exc:
        logger.warning("OCR failed: %s", exc)
        raw_text = ""

    # Step 2 — extract values from text (enhanced patterns + confidence)
    extracted = extract_values(raw_text)

    # Step 3 — early exit if gross salary could not be found
    if not extracted.gross_salary:
        return AnalysisResponse(
            extracted_values=extracted,
            flag="Could not extract salary",
            confidence_level=extracted.confidence_level,
            explanation=(
                "We could not detect a gross salary figure in this document. "
                "Make sure the image is clear and labels like 'Gross Salary' are visible. "
                "Alternatively, use the manual calculator."
            ),
        )

    # Step 4 — calculate expected PAYE using the (now-accurate) tax engine
    calc     = calculate_paye(extracted.gross_salary, "USD")
    expected = TaxResponse(**calc)

    # Step 5 — early exit if PAYE line not found in payslip
    if extracted.paye is None:
        return AnalysisResponse(
            extracted_values=extracted,
            expected_values=expected,
            flag="PAYE not found",
            confidence_level=extracted.confidence_level,
            explanation=(
                "Gross salary was detected but PAYE could not be extracted. "
                "Use the manual calculator to estimate your expected tax."
            ),
        )

    # Step 6 — compare and flag using percentage logic (Task 4)
    difference = round(extracted.paye - calc["paye_tax"], 2)
    flag, explanation = _flag_and_explain(difference, calc["paye_tax"])

    return AnalysisResponse(
        extracted_values=extracted,
        expected_values=expected,
        difference=difference,
        flag=flag,
        explanation=explanation,
        confidence_level=extracted.confidence_level,   # Task 3
    )
