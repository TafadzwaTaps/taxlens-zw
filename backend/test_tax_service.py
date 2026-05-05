"""
test_tax_service.py — Unit tests for the PAYE calculation engine.
Run from the backend/ folder: pytest test_tax_service.py -v
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from tax_service import calculate_paye
import pytest


class TestPayeCalculation:

    def test_zero_tax_band(self):
        r = calculate_paye(300.00, "USD")
        assert r["paye_tax"] == 0.0
        assert r["aids_levy"] == 0.0
        assert r["net_salary"] == 300.0

    def test_second_band_only(self):
        # $500: only $200 above $300 taxed at 20%
        r = calculate_paye(500.00, "USD")
        assert r["paye_tax"] == 40.0
        assert r["aids_levy"] == round(40.0 * 0.03, 2)

    def test_spans_two_bands(self):
        # $1000: $400 @ 20% = $80, $300 @ 25% = $75 → $155
        r = calculate_paye(1000.00, "USD")
        assert r["paye_tax"] == 155.0

    def test_top_band(self):
        r = calculate_paye(5000.00, "USD")
        assert r["paye_tax"] > 0
        assert r["effective_rate"] > 25

    def test_aids_levy_always_3_pct(self):
        for salary in [500, 1000, 2000, 5000]:
            r = calculate_paye(float(salary), "USD")
            assert r["aids_levy"] == round(r["paye_tax"] * 0.03, 2)

    def test_net_equals_gross_minus_total(self):
        for salary in [300, 700, 1500, 3000, 6000]:
            r = calculate_paye(float(salary), "USD")
            assert r["net_salary"] == round(r["gross_salary"] - r["total_tax"], 2)

    def test_total_equals_paye_plus_levy(self):
        r = calculate_paye(2500.00, "USD")
        assert r["total_tax"] == round(r["paye_tax"] + r["aids_levy"], 2)

    def test_zig_currency(self):
        r = calculate_paye(10000.00, "ZiG")
        assert r["currency"] == "ZiG"
        assert r["paye_tax"] >= 0

    def test_effective_rate_range(self):
        for salary in [300, 1000, 5000, 10000]:
            r = calculate_paye(float(salary), "USD")
            assert 0 <= r["effective_rate"] <= 40


@pytest.mark.parametrize("gross,expected_paye", [
    (300,    0),
    (500,   40),
    (700,   80),
    (1000, 155),
    (1500, 280),
    (3000, 730),
])
def test_known_values(gross, expected_paye):
    r = calculate_paye(float(gross), "USD")
    assert abs(r["paye_tax"] - expected_paye) < 1.0, (
        f"${gross}: expected ~{expected_paye}, got {r['paye_tax']}"
    )
