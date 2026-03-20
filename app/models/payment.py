"""Payments, commission policies, and commission records."""

from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_order", "order_id"),
        Index("ix_payments_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    estimate_id: Mapped[int | None] = mapped_column(ForeignKey("estimates.id"))

    amount_expected: Mapped[int] = mapped_column(Integer)
    amount_paid: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(5), default="RUB")

    method: Mapped[str | None] = mapped_column(String(30))  # qr, phone, card, cash
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending, sent, confirmed, failed, refunded

    qr_payload: Mapped[str | None] = mapped_column(Text)
    phone_number: Mapped[str | None] = mapped_column(String(20))
    proof_url: Mapped[str | None] = mapped_column(Text)

    marked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CommissionPolicy(Base, TimestampMixin):
    """Configurable commission rules."""
    __tablename__ = "commission_policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    platform_fee_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=20.0)
    senior_master_share_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=5.0)
    admin_share_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=5.0)
    profession_id: Mapped[int | None] = mapped_column(ForeignKey("professions.id"))
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class CommissionRecord(Base):
    """Calculated commission for a completed payment."""
    __tablename__ = "commission_records"
    __table_args__ = (
        Index("ix_commission_records_payment", "payment_id"),
        Index("ix_commission_records_master", "master_id"),
        Index("ix_commission_records_senior", "senior_master_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    policy_id: Mapped[int | None] = mapped_column(ForeignKey("commission_policies.id"))

    gross_total: Mapped[int] = mapped_column(Integer)
    discount_total: Mapped[int] = mapped_column(Integer, default=0)
    net_total: Mapped[int] = mapped_column(Integer)  # gross - discount

    platform_fee: Mapped[int] = mapped_column(Integer)
    senior_master_share: Mapped[int] = mapped_column(Integer, default=0)
    senior_master_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    admin_share: Mapped[int] = mapped_column(Integer, default=0)
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    master_net: Mapped[int] = mapped_column(Integer)
    master_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
