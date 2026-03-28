"""Focused tests for discount approval helpers."""

from types import SimpleNamespace

import pytest

from app.core.exceptions import PermissionDenied, ValidationError
from app.services.discount import _calculate_discount_amount, _check_can_approve, can_access_discount_request


class FakeRole:
    def __init__(self, role_code: str):
        self.role_code = role_code


class FakeUser:
    def __init__(self, user_id: int, roles: list[str]):
        self.id = user_id
        self.roles = [FakeRole(role) for role in roles]


def _request(status: str = "pending", assigned_to: int | None = 10):
    return SimpleNamespace(status=status, assigned_to=assigned_to)


def test_percent_discount_is_capped_by_base_amount():
    assert _calculate_discount_amount(1000, "percent", 15) == 150
    assert _calculate_discount_amount(1000, "percent", 250) == 1000


def test_fixed_discount_is_capped_by_base_amount():
    assert _calculate_discount_amount(1000, "fixed", 300) == 300
    assert _calculate_discount_amount(1000, "fixed", 5000) == 1000


def test_assigned_senior_master_can_approve():
    senior = FakeUser(10, ["senior_master", "master"])
    _check_can_approve(_request(assigned_to=10), senior)


def test_regular_master_cannot_approve():
    master = FakeUser(22, ["master"])
    with pytest.raises(PermissionDenied):
        _check_can_approve(_request(assigned_to=10), master)


def test_admin_can_access_any_discount_request():
    admin = FakeUser(2, ["admin"])
    assert can_access_discount_request(_request(assigned_to=99), admin)


def test_owner_can_access_any_discount_request():
    owner = FakeUser(1, ["product_owner"])
    assert can_access_discount_request(_request(assigned_to=99), owner)


def test_senior_cannot_access_foreign_discount_request():
    senior = FakeUser(10, ["senior_master", "master"])
    assert not can_access_discount_request(_request(assigned_to=11), senior)


def test_processed_request_cannot_be_approved_again():
    admin = FakeUser(2, ["admin"])
    with pytest.raises(ValidationError):
        _check_can_approve(_request(status="approved", assigned_to=2), admin)
