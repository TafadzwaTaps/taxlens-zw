"""
import_duty_service.py — Zimbabwe Import Duty Calculator.
NEW FILE. Does not touch existing files.

Duty rates are illustrative estimates based on ZIMRA tariff schedules.
All rates should be verified against the latest ZIMRA tariff book.
"""

from schemas_payroll import ImportDutyRequest, ImportDutyResponse

# ── Duty rate table ───────────────────────────────────────────────────────────
# Format: category → {duty_rate, surtax_rate, label}
# Rates are percentage decimals (0.40 = 40%)
DUTY_RATES = {
    "electronics": {
        "duty":    0.25,
        "surtax":  0.10,
        "label":   "Electronics & Electrical Appliances",
        "note":    "Includes phones, laptops, TVs, audio equipment",
    },
    "clothing": {
        "duty":    0.40,
        "surtax":  0.05,
        "label":   "Clothing & Textiles",
        "note":    "Includes garments, footwear, accessories",
    },
    "vehicle": {
        "duty":    0.40,
        "surtax":  0.25,
        "label":   "Motor Vehicles",
        "note":    "Additional carbon tax may apply for older vehicles",
    },
    "furniture": {
        "duty":    0.40,
        "surtax":  0.10,
        "label":   "Furniture & Household Goods",
        "note":    "Includes wooden, metal, and upholstered furniture",
    },
    "food": {
        "duty":    0.10,
        "surtax":  0.00,
        "label":   "Food & Beverages",
        "note":    "Basic foodstuffs may be zero-rated; processed foods vary",
    },
    "cosmetics": {
        "duty":    0.40,
        "surtax":  0.05,
        "label":   "Cosmetics & Personal Care",
        "note":    "Includes perfumes, makeup, skincare products",
    },
    "other": {
        "duty":    0.20,
        "surtax":  0.05,
        "label":   "General Goods",
        "note":    "Default rate — actual rate depends on HS tariff code",
    },
}

ZW_VAT_RATE = 0.145   # Zimbabwe standard VAT rate: 14.5%


def calculate_import_duty(request: ImportDutyRequest) -> ImportDutyResponse:
    """
    Estimate Zimbabwe import duties and total landed cost.

    Algorithm:
      1. CIF = item_value + shipping + insurance
      2. duty_amount = CIF × duty_rate
      3. vat_amount  = (CIF + duty_amount) × 14.5%
      4. surtax      = CIF × surtax_rate
      5. total_import_cost = CIF + duty + VAT + surtax
      6. total_landed_cost = same as total_import_cost (CIF already included)
    """
    rates = DUTY_RATES.get(request.category, DUTY_RATES["other"])

    # ── CIF (Cost, Insurance, Freight) ────────────────────────────────────────
    cif = round(request.item_value_usd + request.shipping_usd + request.insurance_usd, 2)

    # ── Duty ──────────────────────────────────────────────────────────────────
    duty_rate   = rates["duty"]
    duty_amount = round(cif * duty_rate, 2)

    # ── VAT — levied on CIF + duty ────────────────────────────────────────────
    vat_base    = cif + duty_amount
    vat_amount  = round(vat_base * ZW_VAT_RATE, 2)

    # ── Surtax ────────────────────────────────────────────────────────────────
    surtax_amount = round(cif * rates["surtax"], 2)

    # ── Totals ────────────────────────────────────────────────────────────────
    total_import_cost = round(cif + duty_amount + vat_amount + surtax_amount, 2)

    breakdown = {
        "cif_value":         cif,
        "duty_rate_pct":     f"{duty_rate * 100:.0f}%",
        "duty_amount":       duty_amount,
        "vat_rate_pct":      f"{ZW_VAT_RATE * 100:.1f}%",
        "vat_amount":        vat_amount,
        "surtax_rate_pct":   f"{rates['surtax'] * 100:.0f}%",
        "surtax_amount":     surtax_amount,
        "category_note":     rates["note"],
    }

    return ImportDutyResponse(
        category=rates["label"],
        cif_value=cif,
        duty_rate=duty_rate,
        duty_amount=duty_amount,
        vat_rate=ZW_VAT_RATE,
        vat_amount=vat_amount,
        surtax_amount=surtax_amount,
        total_import_cost=total_import_cost,
        total_landed_cost=total_import_cost,
        breakdown=breakdown,
    )
