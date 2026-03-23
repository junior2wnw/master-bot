"""Add master_profiles table for personal data and bank details.

Revision ID: 002
Revises: 001
Create Date: 2026-03-23
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "master_profiles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        # Personal data
        sa.Column("full_name", sa.String(200)),
        sa.Column("phone", sa.String(20)),
        sa.Column("email", sa.String(200)),
        sa.Column("telegram_username", sa.String(100)),
        sa.Column("company_name", sa.String(200)),
        sa.Column("inn", sa.String(12)),
        sa.Column("address", sa.Text),
        sa.Column("specialization", sa.String(200)),
        # Bank details
        sa.Column("bank_name", sa.String(200)),
        sa.Column("bik", sa.String(9)),
        sa.Column("correspondent_account", sa.String(20)),
        sa.Column("settlement_account", sa.String(20)),
        sa.Column("card_number", sa.String(19)),
        sa.Column("sbp_phone", sa.String(20)),
        sa.Column("payment_recipient", sa.String(200)),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_master_profiles_user_id", "master_profiles", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_table("master_profiles")
