"""
test_tax_service.py — Unit tests for the PAYE calculation engine.

WHAT CHANGED:
  - Original tests kept, band assertions updated for new ZIMRA thresholds
  - Task 2 — NSSA tests added
  - Task 6 — three reference salary cases: $500, $1,500, $4,000
  - Band boundary tests added to verify annual threshold correctness

Run from the backend/ folder:
    pytest test_tax_service.py -v
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import pytest
from tax_service import calculate_paye, NSSA_CAP, NSSA_RATE


# ── Original tests (kept, some assertions updated for new bands) ───────────────

class TestPayeCalculation:

    def test_zero_tax_band(self):
        # $300/month = $3,600/year → inside 0% annual band (≤ $14,400)
        r = calculate_paye(300.00, "USD")
        assert r["paye_tax"] == 0.0
        assert r["aids_levy"] == 0.0

    def test_first_band_no_paye(self):
        # $1,200/month = $14,400/year → exactly at 0% ceiling → still 0 PAYE
        r = calculate_paye(1200.00, "USD")
        assert r["paye_tax"] == 0.0

    def test_spans_two_bands(self):
        # $1,500/month = $18,000/year
        # 0% band: 14,400 × 0% = 0
        # 20% band:  3,600 × 20% = 720 → monthly = 60.00
        r = calculate_paye(1500.00, "USD")
        assert r["paye_tax"] == 60.00

    def test_top_band_reached(self):
        r = calculate_paye(40_000.00, "USD")
        assert r["paye_tax"] > 0
        assert r["effective_rate"] > 30

    def test_aids_levy_always_3_pct(self):
        for salary in [500, 1500, 4000, 10000]:
            r = calculate_paye(float(salary), "USD")
            assert r["aids_levy"] == round(r["paye_tax"] * 0.03, 2)

    def test_net_equals_gross_minus_total_minus_nssa(self):
        for salary in [300, 1500, 4000, 6000]:
            r = calculate_paye(float(salary), "USD")
            expected_net = round(r["gross_salary"] - r["total_tax"] - r["nssa"], 2)
            assert r["net_salary"] == expected_net

    def test_total_equals_paye_plus_levy(self):
        r = calculate_paye(2500.00, "USD")
        assert r["total_tax"] == round(r["paye_tax"] + r["aids_levy"], 2)

    def test_zig_currency(self):
        r = calculate_paye(10000.00, "ZiG")
        assert r["currency"] == "ZiG"
        assert r["paye_tax"] >= 0

    def test_effective_rate_range(self):
        for salary in [300, 1500, 5000, 40000]:
            r = calculate_paye(float(salary), "USD")
            assert 0 <= r["effective_rate"] <= 55


# ── Task 2 — NSSA tests ───────────────────────────────────────────────────────

class TestNSSA:

    def test_nssa_below_cap(self):
        r = calculate_paye(500.00, "USD")
        assert r["nssa"] == round(500 * NSSA_RATE, 2)   # 22.50

    def test_nssa_at_cap(self):
        r = calculate_paye(700.00, "USD")
        assert r["nssa"] == round(700 * NSSA_RATE, 2)   # 31.50

    def test_nssa_above_cap(self):
        r = calculate_paye(5000.00, "USD")
        assert r["nssa"] == round(NSSA_CAP * NSSA_RATE, 2)   # 31.50

    def test_nssa_key_present(self):
        for salary in [300, 1200, 5000]:
            r = calculate_paye(float(salary), "USD")
            assert "nssa" in r

    def test_nssa_not_in_total_tax(self):
        r = calculate_paye(3000.00, "USD")
        assert r["total_tax"] == round(r["paye_tax"] + r["aids_levy"], 2)


# ── Task 6 — Reference values ─────────────────────────────────────────────────

@pytest.mark.parametrize("gross,exp_paye,exp_aids,exp_nssa,exp_net", [
    # $500: annual=6,000 → 0% band → paye=0, aids=0
    # nssa=500×4.5%=22.50 | net=500-0-0-22.50=477.50
    (500.00,    0.00,   0.00,  22.50,  477.50),
    # $1,500: annual=18,000 | 0%:14400×0=0 | 20%:3600×20%=720 → month=60
    # aids=60×3%=1.80 | nssa=min(1500,700)×4.5%=31.50 | net=1406.70
    (1500.00,  60.00,   1.80,  31.50, 1406.70),
    # $4,000: annual=48,000 | 0%:14400×0 | 20%:28800×20%=5760 | 25%:4800×25%=1200
    # annual_paye=6960 → month=580 | aids=17.40 | nssa=31.50 | net=3371.10
    (4000.00, 580.00,  17.40,  31.50, 3371.10),
])
def test_task6_reference_values(gross, exp_paye, exp_aids, exp_nssa, exp_net):
    r = calculate_paye(gross, "USD")
    assert r["paye_tax"]   == exp_paye,  f"PAYE at ${gross}: expected {exp_paye}, got {r['paye_tax']}"
    assert r["aids_levy"]  == exp_aids,  f"AIDS at ${gross}: expected {exp_aids}, got {r['aids_levy']}"
    assert r["nssa"]       == exp_nssa,  f"NSSA at ${gross}: expected {exp_nssa}, got {r['nssa']}"
    assert r["net_salary"] == exp_net,   f"Net  at ${gross}: expected {exp_net}, got {r['net_salary']}"


# ── Band boundary tests ───────────────────────────────────────────────────────

@pytest.mark.parametrize("monthly,expect_paye_gt_zero", [
    (1200.00, False),   # exactly at 0% annual ceiling ($14,400)
    (1201.00, True),    # $1 into 20% band
    (3600.00, True),    # top of 20% band ($43,200/yr)
    (3601.00, True),    # into 25% band
])
def test_band_boundaries(monthly, expect_paye_gt_zero):
    r = calculate_paye(monthly, "USD")
    if expect_paye_gt_zero:
        assert r["paye_tax"] > 0, f"Expected PAYE > 0 at ${monthly}/month"
    else:
        assert r["paye_tax"] == 0.0, f"Expected PAYE = 0 at ${monthly}/month"
