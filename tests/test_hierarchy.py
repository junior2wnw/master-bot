"""Tests for hierarchy permission checks."""

from app.core.security import Role, can_manage_user, has_role, is_in_branch, is_senior_in_branch


class TestHierarchy:
    def test_senior_master_is_in_branch(self, senior_master):
        assert is_in_branch(senior_master, 1)
        assert not is_in_branch(senior_master, 2)
        assert is_senior_in_branch(senior_master, 1)
        assert not is_senior_in_branch(senior_master, 2)

    def test_master_is_in_branch(self, master):
        assert is_in_branch(master, 1)
        assert not is_in_branch(master, 99)
        assert not is_senior_in_branch(master, 1)

    def test_admin_can_manage_any_master(self, admin, master, other_branch_master):
        assert can_manage_user(admin, master)
        assert can_manage_user(admin, other_branch_master)

    def test_senior_manages_own_branch_only(self, senior_master, master, other_branch_master):
        # master is in branch 1, senior_master is senior of branch 1
        assert can_manage_user(senior_master, master)
        # other_branch_master is in branch 2
        assert not can_manage_user(senior_master, other_branch_master)

    def test_master_cannot_manage_others(self, master, other_branch_master, client):
        assert not can_manage_user(master, other_branch_master)
        assert not can_manage_user(master, client)

    def test_multi_role_user(self, senior_master):
        """Senior master also has master role."""
        assert has_role(senior_master, Role.SENIOR_MASTER)
        assert has_role(senior_master, Role.MASTER)
        assert not has_role(senior_master, Role.ADMIN)
