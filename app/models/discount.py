"""Discount approval workflow."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DiscountRequest(Base):
    """A request from master to apply a discount, requiring approval."""
    __tablename__ = "discount_requests"
    __table_args__ = (
        Index("ix_discount_requests_status", "status"),
        Index("ix_discount_requests_estimate", "estimate_id"),
        Index("ix_discount_requests_approver", "assigned_to", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    estimate_id: Mapped[int] = mapped_column(ForeignKey("estimates.id"))
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))

    # Discount details
    discount_type: Mapped[str] = mapped_column(String(20))  # percent, fixed
    discount_value: Mapped[float] = mapped_column(Numeric(10, 2))
    scope: Mapped[str] = mapped_column(String(20), default="estimate")  # estimate, line_item
    line_item_id: Mapped[int | None] = mapped_column(Integer)  # if scope = line_item

    # Justification
    reason: Mapped[str] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)

    # Approval chain
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending, approved, rejected, escalated

    # Resolution
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    resolution_comment: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    requester = relationship("User", foreign_keys=[requested_by], lazy="selectin")
    resolver = relationship("User", foreign_keys=[resolved_by], lazy="selectin")
