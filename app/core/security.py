"""RBAC engine. Role checks, permission matrix, hierarchy validation."""

from enum import StrEnum
from typing import TYPE_CHECKING

from app.core.exceptions import PermissionDenied

if TYPE_CHECKING:
    from app.models.user import User


class Role(StrEnum):
    PRODUCT_OWNER = "product_owner"
    ADMIN = "admin"
    SENIOR_MASTER = "senior_master"
    MASTER = "master"
    CLIENT = "client"


class Permission(StrEnum):
    # Catalog
    CATALOG_VIEW = "catalog.view"
    CATALOG_EDIT = "catalog.edit"

    # Estimates
    ESTIMATE_CREATE = "estimate.create"
    ESTIMATE_VIEW_OWN = "estimate.view_own"
    ESTIMATE_VIEW_BRANCH = "estimate.view_branch"
    ESTIMATE_VIEW_ALL = "estimate.view_all"
    ESTIMATE_APPROVE = "estimate.approve"

    # Discounts
    DISCOUNT_REQUEST = "discount.request"
    DISCOUNT_APPROVE_BRANCH = "discount.approve_branch"
    DISCOUNT_APPROVE_ALL = "discount.approve_all"

    # Orders
    ORDER_CREATE = "order.create"
    ORDER_VIEW_OWN = "order.view_own"
    ORDER_VIEW_BRANCH = "order.view_branch"
    ORDER_VIEW_ALL = "order.view_all"

    # Users & Hierarchy
    USER_VIEW_OWN = "user.view_own"
    USER_VIEW_BRANCH = "user.view_branch"
    USER_VIEW_ALL = "user.view_all"
    USER_MANAGE = "user.manage"
    BRANCH_MANAGE = "branch.manage"
    BRANCH_MANAGE_OWN = "branch.manage_own"

    # Invites
    INVITE_CREATE = "invite.create"
    INVITE_CREATE_BRANCH = "invite.create_branch"
    INVITE_MODERATE = "invite.moderate"

    # Staffing
    STAFFING_INITIATE_BRANCH = "staffing.initiate_branch"
    STAFFING_INITIATE_ALL = "staffing.initiate_all"
    STAFFING_APPROVE = "staffing.approve"

    # Payments & Commissions
    PAYMENT_VIEW_OWN = "payment.view_own"
    PAYMENT_VIEW_ALL = "payment.view_all"
    COMMISSION_VIEW = "commission.view"
    COMMISSION_CONFIGURE = "commission.configure"

    # Notifications
    NOTIFICATION_CONFIGURE = "notification.configure"

    # Feature Flags & Settings
    FEATURE_FLAG_MANAGE = "feature_flag.manage"
    SETTINGS_MANAGE = "settings.manage"

    # Audit & Analytics
    AUDIT_VIEW = "audit.view"
    ANALYTICS_VIEW_OWN = "analytics.view_own"
    ANALYTICS_VIEW_BRANCH = "analytics.view_branch"
    ANALYTICS_VIEW_ALL = "analytics.view_all"

    # AI
    AI_CONFIGURE = "ai.configure"

    # Admin / Owner panels
    ADMIN_PANEL = "admin.panel"
    OWNER_PANEL = "owner.panel"


# Role → permissions matrix. Compact, explicit, no hidden magic.
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.CLIENT: {
        Permission.CATALOG_VIEW,
        Permission.ESTIMATE_VIEW_OWN,
        Permission.ORDER_CREATE,
        Permission.ORDER_VIEW_OWN,
        Permission.USER_VIEW_OWN,
        Permission.PAYMENT_VIEW_OWN,
        Permission.ANALYTICS_VIEW_OWN,
    },
    Role.MASTER: {
        Permission.CATALOG_VIEW,
        Permission.ESTIMATE_CREATE,
        Permission.ESTIMATE_VIEW_OWN,
        Permission.DISCOUNT_REQUEST,
        Permission.ORDER_VIEW_OWN,
        Permission.USER_VIEW_OWN,
        Permission.PAYMENT_VIEW_OWN,
        Permission.ANALYTICS_VIEW_OWN,
        Permission.INVITE_CREATE_BRANCH,
    },
    Role.SENIOR_MASTER: {
        Permission.CATALOG_VIEW,
        Permission.ESTIMATE_CREATE,
        Permission.ESTIMATE_VIEW_OWN,
        Permission.ESTIMATE_VIEW_BRANCH,
        Permission.DISCOUNT_REQUEST,
        Permission.DISCOUNT_APPROVE_BRANCH,
        Permission.ORDER_VIEW_OWN,
        Permission.ORDER_VIEW_BRANCH,
        Permission.USER_VIEW_OWN,
        Permission.USER_VIEW_BRANCH,
        Permission.BRANCH_MANAGE_OWN,
        Permission.INVITE_CREATE_BRANCH,
        Permission.STAFFING_INITIATE_BRANCH,
        Permission.PAYMENT_VIEW_OWN,
        Permission.COMMISSION_VIEW,
        Permission.ANALYTICS_VIEW_OWN,
        Permission.ANALYTICS_VIEW_BRANCH,
    },
    Role.ADMIN: {
        Permission.CATALOG_VIEW,
        Permission.CATALOG_EDIT,
        Permission.ESTIMATE_CREATE,
        Permission.ESTIMATE_VIEW_OWN,
        Permission.ESTIMATE_VIEW_BRANCH,
        Permission.ESTIMATE_VIEW_ALL,
        Permission.ESTIMATE_APPROVE,
        Permission.DISCOUNT_REQUEST,
        Permission.DISCOUNT_APPROVE_BRANCH,
        Permission.DISCOUNT_APPROVE_ALL,
        Permission.ORDER_CREATE,
        Permission.ORDER_VIEW_OWN,
        Permission.ORDER_VIEW_BRANCH,
        Permission.ORDER_VIEW_ALL,
        Permission.USER_VIEW_OWN,
        Permission.USER_VIEW_BRANCH,
        Permission.USER_VIEW_ALL,
        Permission.USER_MANAGE,
        Permission.BRANCH_MANAGE,
        Permission.BRANCH_MANAGE_OWN,
        Permission.INVITE_CREATE,
        Permission.INVITE_CREATE_BRANCH,
        Permission.INVITE_MODERATE,
        Permission.STAFFING_INITIATE_BRANCH,
        Permission.STAFFING_INITIATE_ALL,
        Permission.STAFFING_APPROVE,
        Permission.PAYMENT_VIEW_OWN,
        Permission.PAYMENT_VIEW_ALL,
        Permission.COMMISSION_VIEW,
        Permission.COMMISSION_CONFIGURE,
        Permission.NOTIFICATION_CONFIGURE,
        Permission.FEATURE_FLAG_MANAGE,
        Permission.SETTINGS_MANAGE,
        Permission.AUDIT_VIEW,
        Permission.ANALYTICS_VIEW_OWN,
        Permission.ANALYTICS_VIEW_BRANCH,
        Permission.ANALYTICS_VIEW_ALL,
        Permission.AI_CONFIGURE,
        Permission.ADMIN_PANEL,
    },
    Role.PRODUCT_OWNER: set(Permission),  # All permissions
}


def get_permissions(roles: list[Role]) -> set[Permission]:
    """Merge permissions from all user roles."""
    result: set[Permission] = set()
    for role in roles:
        result |= ROLE_PERMISSIONS.get(role, set())
    return result


def has_permission(user: "User", permission: Permission) -> bool:
    """Check if user has a specific permission through any of their roles."""
    user_roles = [Role(r.role_code) for r in user.roles]
    return permission in get_permissions(user_roles)


def require_permission(user: "User", permission: Permission) -> None:
    """Raise PermissionDenied if user lacks the permission."""
    if not has_permission(user, permission):
        raise PermissionDenied(f"Требуется право: {permission.value}")


def has_role(user: "User", role: Role) -> bool:
    """Check if user has a specific role."""
    return any(r.role_code == role.value for r in user.roles)


def is_in_branch(user: "User", branch_id: int) -> bool:
    """Check if user belongs to a specific branch."""
    if not hasattr(user, "branch_memberships"):
        return False
    return any(m.branch_id == branch_id for m in user.branch_memberships)


def can_manage_user(actor: "User", target: "User") -> bool:
    """Check if actor can perform staffing actions on target.

    Rules:
    - product_owner/admin can manage anyone
    - senior_master can manage only masters in their branch
    """
    if has_role(actor, Role.PRODUCT_OWNER) or has_role(actor, Role.ADMIN):
        return True
    if has_role(actor, Role.SENIOR_MASTER):
        actor_branches = {m.branch_id for m in actor.branch_memberships if m.is_senior}
        target_branches = {m.branch_id for m in target.branch_memberships}
        return bool(actor_branches & target_branches)
    return False
