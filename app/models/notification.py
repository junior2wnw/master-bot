"""Notification system: events, templates, delivery state."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NotificationTemplate(Base):
    """Message templates for notifications."""
    __tablename__ = "notification_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True)
    event_type: Mapped[str] = mapped_column(String(60))
    title_template: Mapped[str] = mapped_column(Text)
    body_template: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(20), default="telegram")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Notification(Base):
    """A notification record to be delivered to a user."""
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_status", "user_id", "status"),
        Index("ix_notifications_type", "event_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(20), default="telegram")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending, sent, delivered, failed, read

    entity_type: Mapped[str | None] = mapped_column(String(40))  # estimate, discount_request, etc.
    entity_id: Mapped[int | None] = mapped_column(Integer)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
