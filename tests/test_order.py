"""Tests for order service: status transitions, validation."""

from types import SimpleNamespace

import pytest
from app.core.exceptions import ValidationError
from app.services.order import (
    TRANSITIONS,
    get_cancellation_reason_options,
    normalize_cancellation_reason,
)


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


def _user(user_id: int, roles: list[str]):
    return SimpleNamespace(
        id=user_id,
        roles=[SimpleNamespace(role_code=role) for role in roles],
    )


def _order(master_id: int | None = None, status: str = "assigned"):
    return SimpleNamespace(master_id=master_id, client_id=5, status=status)


def test_master_gets_predefined_cancellation_reasons():
    reasons = get_cancellation_reason_options(_user(3, ["master"]), _order(master_id=3))
    assert reasons
    assert reasons[0]["code"] == "master_health"


def test_master_cancellation_reason_is_normalized_from_code():
    label = normalize_cancellation_reason(
        _user(3, ["master"]),
        _order(master_id=3),
        "missing_tools_or_parts",
    )
    assert "инструмента" in label


def test_master_cannot_cancel_with_arbitrary_reason():
    with pytest.raises(ValidationError):
        normalize_cancellation_reason(
            _user(3, ["master"]),
            _order(master_id=3),
            "Неудобный клиент",
        )
