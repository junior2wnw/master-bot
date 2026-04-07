"""Tests for RBAC permission system."""

from types import SimpleNamespace

import pytest

from app.core.security import (
    Permission, Role, can_assign_order, can_create_order_from_estimate, can_manage_user,
    effective_role_codes, estimate_action_capabilities, get_active_role_code, get_active_role_label, get_available_role_codes,
    get_effective_role_codes, get_permissions, get_max_role_label, has_permission,
    has_permission_for_roles, has_role, has_role_switch_access, highest_role_code,
    highest_role_label, is_role_switch_overridden, require_permission, role_codes_with_inheritance,
)
from app.core.exceptions import PermissionDenied


class TestRolePermissions:
    def test_product_owner_has_all_permissions(self, owner):
        """Product owner should have every permission."""
        all_perms = set(Permission)
        owner_perms = get_permissions([Role.PRODUCT_OWNER])
        assert owner_perms == all_perms

    def test_admin_has_catalog_edit(self, admin):
        assert has_permission(admin, Permission.CATALOG_EDIT)

    def test_admin_has_admin_panel(self, admin):
        assert has_permission(admin, Permission.ADMIN_PANEL)

    def test_admin_inherits_senior_master_permissions(self, admin):
        assert has_permission(admin, Permission.DISCOUNT_APPROVE_BRANCH)

    def test_admin_lacks_owner_panel(self, admin):
        assert not has_permission(admin, Permission.OWNER_PANEL)

    def test_master_can_create_estimates(self, master):
        assert has_permission(master, Permission.ESTIMATE_CREATE)

    def test_master_cannot_edit_catalog(self, master):
        assert not has_permission(master, Permission.CATALOG_EDIT)

    def test_master_cannot_approve_discounts_globally(self, master):
        assert not has_permission(master, Permission.DISCOUNT_APPROVE_ALL)

    def test_senior_master_can_approve_branch_discounts(self, senior_master):
        assert has_permission(senior_master, Permission.DISCOUNT_APPROVE_BRANCH)

    def test_senior_master_cannot_approve_all_discounts(self, senior_master):
        assert not has_permission(senior_master, Permission.DISCOUNT_APPROVE_ALL)

    def test_client_can_view_catalog(self, client):
        assert has_permission(client, Permission.CATALOG_VIEW)

    def test_client_cannot_create_estimates(self, client):
        assert not has_permission(client, Permission.ESTIMATE_CREATE)

    def test_client_can_create_orders(self, client):
        assert has_permission(client, Permission.ORDER_CREATE)


class TestRequirePermission:
    def test_raises_on_missing_permission(self, client):
        with pytest.raises(PermissionDenied):
            require_permission(client, Permission.CATALOG_EDIT)

    def test_passes_on_valid_permission(self, admin):
        require_permission(admin, Permission.CATALOG_EDIT)  # Should not raise


class TestHasRole:
    def test_has_role_true(self, admin):
        assert has_role(admin, Role.ADMIN)

    def test_has_role_false(self, master):
        assert not has_role(master, Role.ADMIN)

    def test_multi_role(self, senior_master):
        assert has_role(senior_master, Role.SENIOR_MASTER)
        assert has_role(senior_master, Role.MASTER)

    def test_owner_inherits_admin_and_master_roles(self, owner):
        assert has_role(owner, Role.ADMIN)
        assert has_role(owner, Role.MASTER)


class TestRoleInheritanceHelpers:
    def test_role_codes_with_inheritance(self):
        assert role_codes_with_inheritance([Role.ADMIN]) == [
            Role.MASTER.value,
            Role.SENIOR_MASTER.value,
            Role.ADMIN.value,
        ]

    def test_effective_role_codes_for_owner_include_entire_staff_chain(self):
        assert effective_role_codes([Role.PRODUCT_OWNER]) == [
            Role.MASTER.value,
            Role.SENIOR_MASTER.value,
            Role.ADMIN.value,
            Role.PRODUCT_OWNER.value,
        ]

    def test_has_permission_for_roles_uses_inheritance(self):
        assert has_permission_for_roles([Role.ADMIN.value], Permission.ESTIMATE_CREATE)

    def test_highest_role_helpers_collapse_inherited_chain(self):
        assert highest_role_code([Role.PRODUCT_OWNER.value]) == Role.PRODUCT_OWNER.value
        assert highest_role_label([Role.ADMIN.value]) == "Администратор"

    def test_owner_can_switch_between_all_inherited_staff_roles(self, owner):
        assert get_available_role_codes(owner) == [
            Role.CLIENT.value,
            Role.MASTER.value,
            Role.SENIOR_MASTER.value,
            Role.ADMIN.value,
            Role.PRODUCT_OWNER.value,
        ]
        assert has_role_switch_access(owner)

    def test_active_role_override_limits_permissions_to_selected_context(self, owner):
        owner.active_role_code = Role.MASTER.value

        assert get_effective_role_codes(owner) == [Role.MASTER.value]
        assert get_active_role_code(owner) == Role.MASTER.value
        assert get_active_role_label(owner) == "Мастер"
        assert get_max_role_label(owner) == "Product Owner"
        assert is_role_switch_overridden(owner)
        assert has_permission(owner, Permission.ESTIMATE_CREATE)
        assert not has_permission(owner, Permission.OWNER_PANEL)

    def test_owner_can_switch_to_client_test_context(self, owner):
        owner.active_role_code = Role.CLIENT.value

        assert get_effective_role_codes(owner) == [Role.CLIENT.value]
        assert get_active_role_code(owner) == Role.CLIENT.value
        assert get_active_role_label(owner) == "Клиент"
        assert not has_permission(owner, Permission.ESTIMATE_CREATE)
        assert has_permission(owner, Permission.ORDER_CREATE)


class TestAccessCapabilities:
    def test_admin_can_assign_only_submitted_orders(self, admin):
        submitted = SimpleNamespace(status="submitted", client_id=5, master_id=None)
        completed = SimpleNamespace(status="completed", client_id=5, master_id=None)

        assert can_assign_order(admin, submitted, master_id=admin.id)
        assert not can_assign_order(admin, completed, master_id=admin.id)

    def test_master_draft_capabilities_include_delete(self, master):
        estimate = SimpleNamespace(status="draft", client_id=5, master_id=master.id)
        capabilities = estimate_action_capabilities(master, estimate)

        assert capabilities["can_edit"] is True
        assert capabilities["can_delete"] is True

    def test_create_order_from_estimate_requires_client_and_approved_status(self, client, admin):
        approved_for_client = SimpleNamespace(status="approved", client_id=client.id, master_id=4)
        foreign_estimate = SimpleNamespace(status="approved", client_id=999, master_id=4)
        draft_for_client = SimpleNamespace(status="draft", client_id=client.id, master_id=4)

        assert can_create_order_from_estimate(client, approved_for_client)
        assert not can_create_order_from_estimate(client, foreign_estimate)
        assert not can_create_order_from_estimate(client, draft_for_client)
        assert not can_create_order_from_estimate(admin, approved_for_client)


class TestCanManageUser:
    def test_admin_can_manage_anyone(self, admin, master, senior_master, client):
        assert can_manage_user(admin, master)
        assert can_manage_user(admin, senior_master)
        assert can_manage_user(admin, client)

    def test_owner_can_manage_anyone(self, owner, admin, master):
        assert can_manage_user(owner, admin)
        assert can_manage_user(owner, master)

    def test_admin_cannot_manage_owner(self, admin, owner):
        assert not can_manage_user(admin, owner)

    def test_senior_master_can_manage_own_branch(self, senior_master, master):
        assert can_manage_user(senior_master, master)

    def test_senior_master_cannot_manage_other_branch(self, senior_master, other_branch_master):
        assert not can_manage_user(senior_master, other_branch_master)

    def test_master_cannot_manage_others(self, master, client):
        assert not can_manage_user(master, client)

    def test_client_cannot_manage_anyone(self, client, master):
        assert not can_manage_user(client, master)
