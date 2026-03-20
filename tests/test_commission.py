"""Tests for commission calculation engine."""

from decimal import Decimal

import pytest

from app.services.commission import CommissionBreakdown, calculate_commission


class TestCommissionCalculation:
    def test_basic_commission_10000(self):
        """Standard case: 10000₽, 20% platform, 5% senior, 5% admin."""
        result = calculate_commission(
            gross_total=10000,
            platform_fee_pct=Decimal("20.0"),
            senior_master_share_pct=Decimal("5.0"),
            admin_share_pct=Decimal("5.0"),
            senior_master_id=1,
            admin_id=2,
        )
        assert result.gross_total == 10000
        assert result.net_total == 10000
        assert result.platform_fee == 2000
        assert result.senior_master_share == 500
        assert result.admin_share == 500
        assert result.platform_net == 1000
        assert result.master_net == 8000
        # Verify: all parts sum to gross
        assert result.master_net + result.platform_fee == result.gross_total
        assert result.senior_master_share + result.admin_share + result.platform_net == result.platform_fee

    def test_commission_with_discount(self):
        """Commission calculated on net (after discount)."""
        result = calculate_commission(
            gross_total=10000,
            discount_total=2000,
            platform_fee_pct=Decimal("20.0"),
            senior_master_share_pct=Decimal("5.0"),
            admin_share_pct=Decimal("5.0"),
            senior_master_id=1,
            admin_id=2,
        )
        assert result.net_total == 8000
        assert result.platform_fee == 1600  # 20% of 8000
        assert result.senior_master_share == 400  # 5% of 8000
        assert result.admin_share == 400  # 5% of 8000
        assert result.platform_net == 800  # 1600 - 400 - 400
        assert result.master_net == 6400  # 8000 - 1600

    def test_no_senior_master(self):
        """When master is directly under admin, no senior share."""
        result = calculate_commission(
            gross_total=5000,
            platform_fee_pct=Decimal("20.0"),
            senior_master_share_pct=Decimal("5.0"),
            admin_share_pct=Decimal("5.0"),
            senior_master_id=None,
            admin_id=2,
        )
        assert result.senior_master_share == 0
        assert result.admin_share == 250  # 5% of 5000
        assert result.platform_fee == 1000
        assert result.platform_net == 750  # 1000 - 0 - 250
        assert result.master_net == 4000

    def test_no_admin_share(self):
        """When admin share is not configured."""
        result = calculate_commission(
            gross_total=5000,
            platform_fee_pct=Decimal("20.0"),
            senior_master_share_pct=Decimal("5.0"),
            admin_share_pct=Decimal("5.0"),
            senior_master_id=1,
            admin_id=None,
        )
        assert result.admin_share == 0
        assert result.senior_master_share == 250
        assert result.platform_net == 750  # 1000 - 250

    def test_zero_order(self):
        result = calculate_commission(
            gross_total=0,
            platform_fee_pct=Decimal("20.0"),
        )
        assert result.platform_fee == 0
        assert result.master_net == 0

    def test_small_order_rounding(self):
        """Rounding should be correct for small amounts."""
        result = calculate_commission(
            gross_total=150,
            platform_fee_pct=Decimal("20.0"),
            senior_master_share_pct=Decimal("5.0"),
            admin_share_pct=Decimal("5.0"),
            senior_master_id=1,
            admin_id=2,
        )
        assert result.platform_fee == 30
        assert result.senior_master_share == 8  # 150 * 5% = 7.5 → 8
        assert result.admin_share == 8
        assert result.platform_net == 14  # 30 - 8 - 8
        assert result.master_net == 120

    def test_large_order(self):
        result = calculate_commission(
            gross_total=100000,
            platform_fee_pct=Decimal("20.0"),
            senior_master_share_pct=Decimal("5.0"),
            admin_share_pct=Decimal("5.0"),
            senior_master_id=1,
            admin_id=2,
        )
        assert result.platform_fee == 20000
        assert result.senior_master_share == 5000
        assert result.admin_share == 5000
        assert result.master_net == 80000

    def test_custom_fee_percentage(self):
        result = calculate_commission(
            gross_total=10000,
            platform_fee_pct=Decimal("15.0"),
            senior_master_share_pct=Decimal("3.0"),
            admin_share_pct=Decimal("2.0"),
            senior_master_id=1,
            admin_id=2,
        )
        assert result.platform_fee == 1500
        assert result.senior_master_share == 300
        assert result.admin_share == 200
        assert result.platform_net == 1000
        assert result.master_net == 8500

    def test_invariant_parts_sum_to_gross(self):
        """master_net + platform_fee must always equal net_total."""
        for gross in [100, 500, 1000, 7777, 10000, 99999]:
            result = calculate_commission(
                gross_total=gross,
                platform_fee_pct=Decimal("20.0"),
                senior_master_share_pct=Decimal("5.0"),
                admin_share_pct=Decimal("5.0"),
                senior_master_id=1,
                admin_id=2,
            )
            assert result.master_net + result.platform_fee == result.net_total
            assert result.platform_net >= 0

    def test_safety_platform_net_never_negative(self):
        """Even with extreme shares, platform_net should not go negative."""
        result = calculate_commission(
            gross_total=1000,
            platform_fee_pct=Decimal("10.0"),  # 100₽ fee
            senior_master_share_pct=Decimal("8.0"),  # 80₽
            admin_share_pct=Decimal("8.0"),  # 80₽ → would be 160 > 100
            senior_master_id=1,
            admin_id=2,
        )
        assert result.platform_net >= 0
