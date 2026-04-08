"""Marketplace and workspace models for the Mini App superapp shell."""

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin


class PublicMasterProfile(Base, TimestampMixin):
    """Public-facing master profile for marketplace discovery."""

    __tablename__ = "public_master_profiles"
    __table_args__ = (
        Index("ix_public_master_profiles_public", "is_public", "availability_status"),
        Index("ix_public_master_profiles_city", "city"),
        CheckConstraint("experience_years >= 0", name="ck_public_master_profiles_experience"),
        CheckConstraint("hourly_rate_from IS NULL OR hourly_rate_from >= 0", name="ck_public_master_profiles_rate_from"),
        CheckConstraint("hourly_rate_to IS NULL OR hourly_rate_to >= 0", name="ck_public_master_profiles_rate_to"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    headline: Mapped[str | None] = mapped_column(String(160))
    bio: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(120))
    experience_years: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    hourly_rate_from: Mapped[int | None] = mapped_column(Integer)
    hourly_rate_to: Mapped[int | None] = mapped_column(Integer)
    availability_status: Mapped[str] = mapped_column(
        String(20),
        default="open",
        server_default="open",
    )
    response_time_label: Mapped[str | None] = mapped_column(String(80))
    verification_status: Mapped[str] = mapped_column(
        String(20),
        default="community",
        server_default="community",
    )
    rating_average: Mapped[float] = mapped_column(
        Numeric(4, 2),
        default=0,
        server_default="0",
    )
    rating_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    completed_jobs: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    accent_color: Mapped[str | None] = mapped_column(String(20))
    skills_json: Mapped[list[str] | None] = mapped_column(JSON)
    portfolio_json: Mapped[list[dict] | None] = mapped_column(JSON)

    user = relationship("User", lazy="selectin")


class WorkspaceLayout(Base, TimestampMixin):
    """Saved workspace layout per user and preset."""

    __tablename__ = "workspace_layouts"
    __table_args__ = (
        UniqueConstraint("user_id", "preset_code", name="uq_workspace_layouts_user_preset"),
        Index("ix_workspace_layouts_user_preset", "user_id", "preset_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    preset_code: Mapped[str] = mapped_column(String(32))
    layout_json: Mapped[dict] = mapped_column(JSON)

    user = relationship("User", lazy="selectin")


class JobPost(Base, TimestampMixin):
    """Demand-side job request published to the marketplace board."""

    __tablename__ = "job_posts"
    __table_args__ = (
        Index("ix_job_posts_status_created", "status", "created_at"),
        Index("ix_job_posts_author_status", "author_user_id", "status"),
        Index("ix_job_posts_city", "city"),
        CheckConstraint("budget_from IS NULL OR budget_from >= 0", name="ck_job_posts_budget_from"),
        CheckConstraint("budget_to IS NULL OR budget_to >= 0", name="ck_job_posts_budget_to"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    author_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    profession_id: Mapped[int | None] = mapped_column(ForeignKey("professions.id"))
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(120))
    budget_from: Mapped[int | None] = mapped_column(Integer)
    budget_to: Mapped[int | None] = mapped_column(Integer)
    urgency: Mapped[str] = mapped_column(String(20), default="normal", server_default="normal")
    desired_start_label: Mapped[str | None] = mapped_column(String(120))
    preferred_contact: Mapped[str | None] = mapped_column(String(30))
    source_channel: Mapped[str] = mapped_column(String(20), default="max", server_default="max")
    status: Mapped[str] = mapped_column(String(20), default="open", server_default="open")

    author = relationship("User", lazy="selectin")
    responses: Mapped[list["JobPostResponse"]] = relationship(
        back_populates="job_post",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class JobPostResponse(Base, TimestampMixin):
    """Provider response to a board post."""

    __tablename__ = "job_post_responses"
    __table_args__ = (
        UniqueConstraint("job_post_id", "responder_user_id", name="uq_job_post_responses_post_user"),
        Index("ix_job_post_responses_post_status", "job_post_id", "status"),
        CheckConstraint("price_offer IS NULL OR price_offer >= 0", name="ck_job_post_responses_price_offer"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_post_id: Mapped[int] = mapped_column(
        ForeignKey("job_posts.id", ondelete="CASCADE"),
        nullable=False,
    )
    responder_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    message: Mapped[str] = mapped_column(Text)
    price_offer: Mapped[int | None] = mapped_column(Integer)
    eta_label: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(
        String(20),
        default="submitted",
        server_default="submitted",
    )

    job_post = relationship("JobPost", back_populates="responses", lazy="selectin")
    responder = relationship("User", lazy="selectin")
