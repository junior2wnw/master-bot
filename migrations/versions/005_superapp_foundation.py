"""Add superapp foundation tables.

Revision ID: 005
Revises: 004
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "public_master_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("headline", sa.String(length=160)),
        sa.Column("bio", sa.Text()),
        sa.Column("city", sa.String(length=120)),
        sa.Column("experience_years", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hourly_rate_from", sa.Integer()),
        sa.Column("hourly_rate_to", sa.Integer()),
        sa.Column("availability_status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("response_time_label", sa.String(length=80)),
        sa.Column("verification_status", sa.String(length=20), nullable=False, server_default="community"),
        sa.Column("rating_average", sa.Numeric(4, 2), nullable=False, server_default="0"),
        sa.Column("rating_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_jobs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("accent_color", sa.String(length=20)),
        sa.Column("skills_json", sa.JSON()),
        sa.Column("portfolio_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("experience_years >= 0", name="ck_public_master_profiles_experience"),
        sa.CheckConstraint("hourly_rate_from IS NULL OR hourly_rate_from >= 0", name="ck_public_master_profiles_rate_from"),
        sa.CheckConstraint("hourly_rate_to IS NULL OR hourly_rate_to >= 0", name="ck_public_master_profiles_rate_to"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_public_master_profiles_user_id", "public_master_profiles", ["user_id"])
    op.create_index("ix_public_master_profiles_public", "public_master_profiles", ["is_public", "availability_status"])
    op.create_index("ix_public_master_profiles_city", "public_master_profiles", ["city"])

    op.create_table(
        "workspace_layouts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("preset_code", sa.String(length=32), nullable=False),
        sa.Column("layout_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "preset_code", name="uq_workspace_layouts_user_preset"),
    )
    op.create_index("ix_workspace_layouts_user_id", "workspace_layouts", ["user_id"])
    op.create_index("ix_workspace_layouts_user_preset", "workspace_layouts", ["user_id", "preset_code"])

    op.create_table(
        "job_posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("author_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("profession_id", sa.Integer(), sa.ForeignKey("professions.id")),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("city", sa.String(length=120)),
        sa.Column("budget_from", sa.Integer()),
        sa.Column("budget_to", sa.Integer()),
        sa.Column("urgency", sa.String(length=20), nullable=False, server_default="normal"),
        sa.Column("desired_start_label", sa.String(length=120)),
        sa.Column("preferred_contact", sa.String(length=30)),
        sa.Column("source_channel", sa.String(length=20), nullable=False, server_default="max"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("budget_from IS NULL OR budget_from >= 0", name="ck_job_posts_budget_from"),
        sa.CheckConstraint("budget_to IS NULL OR budget_to >= 0", name="ck_job_posts_budget_to"),
    )
    op.create_index("ix_job_posts_status_created", "job_posts", ["status", "created_at"])
    op.create_index("ix_job_posts_author_status", "job_posts", ["author_user_id", "status"])
    op.create_index("ix_job_posts_city", "job_posts", ["city"])

    op.create_table(
        "job_post_responses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_post_id", sa.Integer(), sa.ForeignKey("job_posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("responder_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("price_offer", sa.Integer()),
        sa.Column("eta_label", sa.String(length=120)),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="submitted"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("price_offer IS NULL OR price_offer >= 0", name="ck_job_post_responses_price_offer"),
        sa.UniqueConstraint("job_post_id", "responder_user_id", name="uq_job_post_responses_post_user"),
    )
    op.create_index("ix_job_post_responses_post_status", "job_post_responses", ["job_post_id", "status"])


def downgrade() -> None:
    op.drop_table("job_post_responses")
    op.drop_table("job_posts")
    op.drop_table("workspace_layouts")
    op.drop_table("public_master_profiles")
