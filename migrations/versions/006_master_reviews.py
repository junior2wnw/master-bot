"""Add verified master reviews.

Revision ID: 006
Revises: 005
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "master_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("master_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("author_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("headline", sa.String(length=120)),
        sa.Column("body", sa.Text()),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_master_reviews_rating_range"),
        sa.UniqueConstraint("order_id", name="uq_master_reviews_order"),
        sa.UniqueConstraint("author_user_id", "order_id", name="uq_master_reviews_author_order"),
    )
    op.create_index("ix_master_reviews_master_user_id", "master_reviews", ["master_user_id"])
    op.create_index("ix_master_reviews_author_user_id", "master_reviews", ["author_user_id"])
    op.create_index("ix_master_reviews_master_created", "master_reviews", ["master_user_id", "created_at"])
    op.create_index("ix_master_reviews_author_created", "master_reviews", ["author_user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("master_reviews")
