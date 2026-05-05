"""
ocr_service.py — Payslip OCR and analysis pipeline.

Flow:
  1. Receive file bytes (JPG / PNG / PDF)
  2. Convert to greyscale PIL image (PDF → first page via PyMuPDF)
  3. Run Tesseract OCR
  4. Extract gross salary, PAYE, AIDS levy, deductions, net pay via regex
  5. Recalculate expected PAYE with our tax engine
  6. Compare extracted vs expected → flag discrepancy

The uploaded file bytes are NEVER written to disk or stored.
"""

import re
import io
import logging
from typing import Optional

from PIL import Image
import pytesseract
import fitz                             # PyMuPDF

from schemas import ExtractedValues, AnalysisResponse, TaxResponse
from tax_service import calculate_paye

logger = logging.getLogger(__name__)

FLAG_THRESHOLD        = 5.0             # $5 tolerance before flagging
OK_LABEL              = "OK"
OVER_DEDUCTION_LABEL  = "Possible over-deduction"
UNDER_DEDUCTION_LABEL = "Possible under-deduction"


# ── Image helpers ──────────────────────────────────────────────────────────────

def _pdf_first_page_to_image(pdf_bytes: bytes) -> Image.Image:
    """Rasterise the first page of a PDF at 2× zoom for better OCR accuracy."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
    return Image.open(io.BytesIO(pix.tobytes("png")))


def _to_greyscale_image(file_bytes: bytes, content_type: str) -> Image.Image:
    """Return a greyscale PIL image regardless of input format."""
    if "pdf" in content_type:
        img = _pdf_first_page_to_image(file_bytes)
    else:
        img = Image.open(io.BytesIO(file_bytes))
    return img.convert("L")


# ── OCR ───────────────────────────────────────────────────────────────────────

def run_ocr(file_bytes: bytes, content_type: str) -> str:
    """Run Tesseract on the image and return raw text."""
    img = _to_greyscale_image(file_bytes, content_type)
    return pytesseract.image_to_string(img, config="--psm 6")


# ── Value extraction ──────────────────────────────────────────────────────────

def _find_amount(patterns: list[str], text: str) -> Optional[float]:
    """Try each regex pattern; return the first numeric match as float."""
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(",", "").strip()
            try:
                return float(raw)
            except ValueError:
                continue
    return None


def extract_values(text: str) -> ExtractedValues:
    """
    Parse OCR text and extract payslip fields.
    Patterns are intentionally broad to handle varied payslip layouts.
    Add more patterns here as you encounter new payslip formats.
    """
    gross = _find_amount([
        r"gross\s*(?:salary|pay|earnings)\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
        r"basic\s*(?:salary|pay)\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
        r"gross\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
    ], text)

    paye = _find_amount([
        r"p\.?a\.?y\.?e\.?\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
        r"income\s*tax\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
        r"tax\s*deducted\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
        r"paye\s*tax\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
    ], text)

    aids = _find_amount([
        r"aids\s*levy\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
        r"hiv\s*levy\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
    ], text)

    total_deductions = _find_amount([
        r"total\s*deductions?\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
        r"deductions?\s*total\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
    ], text)

    net = _find_amount([
        r"net\s*(?:pay|salary)\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
        r"take[\s\-]?home\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
        r"net\s*[:\-]?\s*\$?\s*([0-9,]+(?:\.\d{1,2})?)",
    ], text)

    return ExtractedValues(
        gross_salary=gross,
        paye=paye,
        aids_levy=aids,
        total_deductions=total_deductions,
        net_salary=net,
        raw_text_snippet=text[:500].strip(),
    )


# ── Comparison ────────────────────────────────────────────────────────────────

def _flag_and_explain(difference: float) -> tuple[str, str]:
    """Map a PAYE difference to a flag label and plain-English explanation."""
    abs_diff = abs(difference)

    if abs_diff <= FLAG_THRESHOLD:
        return (
            OK_LABEL,
            f"The PAYE on your payslip is within ${FLAG_THRESHOLD:.2f} of the estimate — "
            "within normal rounding tolerance. Your deductions look correct."
        )
    if difference > 0:
        return (
            OVER_DEDUCTION_LABEL,
            f"Your payslip shows ${abs_diff:.2f} more PAYE than our estimate. "
            "This may be due to taxable benefits, arrears, or a different tax period. "
            "We recommend confirming with your payroll department."
        )
    return (
        UNDER_DEDUCTION_LABEL,
        f"Your payslip shows ${abs_diff:.2f} less PAYE than our estimate. "
        "This could reflect exemptions, tax credits, or a different gross figure. "
        "Verify with your employer or a tax advisor."
    )


# ── Public entry point ────────────────────────────────────────────────────────

async def analyze_payslip(file_bytes: bytes, content_type: str) -> AnalysisResponse:
    """
    Full pipeline: OCR → extract → calculate → compare → flag.
    File bytes are never persisted.
    """
    # Step 1 — OCR
    try:
        raw_text = run_ocr(file_bytes, content_type)
    except Exception as exc:
        logger.warning("OCR failed: %s", exc)
        raw_text = ""

    # Step 2 — extract values from text
    extracted = extract_values(raw_text)

    # Step 3 — compare to expected (only if gross found)
    if not extracted.gross_salary:
        return AnalysisResponse(
            extracted_values=extracted,
            flag="Could not extract salary",
            explanation=(
                "We could not detect a gross salary figure in this document. "
                "Make sure the image is clear and labels like 'Gross Salary' are visible. "
                "Alternatively, use the manual calculator."
            ),
        )

    calc    = calculate_paye(extracted.gross_salary, "USD")
    expected = TaxResponse(**calc)

    if extracted.paye is None:
        return AnalysisResponse(
            extracted_values=extracted,
            expected_values=expected,
            flag="PAYE not found",
            explanation=(
                "Gross salary was detected but PAYE could not be extracted. "
                "Use the manual calculator to estimate your expected tax."
            ),
        )

    difference = round(extracted.paye - calc["paye_tax"], 2)
    flag, explanation = _flag_and_explain(difference)

    return AnalysisResponse(
        extracted_values=extracted,
        expected_values=expected,
        difference=difference,
        flag=flag,
        explanation=explanation,
    )
