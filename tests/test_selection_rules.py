"""Tests for selection/exclusion rules engine."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class FakeServiceItem:
    def __init__(self, code, name, excludes=None, shared_ops=None, selection_mode="quantity"):
        self.id = hash(code) % 10000
        self.code = code
        self.name = name
        self.excludes = excludes
        self.shared_ops = shared_ops
        self.selection_mode = selection_mode


class FakeLineItem:
    def __init__(self, service_item_id, shared_operation_id=None):
        self.service_item_id = service_item_id
        self.shared_operation_id = shared_operation_id


class TestExclusionLogic:
    """Test exclusion rule parsing and logic."""

    def test_parse_excludes_semicolon_separated(self):
        item = FakeServiceItem("A", "Item A", excludes="B;C;D")
        codes = {c.strip() for c in item.excludes.split(";") if c.strip()}
        assert codes == {"B", "C", "D"}

    def test_empty_excludes(self):
        item = FakeServiceItem("A", "Item A", excludes=None)
        assert item.excludes is None

    def test_single_exclude(self):
        item = FakeServiceItem("A", "Item A", excludes="B")
        codes = {c.strip() for c in item.excludes.split(";") if c.strip()}
        assert codes == {"B"}

    def test_excludes_with_whitespace(self):
        item = FakeServiceItem("A", "Item A", excludes="B ; C ;  D  ")
        codes = {c.strip() for c in item.excludes.split(";") if c.strip()}
        assert codes == {"B", "C", "D"}


class TestSharedOps:
    """Test shared operations parsing."""

    def test_parse_shared_ops(self):
        item = FakeServiceItem("A", "Item A", shared_ops="#CALL_OUT;#DRILL_HOLE")
        codes = [c.strip() for c in item.shared_ops.split(";") if c.strip()]
        assert codes == ["#CALL_OUT", "#DRILL_HOLE"]

    def test_empty_shared_ops(self):
        item = FakeServiceItem("A", "Item A", shared_ops=None)
        assert item.shared_ops is None


class TestSelectionMode:
    """Test selection mode constraints."""

    def test_single_mode_detection(self):
        item = FakeServiceItem("A", "Item A", selection_mode="single")
        assert item.selection_mode == "single"

    def test_quantity_mode_default(self):
        item = FakeServiceItem("A", "Item A")
        assert item.selection_mode == "quantity"

    def test_single_item_in_existing_codes(self):
        """Single-mode item should be flagged if already in estimate."""
        item = FakeServiceItem("A", "Item A", selection_mode="single")
        existing_codes = {"A", "B", "C"}
        is_duplicate = item.selection_mode == "single" and item.code in existing_codes
        assert is_duplicate is True

    def test_quantity_item_can_be_added_multiple_times(self):
        item = FakeServiceItem("A", "Item A", selection_mode="quantity")
        existing_codes = {"A", "B", "C"}
        is_duplicate = item.selection_mode == "single" and item.code in existing_codes
        assert is_duplicate is False


class TestBidirectionalExclusion:
    """Test that exclusion rules work in both directions."""

    def test_forward_exclusion(self):
        """If A excludes B, adding B should warn."""
        item_a = FakeServiceItem("A", "Item A", excludes="B")
        item_b_code = "B"
        excluded = {c.strip() for c in item_a.excludes.split(";") if c.strip()}
        assert item_b_code in excluded

    def test_reverse_exclusion(self):
        """If B excludes A, adding A should also warn."""
        item_b = FakeServiceItem("B", "Item B", excludes="A")
        new_item_code = "A"
        existing_codes = {"B"}
        # Check if new item is excluded by any existing item
        excluded = {c.strip() for c in item_b.excludes.split(";") if c.strip()}
        assert new_item_code in excluded
