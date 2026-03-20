"""Pricing coefficients: urgency, material, access, weight, height, etc."""

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin


class Coefficient(Base, TimestampMixin):
    """A multiplier applied to service prices based on conditions.

    From Coeff_Template: urgency, material, access, weight, height, built_in, floor.
    """
    __tablename__ = "coefficients"

    id: Mapped[int] = mapped_column(primary_key=True)
    coef_type: Mapped[str] = mapped_column(String(30))  # urgency, material, access, weight, height, built_in, floor
    coef_key: Mapped[str] = mapped_column(String(50), unique=True)  # urgent, night, wall_concrete, etc.
    label: Mapped[str] = mapped_column(String(200))  # human-readable Russian label
    multiplier: Mapped[float] = mapped_column(Numeric(4, 2))  # e.g. 1.20, 1.35
    applies_to: Mapped[str | None] = mapped_column(Text)  # comma-separated professions or "all"
    when_use: Mapped[str | None] = mapped_column(Text)  # description when to apply
    note: Mapped[str | None] = mapped_column(Text)
    sort_priority: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
