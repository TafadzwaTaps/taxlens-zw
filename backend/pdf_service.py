"""
pdf_service.py — PDF generation for TaxLens Zimbabwe.
NEW FILE.

Generates professional PDFs for:
  - Individual payslip / tax breakdown
  - Payroll run summary
  - OCR analysis report

Uses ReportLab (pure Python, no system dependencies).
Add to requirements.txt: reportlab==4.2.2
"""

import io
from datetime import datetime
from typing import Optional, List

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    )
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


# ── Colour palette (matches frontend dark theme on paper) ─────────────────────
GOLD  = colors.HexColor("#D4A017")
DARK  = colors.HexColor("#1C201C")
GREEN = colors.HexColor("#4CAF50")
RED   = colors.HexColor("#FF6B6B")
GREY  = colors.HexColor("#A8B5A8")
WHITE = colors.white


def _check_reportlab():
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError(
            "ReportLab is not installed. Add 'reportlab==4.2.2' to requirements.txt "
            "and redeploy."
        )


def _header_table(title: str, subtitle: str) -> "Table":
    """Reusable branded header for all PDF types."""
    data = [[
        Paragraph(f"<b>TaxLens Zimbabwe</b>", ParagraphStyle(
            "Brand", fontName="Helvetica-Bold", fontSize=16, textColor=GOLD
        )),
        Paragraph(
            f"<b>{title}</b><br/><font size=9 color='grey'>{subtitle}</font>",
            ParagraphStyle("Title", fontName="Helvetica-Bold", fontSize=13, alignment=2)
        ),
    ]]
    t = Table(data, colWidths=[9 * cm, 9 * cm])
    t.setStyle(TableStyle([
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW",   (0, 0), (-1, 0),  1, GOLD),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
    ]))
    return t


def generate_payslip_pdf(
    gross_salary: float,
    paye_tax: float,
    aids_levy: float,
    nssa: float,
    total_tax: float,
    net_salary: float,
    effective_rate: float,
    tax_band: str,
    currency: str = "USD",
    employee_name: Optional[str] = None,
    period: Optional[str] = None,
    company_name: Optional[str] = "Your Company",
) -> bytes:
    """
    Generate a professional payslip PDF.
    Returns raw bytes suitable for a FastAPI StreamingResponse.
    """
    _check_reportlab()
    buf    = io.BytesIO()
    doc    = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm,
                               topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    sym    = "$" if currency == "USD" else "ZiG "
    f      = lambda v: f"{sym}{v:,.2f}"
    story  = []

    period_str = period or datetime.now().strftime("%B %Y")

    story.append(_header_table("PAY ADVICE SLIP", f"{company_name} — {period_str}"))
    story.append(Spacer(1, 0.5 * cm))

    if employee_name:
        story.append(Paragraph(
            f"<b>Employee:</b> {employee_name}",
            ParagraphStyle("Info", fontName="Helvetica", fontSize=10)
        ))
        story.append(Spacer(1, 0.3 * cm))

    # Earnings table
    earnings_data = [
        ["EARNINGS", "AMOUNT"],
        ["Gross Salary", f(gross_salary)],
    ]
    deductions_data = [
        ["DEDUCTIONS", "AMOUNT"],
        ["PAYE Tax", f(paye_tax)],
        ["AIDS Levy (3% of PAYE)", f(aids_levy)],
        ["NSSA Contribution", f(nssa)],
        ["Total Deductions", f(total_tax + nssa)],
    ]
    summary_data = [
        ["NET PAY", f(net_salary)],
        ["Effective Tax Rate", f"{effective_rate:.2f}%"],
        ["Active Tax Band", tax_band.split("—")[0].strip()],
    ]

    def _make_table(data, header_bg=DARK):
        t = Table(data, colWidths=[12 * cm, 5 * cm])
        style = [
            ("BACKGROUND",  (0, 0), (-1, 0),  header_bg),
            ("TEXTCOLOR",   (0, 0), (-1, 0),  GOLD),
            ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",    (0, 0), (-1, 0),  10),
            ("ALIGN",       (1, 0), (1, -1),  "RIGHT"),
            ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE",    (0, 1), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
            ("GRID",        (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING",  (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]
        t.setStyle(TableStyle(style))
        return t

    story.append(_make_table(earnings_data))
    story.append(Spacer(1, 0.4 * cm))
    story.append(_make_table(deductions_data))
    story.append(Spacer(1, 0.4 * cm))

    # Net pay highlight
    net_table = Table(summary_data, colWidths=[12 * cm, 5 * cm])
    net_table.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0),  GREEN),
        ("TEXTCOLOR",   (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",    (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (0, 0),   12),
        ("ALIGN",       (1, 0), (1, -1),  "RIGHT"),
        ("FONTSIZE",    (0, 1), (-1, -1), 9),
        ("GRID",        (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",  (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(net_table)
    story.append(Spacer(1, 0.8 * cm))

    story.append(Paragraph(
        "<i>This document contains estimated tax figures generated by TaxLens Zimbabwe. "
        "It is not an official ZIMRA document. Always consult a qualified tax professional.</i>",
        ParagraphStyle("Disclaimer", fontName="Helvetica-Oblique", fontSize=7, textColor=GREY)
    ))

    doc.build(story)
    return buf.getvalue()


def generate_payroll_summary_pdf(
    run_data: dict,
    employee_rows: List[dict],
    company_name: str = "Your Company",
) -> bytes:
    """
    Generate a payroll run summary PDF.
    run_data: dict with totals (total_gross, total_paye, etc.)
    employee_rows: list of per-employee payroll dicts
    """
    _check_reportlab()
    buf  = io.BytesIO()
    doc  = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm,
                             topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    f      = lambda v: f"${v:,.2f}"
    period = f"{run_data.get('period_month', '')}/{run_data.get('period_year', '')}"
    story  = []

    story.append(_header_table("PAYROLL SUMMARY", f"{company_name} — {period}"))
    story.append(Spacer(1, 0.5 * cm))

    # Totals
    totals = [
        ["METRIC",              "TOTAL"],
        ["Employees",           str(run_data.get("employee_count", 0))],
        ["Total Gross",         f(run_data.get("total_gross", 0))],
        ["Total PAYE",          f(run_data.get("total_paye", 0))],
        ["Total AIDS Levy",     f(run_data.get("total_aids_levy", 0))],
        ["Total NSSA",          f(run_data.get("total_nssa", 0))],
        ["Total Net Payable",   f(run_data.get("total_net", 0))],
    ]
    t = Table(totals, colWidths=[12*cm, 5*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), DARK),
        ("TEXTCOLOR",     (0, 0), (-1, 0), GOLD),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 10),
        ("ALIGN",         (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), 9),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.6*cm))

    # Per-employee breakdown
    if employee_rows:
        story.append(Paragraph(
            "<b>Employee Breakdown</b>",
            ParagraphStyle("SH", fontName="Helvetica-Bold", fontSize=10)
        ))
        story.append(Spacer(1, 0.3*cm))
        headers = ["Name", "Gross", "PAYE", "NSSA", "AIDS", "Net"]
        rows    = [headers] + [
            [
                e.get("employee_name", "—"),
                f(e.get("gross_salary", 0)),
                f(e.get("paye_tax", 0)),
                f(e.get("nssa", 0)),
                f(e.get("aids_levy", 0)),
                f(e.get("net_salary", 0)),
            ]
            for e in employee_rows
        ]
        et = Table(rows, colWidths=[5*cm, 2.5*cm, 2.5*cm, 2*cm, 2*cm, 2.5*cm])
        et.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), DARK),
            ("TEXTCOLOR",     (0, 0), (-1, 0), GOLD),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 8),
            ("ALIGN",         (1, 0), (-1, -1), "RIGHT"),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ]))
        story.append(et)

    story.append(Spacer(1, 0.8*cm))
    story.append(Paragraph(
        "<i>Estimates only. Not an official ZIMRA document.</i>",
        ParagraphStyle("D", fontName="Helvetica-Oblique", fontSize=7, textColor=GREY)
    ))
    doc.build(story)
    return buf.getvalue()
