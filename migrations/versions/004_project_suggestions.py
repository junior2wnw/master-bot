"""Add project suggestions table.

Revision ID: 004
Revises: 003
Create Date: 2026-04-04
"""

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_suggestions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("author_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="submitted"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_project_suggestions_author",
        "project_suggestions",
        ["author_user_id", "created_at"],
    )
    op.create_index(
        "ix_project_suggestions_status",
        "project_suggestions",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("project_suggestions")
