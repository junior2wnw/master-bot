"""Generic approval request model for cross-module use."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ApprovalRequest(Base):
    """Generic approval entity for discounts, staffing, estimates, etc."""
    __tablename__ = "approval_requests"
    __table_args__ = (
        Index("ix_approval_requests_assigned_status", "assigned_to", "status"),
        Index("ix_approval_requests_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    approval_type: Mapped[str] = mapped_column(String(30))
    # discount, staffing, estimate_change, price_override

    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int] = mapped_column(Integer)

    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending, approved, rejected, escalated, expired

    comment: Mapped[str | None] = mapped_column(Text)
    resolution_comment: Mapped[str | None] = mapped_column(Text)

    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
