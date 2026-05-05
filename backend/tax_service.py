"""
tax_service.py — Zimbabwe PAYE calculation engine.

Progressive tax bands representative of Zimbabwe's PAYE structure.
Bands are illustrative — update USD_BANDS / ZIG_BANDS each tax year
from the latest ZIMRA Tariff Schedule.

Reference: ZIMRA PAYE Tax Tables (USD — effective 2024/25)
"""

from schemas import TaxRequest, TaxResponse

# ─── Tax Band Definitions ──────────────────────────────────────────────────────
# Each tuple: (monthly_upper_limit, marginal_rate, description)
# upper_limit = None means "and above" (top band)

USD_BANDS = [
    (300.00,    0.00,  "0% — Up to $300"),
    (700.00,    0.20,  "20% — $301 to $700"),
    (1_500.00,  0.25,  "25% — $701 to $1,500"),
    (3_000.00,  0.30,  "30% — $1,501 to $3,000"),
    (None,      0.35,  "35% — Above $3,000"),
]

# ZiG bands scaled from USD using ~13.5 ZiG:USD exchange rate
ZIG_BANDS = [
    (4_050.00,   0.00,  "0% — Up to ZiG 4,050"),
    (9_450.00,   0.20,  "20% — ZiG 4,051–9,450"),
    (20_250.00,  0.25,  "25% — ZiG 9,451–20,250"),
    (40_500.00,  0.30,  "30% — ZiG 20,251–40,500"),
    (None,       0.35,  "35% — Above ZiG 40,500"),
]

AIDS_LEVY_RATE = 0.03   # 3% of PAYE (all bands)


def _get_bands(currency: str) -> list:
    return USD_BANDS if currency == "USD" else ZIG_BANDS


def calculate_paye(gross_salary: float, currency: str = "USD") -> dict:
    """
    Calculate monthly PAYE using progressive bands.
    Returns a plain dict with all tax components.
    """
    bands = _get_bands(currency)
    paye = 0.0
    prev = 0.0
    band_label = bands[-1][2]

    for upper, rate, label in bands:
        if upper is None:
            paye += (gross_salary - prev) * rate
            band_label = label
            break
        if gross_salary <= upper:
            paye += (gross_salary - prev) * rate
            band_label = label
            break
        paye += (upper - prev) * rate
        prev = upper

    paye        = round(max(paye, 0), 2)
    aids_levy   = round(paye * AIDS_LEVY_RATE, 2)
    total_tax   = round(paye + aids_levy, 2)
    net_salary  = round(gross_salary - total_tax, 2)
    eff_rate    = round(total_tax / gross_salary * 100, 2) if gross_salary > 0 else 0.0

    return {
        "gross_salary":   gross_salary,
        "currency":       currency,
        "paye_tax":       paye,
        "aids_levy":      aids_levy,
        "total_tax":      total_tax,
        "net_salary":     net_salary,
        "tax_band":       band_label,
        "effective_rate": eff_rate,
    }


def build_tax_response(request: TaxRequest) -> TaxResponse:
    """Entry point for the API route — returns a TaxResponse Pydantic model."""
    result = calculate_paye(request.salary, request.currency)
    return TaxResponse(**result)
