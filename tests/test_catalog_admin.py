"""Tests for admin catalog mutation helpers."""

import pytest

from app.core.exceptions import ValidationError
from app.services.catalog import parse_price_input


def test_parse_price_input_accepts_single_value():
    assert parse_price_input("2500") == (2500, 2500, 2500)


def test_parse_price_input_accepts_triplet():
    assert parse_price_input("2000 2500 3000") == (2000, 2500, 3000)


def test_parse_price_input_rejects_invalid_order():
    with pytest.raises(ValidationError):
        parse_price_input("3000 2500 2000")
