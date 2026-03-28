"""RBAC engine. Role hierarchy, permissions, and access helpers."""

from enum import StrEnum
from typing import TYPE_CHECKING, Iterable

from app.core.exceptions import PermissionDenied

if TYPE_CHECKING:
    from app.models.estimate import Estimate
    from app.models.order import Order
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


# Staff hierarchy: each next role inherits the previous one.
ROLE_INHERITANCE: dict[Role, tuple[Role, ...]] = {
    Role.CLIENT: (),
    Role.MASTER: (),
    Role.SENIOR_MASTER: (Role.MASTER,),
    Role.ADMIN: (Role.SENIOR_MASTER,),
    Role.PRODUCT_OWNER: (Role.ADMIN,),
}

ROLE_ORDER: tuple[Role, ...] = (
    Role.CLIENT,
    Role.MASTER,
    Role.SENIOR_MASTER,
    Role.ADMIN,
    Role.PRODUCT_OWNER,
)

ROLE_LABELS: dict[Role, str] = {
    Role.CLIENT: "Клиент",
    Role.MASTER: "Мастер",
    Role.SENIOR_MASTER: "Старший мастер",
    Role.ADMIN: "Администратор",
    Role.PRODUCT_OWNER: "Product Owner",
}

# Extra switch-only contexts for testing flows.
# These do not change real role inheritance in RBAC; they only widen
# the temporary role-mode picker for trusted top-level operators.
ROLE_SWITCH_EXTRAS: dict[Role, tuple[Role, ...]] = {
    Role.PRODUCT_OWNER: (Role.CLIENT,),
}


# Direct permissions only. Inheritance is resolved dynamically.
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
        Permission.ESTIMATE_VIEW_BRANCH,
        Permission.DISCOUNT_APPROVE_BRANCH,
        Permission.ORDER_VIEW_BRANCH,
        Permission.USER_VIEW_BRANCH,
        Permission.BRANCH_MANAGE_OWN,
        Permission.STAFFING_INITIATE_BRANCH,
        Permission.COMMISSION_VIEW,
        Permission.ANALYTICS_VIEW_BRANCH,
    },
    Role.ADMIN: {
        Permission.CATALOG_EDIT,
        Permission.ESTIMATE_VIEW_ALL,
        Permission.ESTIMATE_APPROVE,
        Permission.DISCOUNT_APPROVE_ALL,
        Permission.ORDER_CREATE,
        Permission.ORDER_VIEW_ALL,
        Permission.USER_VIEW_ALL,
        Permission.USER_MANAGE,
        Permission.BRANCH_MANAGE,
        Permission.INVITE_CREATE,
        Permission.INVITE_MODERATE,
        Permission.STAFFING_INITIATE_ALL,
        Permission.STAFFING_APPROVE,
        Permission.PAYMENT_VIEW_ALL,
        Permission.COMMISSION_CONFIGURE,
        Permission.NOTIFICATION_CONFIGURE,
        Permission.FEATURE_FLAG_MANAGE,
        Permission.SETTINGS_MANAGE,
        Permission.AUDIT_VIEW,
        Permission.ANALYTICS_VIEW_ALL,
        Permission.AI_CONFIGURE,
        Permission.ADMIN_PANEL,
    },
    Role.PRODUCT_OWNER: {
        Permission.OWNER_PANEL,
    },
}


def _coerce_role(role: Role | str) -> Role:
    return role if isinstance(role, Role) else Role(role)


def expand_roles(roles: Iterable[Role | str]) -> set[Role]:
    """Expand direct roles with inherited roles."""
    resolved: set[Role] = set()
    stack = [_coerce_role(role) for role in roles]

    while stack:
        role = stack.pop()
        if role in resolved:
            continue
        resolved.add(role)
        stack.extend(ROLE_INHERITANCE.get(role, ()))

    return resolved


def role_codes_with_inheritance(roles: Iterable[Role | str]) -> list[str]:
    expanded = expand_roles(roles)
    return [role.value for role in ROLE_ORDER if role in expanded]


def effective_role_codes(roles: Iterable[Role | str]) -> list[str]:
    """Alias with a clearer name for UI-facing code."""
    return role_codes_with_inheritance(roles)


def highest_role(roles: Iterable[Role | str]) -> Role | None:
    """Return the highest role in the inheritance chain."""
    expanded = expand_roles(roles)
    for role in reversed(ROLE_ORDER):
        if role in expanded:
            return role
    return None


def highest_role_code(roles: Iterable[Role | str]) -> str | None:
    role = highest_role(roles)
    return role.value if role else None


def highest_role_label(roles: Iterable[Role | str]) -> str:
    role = highest_role(roles)
    if role is None:
        return "Без роли"
    return ROLE_LABELS.get(role, role.value)


def get_direct_role_codes(user: "User") -> list[str]:
    return [role.role_code for role in getattr(user, "roles", [])]


def get_available_role_codes(user: "User") -> list[str]:
    direct_roles = {_coerce_role(role_code) for role_code in get_direct_role_codes(user)}
    available_roles = expand_roles(direct_roles)
    for role in tuple(available_roles):
        available_roles.update(ROLE_SWITCH_EXTRAS.get(role, ()))
    return [role.value for role in ROLE_ORDER if role in available_roles]


def get_max_role_code(user: "User") -> str | None:
    return highest_role_code(get_direct_role_codes(user))


def get_max_role_label(user: "User") -> str:
    return highest_role_label(get_direct_role_codes(user))


def get_role_context_seed_codes(user: "User") -> list[str]:
    direct_roles = get_direct_role_codes(user)
    available_roles = set(get_available_role_codes(user))
    active_role_code = getattr(user, "active_role_code", None)
    if active_role_code and active_role_code in available_roles:
        return [active_role_code]
    return direct_roles


def get_effective_role_codes(user: "User") -> list[str]:
    return role_codes_with_inheritance(get_role_context_seed_codes(user))


def get_active_role_code(user: "User") -> str | None:
    return highest_role_code(get_effective_role_codes(user))


def get_active_role_label(user: "User") -> str:
    return highest_role_label(get_effective_role_codes(user))


def has_role_switch_access(user: "User") -> bool:
    return len(get_available_role_codes(user)) > 1


def is_role_switch_overridden(user: "User") -> bool:
    active_role_code = getattr(user, "active_role_code", None)
    return bool(active_role_code and active_role_code in set(get_available_role_codes(user)))


def get_permissions(roles: Iterable[Role | str]) -> set[Permission]:
    """Merge permissions from direct roles and their inheritance chain."""
    expanded_roles = expand_roles(roles)
    if Role.PRODUCT_OWNER in expanded_roles:
        return set(Permission)

    result: set[Permission] = set()
    for role in expanded_roles:
        result |= ROLE_PERMISSIONS.get(role, set())
    return result


def has_permission_for_roles(
    roles: Iterable[Role | str],
    permission: Permission | str,
) -> bool:
    resolved_permission = permission if isinstance(permission, Permission) else Permission(permission)
    return resolved_permission in get_permissions(roles)


def get_user_roles(user: "User", *, inherited: bool = True) -> set[Role]:
    role_seed = {_coerce_role(role_code) for role_code in get_role_context_seed_codes(user)}
    return expand_roles(role_seed) if inherited else role_seed


def has_permission(user: "User", permission: Permission) -> bool:
    """Check if user has a specific permission."""
    return permission in get_permissions(get_user_roles(user, inherited=False))


def require_permission(user: "User", permission: Permission) -> None:
    """Raise PermissionDenied if user lacks the permission."""
    if not has_permission(user, permission):
        raise PermissionDenied(f"Требуется право: {permission.value}")


def has_role(user: "User", role: Role) -> bool:
    """Check if user has a role, including inherited roles."""
    return role in get_user_roles(user)


def has_any_role(user: "User", *roles: Role) -> bool:
    return any(has_role(user, role) for role in roles)


def has_role_code(roles: Iterable[Role | str], role: Role | str) -> bool:
    return _coerce_role(role) in expand_roles(roles)


def is_in_branch(user: "User", branch_id: int) -> bool:
    """Check if user belongs to a specific branch."""
    if not hasattr(user, "branch_memberships"):
        return False
    return any(m.branch_id == branch_id for m in user.branch_memberships)


def is_senior_in_branch(user: "User", branch_id: int) -> bool:
    """Check if user is the active senior master of a specific branch."""
    if not hasattr(user, "branch_memberships"):
        return False
    return any(
        m.branch_id == branch_id
        and getattr(m, "is_senior", False)
        and getattr(m, "is_active", True)
        for m in user.branch_memberships
    )


def can_manage_user(actor: "User", target: "User") -> bool:
    """Check if actor can perform staffing actions on target.

    Rules:
    - product_owner can manage anyone
    - admin can manage everyone except product_owner
    - senior_master can manage only masters in their branch
    """
    if has_role(actor, Role.PRODUCT_OWNER):
        return True
    if has_role(actor, Role.ADMIN):
        return not has_role(target, Role.PRODUCT_OWNER)
    if has_role(actor, Role.SENIOR_MASTER):
        if has_role(target, Role.SENIOR_MASTER):
            return False
        actor_branches = {m.branch_id for m in actor.branch_memberships if m.is_senior}
        target_branches = {m.branch_id for m in target.branch_memberships}
        return bool(actor_branches & target_branches)
    return False


def can_create_estimate(user: "User") -> bool:
    return has_permission(user, Permission.ESTIMATE_CREATE)


def can_view_estimate(user: "User", estimate: "Estimate") -> bool:
    if has_permission(user, Permission.ESTIMATE_VIEW_ALL):
        return True
    return estimate.master_id == user.id or estimate.client_id == user.id


def can_edit_estimate(user: "User", estimate: "Estimate") -> bool:
    return (
        has_permission(user, Permission.ESTIMATE_CREATE)
        and estimate.master_id == user.id
        and estimate.status == "draft"
    )


def can_send_estimate_to_client(user: "User", estimate: "Estimate") -> bool:
    return can_edit_estimate(user, estimate)


def can_request_discount_for_estimate(user: "User", estimate: "Estimate") -> bool:
    return can_edit_estimate(user, estimate)


def can_respond_to_estimate(user: "User", estimate: "Estimate") -> bool:
    if has_permission(user, Permission.ESTIMATE_APPROVE):
        return True
    return estimate.client_id == user.id and estimate.status == "client_review"


def can_create_order_from_estimate(user: "User", estimate: "Estimate") -> bool:
    return (
        has_permission(user, Permission.ORDER_CREATE)
        and estimate.client_id == user.id
        and estimate.status == "approved"
    )


def estimate_action_capabilities(user: "User", estimate: "Estimate") -> dict[str, bool]:
    can_view = can_view_estimate(user, estimate)
    can_edit = can_edit_estimate(user, estimate)
    can_respond = can_respond_to_estimate(user, estimate)
    return {
        "can_view": can_view,
        "can_edit": can_edit,
        "can_request_discount": can_request_discount_for_estimate(user, estimate),
        "can_send_to_client": can_send_estimate_to_client(user, estimate),
        "can_client_respond": can_respond,
        "can_create_order": can_create_order_from_estimate(user, estimate),
        "can_export": can_view,
    }


def can_view_order(user: "User", order: "Order") -> bool:
    if has_permission(user, Permission.ORDER_VIEW_ALL):
        return True
    return order.client_id == user.id or order.master_id == user.id


def can_submit_order(user: "User", order: "Order") -> bool:
    return order.client_id == user.id and order.status == "draft"


def can_assign_order(user: "User", order: "Order", *, master_id: int | None = None) -> bool:
    if order.status != "submitted":
        return False
    if has_permission(user, Permission.ORDER_VIEW_ALL):
        return True
    target_master_id = user.id if master_id is None else master_id
    return (
        has_permission(user, Permission.ESTIMATE_CREATE)
        and target_master_id == user.id
        and order.master_id in (None, user.id)
    )


def can_start_order(user: "User", order: "Order") -> bool:
    return order.master_id == user.id and order.status == "assigned"


def can_complete_order(user: "User", order: "Order") -> bool:
    return order.master_id == user.id and order.status == "in_progress"


def can_cancel_order(user: "User", order: "Order") -> bool:
    if order.status in {"paid", "cancelled", "completed"}:
        return False
    if has_permission(user, Permission.ORDER_VIEW_ALL):
        return True
    return order.client_id == user.id or order.master_id == user.id


def can_pay_order(user: "User", order: "Order") -> bool:
    if order.status != "completed":
        return False
    if has_permission(user, Permission.ORDER_VIEW_ALL):
        return True
    return order.client_id == user.id


def order_action_capabilities(user: "User", order: "Order") -> dict[str, bool]:
    can_view = can_view_order(user, order)
    return {
        "can_view": can_view,
        "can_submit": can_submit_order(user, order),
        "can_assign": can_assign_order(user, order),
        "can_start": can_start_order(user, order),
        "can_complete": can_complete_order(user, order),
        "can_cancel": can_cancel_order(user, order),
        "can_pay": can_pay_order(user, order),
    }
