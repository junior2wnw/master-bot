"""Orders / jobs / requests."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin


class Order(Base, TimestampMixin):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_client", "client_id"),
        Index("ix_orders_master", "master_id"),
        Index("ix_orders_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    master_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    estimate_id: Mapped[int | None] = mapped_column(ForeignKey("estimates.id"))

    status: Mapped[str] = mapped_column(String(30), default="draft")
    # draft, submitted, assigned, master_arriving, on_site,
    # awaiting_client_approval, approved, in_progress,
    # completed, paid, cancelled, disputed

    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    urgency: Mapped[str] = mapped_column(String(20), default="normal")  # normal, urgent, emergency
    preferred_time: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    source_channel: Mapped[str] = mapped_column(String(30), default="telegram")
    cancellation_reason: Mapped[str | None] = mapped_column(Text)

    client = relationship("User", foreign_keys=[client_id], lazy="selectin")
    master = relationship("User", foreign_keys=[master_id], lazy="selectin")
    status_history: Mapped[list["OrderStatusHistory"]] = relationship(back_populates="order")


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"
    __table_args__ = (
        Index("ix_order_status_history_order", "order_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30))
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    order: Mapped["Order"] = relationship(back_populates="status_history")
