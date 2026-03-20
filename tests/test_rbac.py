"""Tests for RBAC permission system."""

import pytest

from app.core.security import (
    Permission, Role, can_manage_user, get_permissions, has_permission, has_role,
    require_permission,
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


class TestCanManageUser:
    def test_admin_can_manage_anyone(self, admin, master, senior_master, client):
        assert can_manage_user(admin, master)
        assert can_manage_user(admin, senior_master)
        assert can_manage_user(admin, client)

    def test_owner_can_manage_anyone(self, owner, admin, master):
        assert can_manage_user(owner, admin)
        assert can_manage_user(owner, master)

    def test_senior_master_can_manage_own_branch(self, senior_master, master):
        assert can_manage_user(senior_master, master)

    def test_senior_master_cannot_manage_other_branch(self, senior_master, other_branch_master):
        assert not can_manage_user(senior_master, other_branch_master)

    def test_master_cannot_manage_others(self, master, client):
        assert not can_manage_user(master, client)

    def test_client_cannot_manage_anyone(self, client, master):
        assert not can_manage_user(client, master)
