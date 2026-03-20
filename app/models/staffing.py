"""Staffing actions: deactivate, suspend, terminate, transfer."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StaffingAction(Base):
    """Record of a personnel action."""
    __tablename__ = "staffing_actions"
    __table_args__ = (
        Index("ix_staffing_actions_target", "target_user_id"),
        Index("ix_staffing_actions_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    action_type: Mapped[str] = mapped_column(String(30))
    # deactivate, suspend, terminate, transfer, revoke_role, restore

    target_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    initiated_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending, approved, rejected, executed

    reason: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    # e.g. {"from_branch_id": 1, "to_branch_id": 2} for transfers

    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
