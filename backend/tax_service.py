"""
tax_service.py — Zimbabwe PAYE calculation engine.

WHAT CHANGED (surgical edits only):
  Task 1 — USD_BANDS replaced with USD_ANNUAL_BANDS using official ZIMRA
            annual thresholds. calculate_paye() now converts monthly → annual,
            runs the band engine, then divides results back to monthly.
            Top rate corrected to 40%.
  Task 2 — NSSA deduction added: min(gross, 700) * 4.5%.
            "nssa" key added to return dict. net_salary now subtracts NSSA.
  Task 5 — Inline comments added throughout.
  Task 6 — Reference test values documented at the bottom.

WHAT DID NOT CHANGE:
  - Function names: calculate_paye(), build_tax_response()
  - Function signatures (same params, same types)
  - All original return keys: gross_salary, currency, paye_tax, aids_levy,
    total_tax, net_salary, tax_band, effective_rate
  - ZiG support (bands scaled proportionally)
  - build_tax_response() wrapper

Disclaimer: This tool provides estimated tax calculations and is
not affiliated with ZIMRA.
Reference: ZIMRA USD PAYE Tax Tables — effective 2024/25
"""

from schemas import TaxRequest, TaxResponse

# ─── Constants ────────────────────────────────────────────────────────────────
AIDS_LEVY_RATE = 0.03    # 3% of PAYE — applied to annual PAYE before monthly split
NSSA_RATE      = 0.045   # 4.5% employee NSSA contribution (Task 2)
NSSA_CAP       = 700.00  # monthly ceiling for NSSA calculation; only $700 is insurable

# ─── ZIMRA Annual Band Definitions (USD) ─────────────────────────────────────
# CHANGED: old monthly bands replaced with official ZIMRA annual thresholds.
#
# Format: (annual_upper_limit, marginal_rate, band_label)
# annual_upper_limit = None → top band ("and above")
#
# Monthly equivalents shown in labels for human readability.
USD_ANNUAL_BANDS = [
    (14_400.00,  0.00,  "0%  — monthly up to $1,200   (annual up to $14,400)"),
    (43_200.00,  0.20,  "20% — monthly $1,201–$3,600   (annual $14,401–$43,200)"),
    (144_000.00, 0.25,  "25% — monthly $3,601–$12,000  (annual $43,201–$144,000)"),
    (288_000.00, 0.30,  "30% — monthly $12,001–$24,000 (annual $144,001–$288,000)"),
    (432_000.00, 0.35,  "35% — monthly $24,001–$36,000 (annual $288,001–$432,000)"),
    (None,       0.40,  "40% — monthly above $36,000   (annual above $432,000)"),
]

# ZiG annual bands — scaled from USD at approximately 13.5 ZiG:USD
# CHANGED: proportionally updated to match new USD structure
ZIG_ANNUAL_BANDS = [
    (194_400.00,   0.00,  "0%  — annual up to ZiG 194,400"),
    (583_200.00,   0.20,  "20% — annual ZiG 194,401–583,200"),
    (1_944_000.00, 0.25,  "25% — annual ZiG 583,201–1,944,000"),
    (3_888_000.00, 0.30,  "30% — annual ZiG 1,944,001–3,888,000"),
    (5_832_000.00, 0.35,  "35% — annual ZiG 3,888,001–5,832,000"),
    (None,         0.40,  "40% — annual above ZiG 5,832,000"),
]


def _get_annual_bands(currency: str) -> list:
    """Return the correct annual band table for the requested currency."""
    return USD_ANNUAL_BANDS if currency == "USD" else ZIG_ANNUAL_BANDS


def _apply_progressive_bands(annual_income: float, bands: list) -> tuple[float, str]:
    """
    Core progressive band engine — operates on annual figures.

    For each band slice:
      - If annual_income fits within this band: tax the remainder at this rate, stop.
      - If annual_income exceeds this band: tax the full slice width, move to next band.

    Returns:
      (annual_paye: float, band_label: str)
    """
    annual_paye   = 0.0
    prev_ceiling  = 0.0          # lower boundary of current band slice
    band_label    = bands[-1][2] # default to top-band label

    for ceiling, rate, label in bands:
        if ceiling is None:
            # Top band — no upper limit; tax everything above the previous ceiling
            annual_paye += (annual_income - prev_ceiling) * rate
            band_label   = label
            break

        if annual_income <= ceiling:
            # Income sits inside this band — tax the slice from prev_ceiling to income
            annual_paye += (annual_income - prev_ceiling) * rate
            band_label   = label
            break

        # Income exceeds this band — tax the full band width and advance
        annual_paye  += (ceiling - prev_ceiling) * rate
        prev_ceiling  = ceiling

    return round(max(annual_paye, 0), 4), band_label  # 4dp here, round at the end


def calculate_paye(gross_salary: float, currency: str = "USD") -> dict:
    """
    Calculate monthly PAYE, AIDS levy, NSSA, and net salary.

    ALGORITHM (Task 1 — annual conversion):
      1. Annualise: annual_income = gross_salary * 12
      2. Run progressive band engine on annual_income → annual_paye
      3. Compute annual AIDS levy = annual_paye * 3%
      4. Convert both back to monthly (÷ 12)

    NSSA (Task 2 — new field, backward-compatible):
      nssa = min(gross_salary, NSSA_CAP) * NSSA_RATE
      nssa is subtracted from net_salary separately.

    RETURN KEYS — all original keys preserved, one new key added:
      gross_salary, currency, paye_tax, aids_levy, total_tax,
      net_salary, tax_band, effective_rate   ← original (unchanged)
      nssa                                   ← NEW (Task 2)
    """
    bands = _get_annual_bands(currency)

    # ── 1. Annualise the monthly gross ────────────────────────────────────────
    annual_income = gross_salary * 12

    # ── 2. Progressive PAYE on annual income ──────────────────────────────────
    annual_paye, band_label = _apply_progressive_bands(annual_income, bands)

    # ── 3. AIDS levy on annual PAYE ───────────────────────────────────────────
    annual_aids_levy = annual_paye * AIDS_LEVY_RATE

    # ── 4. Convert to monthly figures ─────────────────────────────────────────
    monthly_paye      = round(annual_paye / 12,       2)
    monthly_aids_levy = round(annual_aids_levy / 12,  2)
    monthly_total_tax = round(monthly_paye + monthly_aids_levy, 2)  # PAYE + levy only

    # ── NSSA: calculated monthly on actual gross, capped at $700 (Task 2) ─────
    nssa = round(min(gross_salary, NSSA_CAP) * NSSA_RATE, 2)

    # ── Net salary: gross minus PAYE tax, AIDS levy, AND NSSA ─────────────────
    net_salary = round(gross_salary - monthly_total_tax - nssa, 2)

    # ── Effective rate: all statutory deductions as % of gross ───────────────
    total_deductions = monthly_total_tax + nssa
    eff_rate = round(total_deductions / gross_salary * 100, 2) if gross_salary > 0 else 0.0

    return {
        # Original keys — values updated with corrected logic, names unchanged
        "gross_salary":   gross_salary,
        "currency":       currency,
        "paye_tax":       monthly_paye,
        "aids_levy":      monthly_aids_levy,
        "total_tax":      monthly_total_tax,   # PAYE + AIDS levy (not including NSSA)
        "net_salary":     net_salary,          # now correctly deducts NSSA too
        "tax_band":       band_label,
        "effective_rate": eff_rate,
        # New key (Task 2) — added without removing anything
        "nssa":           nssa,
    }


def build_tax_response(request: TaxRequest) -> TaxResponse:
    """
    Entry point called by the API route in main.py.
    Unchanged — still wraps calculate_paye() and returns TaxResponse.
    The extra 'nssa' key is silently ignored by TaxResponse via
    model_config extra='ignore', so no schema change is required here.
    """
    result = calculate_paye(request.salary, request.currency)
    return TaxResponse(**result)


# ─── Task 6 — Reference test values ──────────────────────────────────────────
# Verified expected outputs. Run: pytest test_tax_service.py -v
#
# ┌─────────────┬──────────────┬──────────────┬────────────┬────────────────┐
# │ gross/month │ monthly_paye │ monthly_aids │    nssa    │   net_salary   │
# ├─────────────┼──────────────┼──────────────┼────────────┼────────────────┤
# │   $500.00   │   $0.00      │   $0.00      │  $22.50    │   $477.50      │
# │  $1,500.00  │  $60.00      │   $1.80      │  $31.50    │ $1,406.70      │
# │  $4,000.00  │ $580.00      │  $17.40      │  $31.50    │ $3,371.10      │
# └─────────────┴──────────────┴──────────────┴────────────┴────────────────┘
#
# Workings:
# $500:  annual=6,000 → all in 0% band → paye=0
#        nssa = 500×4.5% = 22.50
#        net  = 500 - 0 - 0 - 22.50 = 477.50
#
# $1,500: annual=18,000
#        0%  band: 14,400 × 0.00  =    0.00
#        20% band:  3,600 × 0.20  =  720.00  → annual_paye = 720.00
#        monthly_paye = 720/12 = 60.00 | aids = 60×3% = 1.80
#        nssa = min(1500,700)×4.5% = 700×4.5% = 31.50
#        net  = 1500 - 60.00 - 1.80 - 31.50 = 1,406.70
#
# $4,000: annual=48,000
#        0%  band: 14,400 × 0.00  =      0.00
#        20% band: 28,800 × 0.20  =  5,760.00
#        25% band:  4,800 × 0.25  =  1,200.00  → annual_paye = 6,960.00
#        monthly_paye = 6960/12 = 580.00 | aids = 580×3% = 17.40
#        nssa = min(4000,700)×4.5% = 700×4.5% = 31.50
#        net  = 4000 - 580.00 - 17.40 - 31.50 = 3,371.10
