"""User suggestions for improving the project."""

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin


class ProjectSuggestion(Base, TimestampMixin):
    __tablename__ = "project_suggestions"
    __table_args__ = (
        Index("ix_project_suggestions_author", "author_user_id", "created_at"),
        Index("ix_project_suggestions_status", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    author_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="api")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="submitted",
        server_default="submitted",
    )

    author = relationship("User", lazy="selectin")
