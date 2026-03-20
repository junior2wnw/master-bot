"""Test fixtures. Uses in-memory models for pure logic tests."""

import pytest
from unittest.mock import MagicMock


class FakeUserRole:
    def __init__(self, role_code: str):
        self.role_code = role_code


class FakeBranchMember:
    def __init__(self, branch_id: int, is_senior: bool = False):
        self.branch_id = branch_id
        self.is_senior = is_senior


class FakeUser:
    def __init__(self, id: int, roles: list[str], branch_memberships=None):
        self.id = id
        self.roles = [FakeUserRole(r) for r in roles]
        self.branch_memberships = branch_memberships or []
        self.is_active = True

    @property
    def role_codes(self):
        return [r.role_code for r in self.roles]

    @property
    def display_name(self):
        return f"User-{self.id}"


@pytest.fixture
def owner():
    return FakeUser(1, ["product_owner"])


@pytest.fixture
def admin():
    return FakeUser(2, ["admin"])


@pytest.fixture
def senior_master():
    return FakeUser(3, ["senior_master", "master"], [FakeBranchMember(1, is_senior=True)])


@pytest.fixture
def master():
    return FakeUser(4, ["master"], [FakeBranchMember(1)])


@pytest.fixture
def client():
    return FakeUser(5, ["client"])


@pytest.fixture
def other_branch_master():
    return FakeUser(6, ["master"], [FakeBranchMember(2)])
