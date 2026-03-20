"""Tests for pricing engine."""

import pytest

from app.services.pricing import calculate_estimate_total, calculate_line_total


class TestLineTotal:
    def test_basic_calculation(self):
        subtotal, coefs = calculate_line_total(unit_price=1000, quantity=2)
        assert subtotal == 2000
        assert coefs == {}

    def test_with_coefficient(self):
        subtotal, coefs = calculate_line_total(
            unit_price=1000, quantity=1,
            coefficients={"urgent": 1.2},
        )
        assert subtotal == 1200
        assert coefs == {"urgent": 1.2}

    def test_multiple_coefficients(self):
        subtotal, coefs = calculate_line_total(
            unit_price=1000, quantity=2,
            coefficients={"urgent": 1.2, "wall_concrete": 1.3},
        )
        # 1000 * 2 * 1.2 * 1.3 = 3120
        assert subtotal == 3120

    def test_quantity_fractional(self):
        subtotal, _ = calculate_line_total(unit_price=300, quantity=5.5)
        assert subtotal == 1650

    def test_zero_quantity(self):
        subtotal, _ = calculate_line_total(unit_price=1000, quantity=0)
        assert subtotal == 0


class TestEstimateTotal:
    def test_basic_total(self):
        result = calculate_estimate_total([
            {"unit_price": 1000, "quantity": 2},
            {"unit_price": 500, "quantity": 1},
        ])
        assert result["total"] == 2500
        assert result["discount"] == 0
        assert result["final"] == 2500

    def test_with_percent_discount(self):
        result = calculate_estimate_total(
            [{"unit_price": 1000, "quantity": 10}],
            [{"type": "percent", "value": 10}],
        )
        assert result["total"] == 10000
        assert result["discount"] == 1000
        assert result["final"] == 9000

    def test_with_fixed_discount(self):
        result = calculate_estimate_total(
            [{"unit_price": 1000, "quantity": 5}],
            [{"type": "fixed", "value": 500}],
        )
        assert result["total"] == 5000
        assert result["discount"] == 500
        assert result["final"] == 4500

    def test_discount_cannot_exceed_total(self):
        result = calculate_estimate_total(
            [{"unit_price": 100, "quantity": 1}],
            [{"type": "fixed", "value": 500}],
        )
        assert result["discount"] == 100  # Capped at total
        assert result["final"] == 0

    def test_multiple_items_with_coefficients(self):
        result = calculate_estimate_total([
            {"unit_price": 330, "quantity": 5, "coefficients": {"wall_concrete": 1.3}},
            {"unit_price": 830, "quantity": 1},
            {"unit_price": 490, "quantity": 3, "coefficients": {"urgent": 1.2}},
        ])
        # 330*5*1.3 = 2145; 830*1 = 830; 490*3*1.2 = 1764
        assert result["total"] == 2145 + 830 + 1764
        assert result["final"] == result["total"]

    def test_empty_estimate(self):
        result = calculate_estimate_total([])
        assert result["total"] == 0
        assert result["final"] == 0
