"""Invite system: one-time/limited codes, role-bound, branch-bound."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin


class Invite(Base, TimestampMixin):
    __tablename__ = "invites"
    __table_args__ = (
        Index("ix_invites_code", "code", unique=True),
        Index("ix_invites_active", "is_active", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    role_code: Mapped[str] = mapped_column(String(30))  # Role to grant on activation
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"))
    profession_id: Mapped[int | None] = mapped_column(ForeignKey("professions.id"))
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    activations: Mapped[list["InviteActivation"]] = relationship(back_populates="invite")
    creator = relationship("User", foreign_keys=[created_by], lazy="selectin")

    @property
    def is_exhausted(self) -> bool:
        return self.used_count >= self.max_uses

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        from datetime import timezone
        return datetime.now(timezone.utc) > self.expires_at


class InviteActivation(Base):
    __tablename__ = "invite_activations"
    __table_args__ = (
        Index("ix_invite_activations_invite", "invite_id"),
        Index("ix_invite_activations_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    invite_id: Mapped[int] = mapped_column(ForeignKey("invites.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, approved, rejected
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    invite: Mapped["Invite"] = relationship(back_populates="activations")
