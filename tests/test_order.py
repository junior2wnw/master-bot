"""Tests for order service: status transitions, validation."""

import pytest
from app.services.order import TRANSITIONS


class TestOrderTransitions:
    """Test the order status state machine."""

    def test_draft_can_submit(self):
        assert "submitted" in TRANSITIONS["draft"]

    def test_draft_can_cancel(self):
        assert "cancelled" in TRANSITIONS["draft"]

    def test_draft_cannot_complete(self):
        assert "completed" not in TRANSITIONS["draft"]

    def test_submitted_can_assign(self):
        assert "assigned" in TRANSITIONS["submitted"]

    def test_assigned_can_start(self):
        assert "in_progress" in TRANSITIONS["assigned"]

    def test_in_progress_can_complete(self):
        assert "completed" in TRANSITIONS["in_progress"]

    def test_completed_can_pay(self):
        assert "paid" in TRANSITIONS["completed"]

    def test_completed_can_dispute(self):
        assert "disputed" in TRANSITIONS["completed"]

    def test_paid_is_terminal(self):
        assert len(TRANSITIONS["paid"]) == 0

    def test_cancelled_is_terminal(self):
        assert len(TRANSITIONS["cancelled"]) == 0

    def test_all_statuses_have_transitions(self):
        expected = {"draft", "submitted", "assigned", "in_progress",
                    "completed", "disputed", "paid", "cancelled"}
        assert set(TRANSITIONS.keys()) == expected

    def test_cancel_from_pre_completed_states(self):
        """All pre-completed states should allow cancellation."""
        cancellable = ["draft", "submitted", "assigned", "in_progress"]
        for status in cancellable:
            assert "cancelled" in TRANSITIONS[status], f"{status} should be cancellable"

    def test_no_backward_transitions(self):
        """No state should allow going backward in the normal flow."""
        forward_order = ["draft", "submitted", "assigned", "in_progress", "completed", "paid"]
        for i, status in enumerate(forward_order):
            for j in range(i):
                earlier = forward_order[j]
                assert earlier not in TRANSITIONS[status], \
                    f"{status} should not transition back to {earlier}"
