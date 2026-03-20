"""Initial schema — all tables for МастерБот v0.1.

Revision ID: 001
Revises:
Create Date: 2026-03-21

Hand-written from SQLAlchemy models for deterministic, reviewable migrations.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # === pg_trgm extension for fuzzy search ===
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # === users ===
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("telegram_id", sa.BigInteger, nullable=False),
        sa.Column("phone", sa.String(20)),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100)),
        sa.Column("username", sa.String(100)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    # === user_roles ===
    op.create_table(
        "user_roles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_code", sa.String(30), nullable=False),
        sa.Column("granted_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_user_roles_user_role", "user_roles", ["user_id", "role_code"], unique=True)

    # === branches ===
    op.create_table(
        "branches",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("senior_master_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # === branch_members ===
    op.create_table(
        "branch_members",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("branch_id", sa.Integer, sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_senior", sa.Boolean, nullable=False, default=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("assigned_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_branch_members_user_branch", "branch_members", ["user_id", "branch_id"], unique=True)
    op.create_index("ix_branch_members_branch_active", "branch_members", ["branch_id", "is_active"])

    # === professions ===
    op.create_table(
        "professions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("icon", sa.String(10)),
        sa.Column("sort_priority", sa.Integer, default=0),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("uq_professions_code", "professions", ["code"], unique=True)

    # === service_groups ===
    op.create_table(
        "service_groups",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("profession_id", sa.Integer, sa.ForeignKey("professions.id"), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("sort_priority", sa.Integer, default=0),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
    )
    op.create_index("ix_service_groups_profession", "service_groups", ["profession_id"])
    op.create_index("uq_service_groups_code", "service_groups", ["code"], unique=True)

    # === service_subgroups ===
    op.create_table(
        "service_subgroups",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("group_id", sa.Integer, sa.ForeignKey("service_groups.id"), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("sort_priority", sa.Integer, default=0),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
    )
    op.create_index("ix_service_subgroups_group", "service_subgroups", ["group_id"])
    op.create_index("uq_service_subgroups_code", "service_subgroups", ["code"], unique=True)

    # === shared_operations ===
    op.create_table(
        "shared_operations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("typical_unit", sa.String(30)),
        sa.Column("pricing_strategy", sa.String(30)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
    )
    op.create_index("uq_shared_operations_code", "shared_operations", ["code"], unique=True)

    # === service_items ===
    op.create_table(
        "service_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sort_order", sa.Integer, default=0),
        sa.Column("profession_id", sa.Integer, sa.ForeignKey("professions.id"), nullable=False),
        sa.Column("group_id", sa.Integer, sa.ForeignKey("service_groups.id"), nullable=False),
        sa.Column("subgroup_id", sa.Integer, sa.ForeignKey("service_subgroups.id")),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("price_min", sa.Integer, default=0),
        sa.Column("price_max", sa.Integer, default=0),
        sa.Column("price_recommended", sa.Integer, default=0),
        sa.Column("currency", sa.String(5), default="RUB"),
        sa.Column("record_type", sa.String(20), nullable=False),
        sa.Column("calc_strategy", sa.String(20), default="PER_UNIT"),
        sa.Column("selection_mode", sa.String(20), default="quantity"),
        sa.Column("complexity", sa.String(20)),
        sa.Column("confidence", sa.String(10)),
        sa.Column("labor_only", sa.Boolean, default=True),
        sa.Column("aliases", sa.Text),
        sa.Column("hashtags", sa.Text),
        sa.Column("search_text", sa.Text),
        sa.Column("shared_ops", sa.Text),
        sa.Column("excludes", sa.Text),
        sa.Column("estimator_fields", sa.Text),
        sa.Column("note", sa.Text),
        sa.Column("source_1", sa.Text),
        sa.Column("source_2", sa.Text),
        sa.Column("city", sa.String(100)),
        sa.Column("region", sa.String(100)),
        sa.Column("price_updated_at", sa.String(20)),
        sa.Column("is_popular", sa.Boolean, default=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer, default=1),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_service_items_code", "service_items", ["code"], unique=True)
    op.create_index("ix_service_items_profession", "service_items", ["profession_id"])
    op.create_index("ix_service_items_group", "service_items", ["group_id"])
    op.create_index("ix_service_items_subgroup", "service_items", ["subgroup_id"])
    op.create_index("ix_service_items_active_popular", "service_items", ["is_active", "is_popular"])
    # GIN trigram index for fast fuzzy search
    op.execute(
        "CREATE INDEX ix_service_items_search_trgm ON service_items "
        "USING gin (search_text gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_service_items_name_trgm ON service_items "
        "USING gin (name gin_trgm_ops)"
    )

    # === coefficients ===
    op.create_table(
        "coefficients",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("coef_type", sa.String(30), nullable=False),
        sa.Column("coef_key", sa.String(50), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("multiplier", sa.Numeric(4, 2), nullable=False),
        sa.Column("applies_to", sa.Text),
        sa.Column("when_use", sa.Text),
        sa.Column("note", sa.Text),
        sa.Column("sort_priority", sa.Integer, default=0),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("uq_coefficients_coef_key", "coefficients", ["coef_key"], unique=True)

    # === invites ===
    op.create_table(
        "invites",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("role_code", sa.String(30), nullable=False),
        sa.Column("branch_id", sa.Integer, sa.ForeignKey("branches.id")),
        sa.Column("profession_id", sa.Integer, sa.ForeignKey("professions.id")),
        sa.Column("max_uses", sa.Integer, default=1),
        sa.Column("used_count", sa.Integer, default=0),
        sa.Column("requires_approval", sa.Boolean, default=False),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_invites_code", "invites", ["code"], unique=True)
    op.create_index("ix_invites_active", "invites", ["is_active", "expires_at"])

    # === invite_activations ===
    op.create_table(
        "invite_activations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("invite_id", sa.Integer, sa.ForeignKey("invites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("approved_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("activated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_invite_activations_invite", "invite_activations", ["invite_id"])
    op.create_index("ix_invite_activations_user", "invite_activations", ["user_id"])

    # === orders ===
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("client_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("master_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("estimate_id", sa.Integer),  # FK added later to avoid circular
        sa.Column("status", sa.String(30), nullable=False, default="draft"),
        sa.Column("address", sa.Text),
        sa.Column("city", sa.String(100)),
        sa.Column("region", sa.String(100)),
        sa.Column("urgency", sa.String(20), default="normal"),
        sa.Column("preferred_time", sa.String(200)),
        sa.Column("notes", sa.Text),
        sa.Column("source_channel", sa.String(30), default="telegram"),
        sa.Column("cancellation_reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_orders_client", "orders", ["client_id"])
    op.create_index("ix_orders_master", "orders", ["master_id"])
    op.create_index("ix_orders_status", "orders", ["status"])

    # === estimates ===
    op.create_table(
        "estimates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("client_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("master_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("order_id", sa.Integer, sa.ForeignKey("orders.id")),
        sa.Column("status", sa.String(30), default="draft"),
        sa.Column("current_version_id", sa.Integer),
        sa.Column("note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_estimates_client", "estimates", ["client_id"])
    op.create_index("ix_estimates_master", "estimates", ["master_id"])
    op.create_index("ix_estimates_status", "estimates", ["status"])

    # Now add FK from orders.estimate_id to estimates
    op.create_foreign_key("fk_orders_estimate_id_estimates", "orders", "estimates", ["estimate_id"], ["id"])

    # === order_status_history ===
    op.create_table(
        "order_status_history",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("order_id", sa.Integer, sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_status", sa.String(30)),
        sa.Column("to_status", sa.String(30), nullable=False),
        sa.Column("changed_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_order_status_history_order", "order_status_history", ["order_id"])

    # === estimate_versions ===
    op.create_table(
        "estimate_versions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("estimate_id", sa.Integer, sa.ForeignKey("estimates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("reason", sa.Text),
        sa.Column("total_amount", sa.Integer, default=0),
        sa.Column("discount_amount", sa.Integer, default=0),
        sa.Column("final_amount", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_estimate_versions_estimate", "estimate_versions", ["estimate_id"])

    # === discount_requests ===
    op.create_table(
        "discount_requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("estimate_id", sa.Integer, sa.ForeignKey("estimates.id"), nullable=False),
        sa.Column("requested_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("discount_type", sa.String(20), nullable=False),
        sa.Column("discount_value", sa.Numeric(10, 2), nullable=False),
        sa.Column("scope", sa.String(20), default="estimate"),
        sa.Column("line_item_id", sa.Integer),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("comment", sa.Text),
        sa.Column("assigned_to", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("resolved_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("resolution_comment", sa.Text),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_discount_requests_status", "discount_requests", ["status"])
    op.create_index("ix_discount_requests_estimate", "discount_requests", ["estimate_id"])
    op.create_index("ix_discount_requests_approver", "discount_requests", ["assigned_to", "status"])

    # === estimate_line_items ===
    op.create_table(
        "estimate_line_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("version_id", sa.Integer, sa.ForeignKey("estimate_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("service_item_id", sa.Integer, sa.ForeignKey("service_items.id")),
        sa.Column("shared_operation_id", sa.Integer, sa.ForeignKey("shared_operations.id")),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), default=1),
        sa.Column("unit_price", sa.Integer, nullable=False),
        sa.Column("coefficients_applied", postgresql.JSONB),
        sa.Column("subtotal", sa.Integer, nullable=False),
        sa.Column("sort_order", sa.Integer, default=0),
    )
    op.create_index("ix_estimate_line_items_version", "estimate_line_items", ["version_id"])

    # === estimate_discounts ===
    op.create_table(
        "estimate_discounts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("version_id", sa.Integer, sa.ForeignKey("estimate_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("discount_request_id", sa.Integer, sa.ForeignKey("discount_requests.id")),
        sa.Column("discount_type", sa.String(20), nullable=False),
        sa.Column("discount_value", sa.Numeric(10, 2), nullable=False),
        sa.Column("amount", sa.Integer, nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("applied_to_line_item_id", sa.Integer, sa.ForeignKey("estimate_line_items.id")),
    )
    op.create_index("ix_estimate_discounts_version", "estimate_discounts", ["version_id"])

    # === payments ===
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("order_id", sa.Integer, sa.ForeignKey("orders.id")),
        sa.Column("estimate_id", sa.Integer, sa.ForeignKey("estimates.id")),
        sa.Column("amount_expected", sa.Integer, nullable=False),
        sa.Column("amount_paid", sa.Integer),
        sa.Column("currency", sa.String(5), default="RUB"),
        sa.Column("method", sa.String(30)),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("qr_payload", sa.Text),
        sa.Column("phone_number", sa.String(20)),
        sa.Column("proof_url", sa.Text),
        sa.Column("marked_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_payments_order", "payments", ["order_id"])
    op.create_index("ix_payments_status", "payments", ["status"])

    # === commission_policies ===
    op.create_table(
        "commission_policies",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("platform_fee_pct", sa.Numeric(5, 2), default=20.0),
        sa.Column("senior_master_share_pct", sa.Numeric(5, 2), default=5.0),
        sa.Column("admin_share_pct", sa.Numeric(5, 2), default=5.0),
        sa.Column("profession_id", sa.Integer, sa.ForeignKey("professions.id")),
        sa.Column("effective_from", sa.DateTime(timezone=True)),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # === commission_records ===
    op.create_table(
        "commission_records",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("payment_id", sa.Integer, sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("order_id", sa.Integer, sa.ForeignKey("orders.id")),
        sa.Column("policy_id", sa.Integer, sa.ForeignKey("commission_policies.id")),
        sa.Column("gross_total", sa.Integer, nullable=False),
        sa.Column("discount_total", sa.Integer, default=0),
        sa.Column("net_total", sa.Integer, nullable=False),
        sa.Column("platform_fee", sa.Integer, nullable=False),
        sa.Column("senior_master_share", sa.Integer, default=0),
        sa.Column("senior_master_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("admin_share", sa.Integer, default=0),
        sa.Column("admin_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("master_net", sa.Integer, nullable=False),
        sa.Column("master_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_commission_records_payment", "commission_records", ["payment_id"])
    op.create_index("ix_commission_records_master", "commission_records", ["master_id"])
    op.create_index("ix_commission_records_senior", "commission_records", ["senior_master_id"])

    # === notification_templates ===
    op.create_table(
        "notification_templates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("title_template", sa.Text, nullable=False),
        sa.Column("body_template", sa.Text, nullable=False),
        sa.Column("channel", sa.String(20), default="telegram"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
    )
    op.create_index("uq_notification_templates_code", "notification_templates", ["code"], unique=True)

    # === notifications ===
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("channel", sa.String(20), default="telegram"),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("entity_type", sa.String(40)),
        sa.Column("entity_id", sa.Integer),
        sa.Column("retry_count", sa.Integer, default=0),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_notifications_user_status", "notifications", ["user_id", "status"])
    op.create_index("ix_notifications_type", "notifications", ["event_type"])

    # === approval_requests ===
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("approval_type", sa.String(30), nullable=False),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("entity_id", sa.Integer, nullable=False),
        sa.Column("requested_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_to", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("comment", sa.Text),
        sa.Column("resolution_comment", sa.Text),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_approval_requests_assigned_status", "approval_requests", ["assigned_to", "status"])
    op.create_index("ix_approval_requests_entity", "approval_requests", ["entity_type", "entity_id"])

    # === staffing_actions ===
    op.create_table(
        "staffing_actions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("action_type", sa.String(30), nullable=False),
        sa.Column("target_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("initiated_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("metadata", postgresql.JSONB),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_staffing_actions_target", "staffing_actions", ["target_user_id"])
    op.create_index("ix_staffing_actions_status", "staffing_actions", ["status"])

    # === audit_log ===
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("entity_id", sa.Integer),
        sa.Column("old_value", postgresql.JSONB),
        sa.Column("new_value", postgresql.JSONB),
        sa.Column("ip_address", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"])
    op.create_index("ix_audit_log_user", "audit_log", ["user_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_created", "audit_log", ["created_at"])

    # === feature_flags ===
    op.create_table(
        "feature_flags",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("module", sa.String(40)),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("updated_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("uq_feature_flags_code", "feature_flags", ["code"], unique=True)

    # === system_settings ===
    op.create_table(
        "system_settings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", postgresql.JSONB),
        sa.Column("description", sa.Text),
        sa.Column("updated_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("uq_system_settings_key", "system_settings", ["key"], unique=True)

    # === prompt_templates ===
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, default=1),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("uq_prompt_templates_code", "prompt_templates", ["code"], unique=True)

    # === ai_request_logs ===
    op.create_table(
        "ai_request_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model", sa.String(60)),
        sa.Column("prompt_template_id", sa.Integer, sa.ForeignKey("prompt_templates.id")),
        sa.Column("input_text", sa.Text),
        sa.Column("output_text", sa.Text),
        sa.Column("tokens_used", sa.Integer),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("status", sa.String(20), default="success"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("ai_request_logs")
    op.drop_table("prompt_templates")
    op.drop_table("system_settings")
    op.drop_table("feature_flags")
    op.drop_table("audit_log")
    op.drop_table("staffing_actions")
    op.drop_table("approval_requests")
    op.drop_table("notifications")
    op.drop_table("notification_templates")
    op.drop_table("commission_records")
    op.drop_table("commission_policies")
    op.drop_table("payments")
    op.drop_table("estimate_discounts")
    op.drop_table("estimate_line_items")
    op.drop_table("estimate_versions")
    op.drop_table("discount_requests")
    op.drop_table("order_status_history")
    # Drop FK before dropping tables
    op.drop_constraint("fk_orders_estimate_id_estimates", "orders", type_="foreignkey")
    op.drop_table("estimates")
    op.drop_table("orders")
    op.drop_table("invite_activations")
    op.drop_table("invites")
    op.drop_table("coefficients")
    op.drop_table("service_items")
    op.drop_table("shared_operations")
    op.drop_table("service_subgroups")
    op.drop_table("service_groups")
    op.drop_table("professions")
    op.drop_table("branch_members")
    op.drop_table("branches")
    op.drop_table("user_roles")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
