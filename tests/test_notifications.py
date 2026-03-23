"""Tests for notification system — action keyboards, convenience functions."""

import pytest
from unittest.mock import MagicMock

from app.services.notification_dispatcher import _build_action_keyboard


class FakeNotification:
    def __init__(self, event_type: str, entity_id: int | None = None):
        self.event_type = event_type
        self.entity_id = entity_id
        self.entity_type = "test"


class TestActionKeyboards:
    """Notifications should include relevant action buttons."""

    def test_discount_requested_has_approve_reject(self):
        n = FakeNotification("discount.requested", entity_id=42)
        kb = _build_action_keyboard(n)
        assert kb is not None
        # Should have approve and reject buttons + menu
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert "✅ Одобрить" in texts
        assert "❌ Отклонить" in texts
        assert "← Меню" in texts

    def test_estimate_for_review_has_approve_reject_view(self):
        n = FakeNotification("estimate.for_review", entity_id=10)
        kb = _build_action_keyboard(n)
        assert kb is not None
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert "✅ Согласовать" in texts
        assert "❌ Отклонить" in texts
        assert "📊 Посмотреть смету" in texts

    def test_order_assigned_has_start_button(self):
        n = FakeNotification("order.assigned", entity_id=5)
        kb = _build_action_keyboard(n)
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert "🔨 Начать работу" in texts

    def test_order_completed_has_pay_button(self):
        n = FakeNotification("order.completed", entity_id=7)
        kb = _build_action_keyboard(n)
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert "💳 Оплатить" in texts

    def test_unknown_event_still_has_menu(self):
        n = FakeNotification("some.unknown.event", entity_id=1)
        kb = _build_action_keyboard(n)
        assert kb is not None
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert "← Меню" in texts

    def test_no_entity_id_still_works(self):
        n = FakeNotification("discount.requested", entity_id=None)
        kb = _build_action_keyboard(n)
        # Without entity_id, no approve/reject buttons, just menu
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert "← Меню" in texts
        assert "✅ Одобрить" not in texts
