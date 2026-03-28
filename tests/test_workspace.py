"""Tests for workspace/inbox helpers used by bot and web app."""

from datetime import UTC, datetime
from types import SimpleNamespace

from app.services.workspace import (
    resolve_notification_callback,
    resolve_notification_target_label,
    serialize_notification,
)


def _notification(**overrides):
    data = {
        "id": 7,
        "event_type": "discount.requested",
        "title": "Discount approval needed",
        "body": "Master requested a discount",
        "status": "pending",
        "entity_type": "discount_request",
        "entity_id": 42,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_discount_request_routes_to_detail_card():
    notification = _notification()
    assert resolve_notification_callback(notification) == "disc_detail:42"
    assert resolve_notification_target_label(notification) == "Открыть скидку"


def test_estimate_notification_routes_to_estimate_view():
    notification = _notification(
        event_type="estimate.for_review",
        entity_type="estimate",
        entity_id=15,
    )
    assert resolve_notification_callback(notification) == "est_view:15"
    assert resolve_notification_target_label(notification) == "Открыть смету"


def test_invite_pending_routes_to_request_card():
    notification = _notification(
        event_type="invite.pending_approval",
        entity_type="invite_activation",
        entity_id=11,
    )
    assert resolve_notification_callback(notification) == "inv_request:11"
    assert resolve_notification_target_label(notification) == "Открыть запрос на роль"


def test_notification_serialization_marks_unread_and_includes_action_target():
    payload = serialize_notification(_notification())
    assert payload["is_unread"] is True
    assert payload["target_callback"] == "disc_detail:42"
    assert payload["target_label"] == "Открыть скидку"


def test_read_notification_is_not_marked_unread():
    payload = serialize_notification(_notification(status="read"))
    assert payload["is_unread"] is False
