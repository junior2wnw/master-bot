"""Branch hierarchy: admin → senior_master → master."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin


class Branch(Base, TimestampMixin):
    """A branch groups masters under a senior_master."""
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    senior_master_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    senior_master = relationship("User", foreign_keys=[senior_master_id], lazy="selectin")
    members: Mapped[list["BranchMember"]] = relationship(back_populates="branch", lazy="selectin")


class BranchMember(Base):
    """Links a user to a branch with their role within it."""
    __tablename__ = "branch_members"
    __table_args__ = (
        Index("ix_branch_members_user_branch", "user_id", "branch_id", unique=True),
        Index("ix_branch_members_branch_active", "branch_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    is_senior: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    branch: Mapped["Branch"] = relationship(back_populates="members")
    user = relationship("User", back_populates="branch_memberships", foreign_keys=[user_id])
