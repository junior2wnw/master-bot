"""Estimates with full versioning: estimate → versions → line items + discounts."""

from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin


class Estimate(Base, TimestampMixin):
    """Top-level estimate linked to client + master."""
    __tablename__ = "estimates"
    __table_args__ = (
        Index("ix_estimates_client", "client_id"),
        Index("ix_estimates_master", "master_id"),
        Index("ix_estimates_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    master_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    status: Mapped[str] = mapped_column(String(30), default="draft")
    # draft, estimated, master_proposed, client_review, approved,
    # in_progress, completed, paid, disputed, cancelled
    current_version_id: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)

    versions: Mapped[list["EstimateVersion"]] = relationship(
        back_populates="estimate", order_by="EstimateVersion.version_number"
    )


class EstimateVersion(Base):
    """A snapshot of the estimate at a point in time."""
    __tablename__ = "estimate_versions"
    __table_args__ = (
        Index("ix_estimate_versions_estimate", "estimate_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    estimate_id: Mapped[int] = mapped_column(ForeignKey("estimates.id", ondelete="CASCADE"))
    version_number: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(Text)  # why this version was created

    # Totals (denormalized for fast access)
    total_amount: Mapped[int] = mapped_column(Integer, default=0)  # sum of line items
    discount_amount: Mapped[int] = mapped_column(Integer, default=0)
    final_amount: Mapped[int] = mapped_column(Integer, default=0)  # total - discount

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    estimate: Mapped["Estimate"] = relationship(back_populates="versions")
    line_items: Mapped[list["EstimateLineItem"]] = relationship(
        back_populates="version", order_by="EstimateLineItem.sort_order"
    )
    discounts: Mapped[list["EstimateDiscount"]] = relationship(back_populates="version")


class EstimateLineItem(Base):
    """A single line in the estimate version."""
    __tablename__ = "estimate_line_items"
    __table_args__ = (
        Index("ix_estimate_line_items_version", "version_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("estimate_versions.id", ondelete="CASCADE"))
    service_item_id: Mapped[int | None] = mapped_column(ForeignKey("service_items.id"))
    shared_operation_id: Mapped[int | None] = mapped_column(ForeignKey("shared_operations.id"))

    # Snapshot (so price changes don't affect past estimates)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(30))
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), default=1)
    unit_price: Mapped[int] = mapped_column(Integer)  # price per unit at time of estimate
    coefficients_applied: Mapped[dict | None] = mapped_column(JSONB)  # {"urgent": 1.2, "wall_concrete": 1.3}
    subtotal: Mapped[int] = mapped_column(Integer)  # unit_price * quantity * product(coefficients)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    version: Mapped["EstimateVersion"] = relationship(back_populates="line_items")


class EstimateDiscount(Base):
    """Discount applied to an estimate version (whole or per-item)."""
    __tablename__ = "estimate_discounts"
    __table_args__ = (
        Index("ix_estimate_discounts_version", "version_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("estimate_versions.id", ondelete="CASCADE"))
    discount_request_id: Mapped[int | None] = mapped_column(ForeignKey("discount_requests.id"))
    discount_type: Mapped[str] = mapped_column(String(20))  # percent, fixed
    discount_value: Mapped[float] = mapped_column(Numeric(10, 2))  # 10 for 10% or 500 for 500₽
    amount: Mapped[int] = mapped_column(Integer)  # actual amount subtracted
    reason: Mapped[str | None] = mapped_column(Text)
    applied_to_line_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("estimate_line_items.id")
    )  # null = whole estimate

    version: Mapped["EstimateVersion"] = relationship(back_populates="discounts")
