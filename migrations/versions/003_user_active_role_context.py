"""Add user active role context for safe role switching.

Revision ID: 003
Revises: 002
Create Date: 2026-03-27
"""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("active_role_code", sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "active_role_code")
