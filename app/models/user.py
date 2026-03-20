"""User and role models."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    username: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    # Relationships
    roles: Mapped[list["UserRole"]] = relationship(back_populates="user", lazy="selectin")
    branch_memberships: Mapped[list["BranchMember"]] = relationship(
        "BranchMember", back_populates="user", lazy="selectin",
        foreign_keys="BranchMember.user_id",
    )

    @property
    def role_codes(self) -> list[str]:
        return [r.role_code for r in self.roles]

    @property
    def display_name(self) -> str:
        parts = [self.first_name]
        if self.last_name:
            parts.append(self.last_name)
        return " ".join(parts)

    def __repr__(self) -> str:
        return f"<User id={self.id} tg={self.telegram_id} name={self.display_name}>"


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        Index("ix_user_roles_user_role", "user_id", "role_code", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role_code: Mapped[str] = mapped_column(String(30))  # matches Role enum values
    granted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="roles", foreign_keys=[user_id])


# Import here to resolve forward ref
from app.models.hierarchy import BranchMember  # noqa: E402
