"""Tests for notification action keyboards."""

from app.services.notification_dispatcher import _build_action_keyboard


class FakeNotification:
    def __init__(self, event_type: str, entity_id: int | None = None):
        self.event_type = event_type
        self.entity_id = entity_id
        self.entity_type = "test"


class TestActionKeyboards:
    def test_discount_requested_has_approve_reject(self):
        notification = FakeNotification("discount.requested", entity_id=42)
        keyboard = _build_action_keyboard(notification)
        texts = [button.text for row in keyboard.inline_keyboard for button in row]
        assert "✅ Одобрить" in texts
        assert "❌ Отклонить" in texts
        assert "← Меню" in texts

    def test_estimate_for_review_has_approve_reject_view(self):
        notification = FakeNotification("estimate.for_review", entity_id=10)
        keyboard = _build_action_keyboard(notification)
        texts = [button.text for row in keyboard.inline_keyboard for button in row]
        assert "✅ Согласовать" in texts
        assert "❌ Отклонить" in texts
        assert "📊 Посмотреть смету" in texts

    def test_order_assigned_has_start_button(self):
        notification = FakeNotification("order.assigned", entity_id=5)
        keyboard = _build_action_keyboard(notification)
        texts = [button.text for row in keyboard.inline_keyboard for button in row]
        assert "🔨 Начать работу" in texts

    def test_order_completed_has_pay_button(self):
        notification = FakeNotification("order.completed", entity_id=7)
        keyboard = _build_action_keyboard(notification)
        texts = [button.text for row in keyboard.inline_keyboard for button in row]
        assert "💳 Оплатить" in texts

    def test_invite_pending_with_entity_id_has_direct_actions(self):
        notification = FakeNotification("invite.pending_approval", entity_id=9)
        keyboard = _build_action_keyboard(notification)
        texts = [button.text for row in keyboard.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
        assert "✅ Одобрить" in texts
        assert "❌ Отклонить" in texts
        assert "inv_approve:9" in callbacks
        assert "inv_reject:9" in callbacks

    def test_unknown_event_still_has_menu(self):
        notification = FakeNotification("some.unknown.event", entity_id=1)
        keyboard = _build_action_keyboard(notification)
        texts = [button.text for row in keyboard.inline_keyboard for button in row]
        assert "← Меню" in texts

    def test_no_entity_id_still_works(self):
        notification = FakeNotification("discount.requested", entity_id=None)
        keyboard = _build_action_keyboard(notification)
        texts = [button.text for row in keyboard.inline_keyboard for button in row]
        assert "← Меню" in texts
        assert "✅ Одобрить" not in texts
