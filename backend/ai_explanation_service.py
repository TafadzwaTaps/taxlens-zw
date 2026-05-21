"""
ai_explanation_service.py — Rule-based payslip explanation engine.
NEW FILE.

Generates human-readable explanations for tax deductions.
Architecture is AI-ready: swap _rule_engine() for an LLM call later
without changing any public function signatures.

No calculations are performed here — only explanation generation.
"""

from typing import Optional


def explain_tax_breakdown(
    gross_salary: float,
    paye_tax: float,
    aids_levy: float,
    nssa: float,
    net_salary: float,
    effective_rate: float,
    tax_band: str,
    currency: str = "USD",
    prev_gross: Optional[float] = None,
    prev_paye: Optional[float] = None,
) -> dict:
    """
    Generate plain-English explanations for a payslip's deductions.

    Returns a dict with:
      summary        — one-sentence overview
      paye_explain   — why PAYE is what it is
      aids_explain   — what AIDS levy is
      nssa_explain   — what NSSA is
      net_explain    — how net was calculated
      anomaly        — change vs previous period (if provided)
      whatsapp_msg   — pre-formatted WhatsApp share text
    """
    sym = "$" if currency == "USD" else "ZiG "
    f   = lambda v: f"{sym}{v:,.2f}"

    # ── Summary ───────────────────────────────────────────────────────────────
    summary = (
        f"On a gross salary of {f(gross_salary)}, your estimated total deductions are "
        f"{f(paye_tax + aids_levy + nssa)} ({effective_rate:.1f}% of gross), "
        f"leaving you with an estimated take-home of {f(net_salary)}."
    )

    # ── PAYE explanation ──────────────────────────────────────────────────────
    if paye_tax == 0:
        paye_explain = (
            f"No PAYE is deducted at your salary level ({f(gross_salary)}/month). "
            "Your annual income falls within the tax-free threshold of $14,400/year ($1,200/month)."
        )
    else:
        paye_explain = (
            f"Your PAYE of {f(paye_tax)}/month is calculated by applying Zimbabwe's progressive "
            f"tax bands to your annualised income. You are currently in the {tax_band.split('—')[0].strip()} "
            f"bracket. Progressive taxation means only the income above each threshold is taxed "
            "at the higher rate — not your entire salary."
        )

    # ── AIDS levy explanation ─────────────────────────────────────────────────
    aids_explain = (
        f"The AIDS levy of {f(aids_levy)}/month is 3% of your PAYE tax ({f(paye_tax)}). "
        "This statutory levy was introduced by the Government of Zimbabwe to fund "
        "the National AIDS Council's programmes."
    )

    # ── NSSA explanation ──────────────────────────────────────────────────────
    nssa_explain = (
        f"Your NSSA contribution of {f(nssa)}/month is 4.5% of your gross salary "
        f"(capped at $700/month insurable earnings). This contributes to Zimbabwe's "
        "National Social Security Authority, which funds pension and accident benefits."
    )

    # ── Net salary explanation ────────────────────────────────────────────────
    net_explain = (
        f"Your estimated take-home pay of {f(net_salary)} is your gross salary ({f(gross_salary)}) "
        f"minus PAYE ({f(paye_tax)}), AIDS levy ({f(aids_levy)}), and NSSA ({f(nssa)}). "
        "Other deductions such as medical aid, pension top-ups, or loan repayments "
        "would reduce this further depending on your employment contract."
    )

    # ── Anomaly detection (vs previous period) ────────────────────────────────
    anomaly = None
    if prev_gross is not None and prev_paye is not None:
        gross_change = gross_salary - prev_gross
        paye_change  = paye_tax - prev_paye
        if abs(gross_change) > 0.01:
            direction = "increased" if gross_change > 0 else "decreased"
            anomaly = (
                f"Your gross salary {direction} by {f(abs(gross_change))} compared to last period. "
                f"This caused your PAYE to {'increase' if paye_change > 0 else 'decrease'} "
                f"by {f(abs(paye_change))}. "
            )
            if paye_change > 0 and gross_change > 0:
                anomaly += (
                    "Because Zimbabwe uses progressive tax bands, a salary increase can push "
                    "part of your income into a higher tax bracket, making the PAYE rise "
                    "proportionally faster than the gross increase."
                )
        else:
            anomaly = "Your salary is unchanged from the previous period."

    # ── WhatsApp message ──────────────────────────────────────────────────────
    whatsapp_msg = (
        f"📊 *TaxLens Zimbabwe — Tax Estimate*\n\n"
        f"💰 Gross Salary:    {f(gross_salary)}\n"
        f"🏛️  PAYE Tax:        {f(paye_tax)}\n"
        f"🔴 AIDS Levy:       {f(aids_levy)}\n"
        f"🛡️  NSSA:            {f(nssa)}\n"
        f"✅ *Net Take-Home:  {f(net_salary)}*\n\n"
        f"Effective rate: {effective_rate:.1f}% | Band: {tax_band.split('—')[0].strip()}\n\n"
        "_Estimates only. Not affiliated with ZIMRA._\n"
        "Calculate yours: https://taxlens.co.zw"
    )

    return {
        "summary":       summary,
        "paye_explain":  paye_explain,
        "aids_explain":  aids_explain,
        "nssa_explain":  nssa_explain,
        "net_explain":   net_explain,
        "anomaly":       anomaly,
        "whatsapp_msg":  whatsapp_msg,
    }


def explain_discrepancy(
    flag: str,
    difference: float,
    expected_paye: float,
    actual_paye: float,
    confidence_level: str = "medium",
    currency: str = "USD",
) -> str:
    """
    Generate a plain-English explanation for an OCR payslip discrepancy.
    Returns a single string suitable for display in an explanation card.
    """
    sym = "$" if currency == "USD" else "ZiG "
    f   = lambda v: f"{sym}{v:,.2f}"

    base = (
        f"We estimated your PAYE at {f(expected_paye)}, but your payslip shows {f(actual_paye)} "
        f"— a difference of {f(abs(difference))}. "
    )

    if flag == "OK":
        return base + (
            "This small difference is within normal rounding tolerance and is not a cause for concern."
        )
    elif "Minor" in flag:
        return base + (
            "This is a minor difference that may be caused by timing adjustments, "
            "rounding between payroll systems, or employer-specific allowances. "
            "We recommend confirming with your payroll department if you are unsure."
        )
    else:
        return base + (
            "This is a notable difference. Common reasons include additional taxable benefits, "
            "pension contributions, loan repayments, or a different gross salary basis "
            "than the one we detected. Please verify this with your employer or a qualified "
            "tax advisor. This tool provides estimates only and is not affiliated with ZIMRA."
        )
