"""Tests for feature flag / module registry."""

from app.core.module_registry import _flags, is_enabled


class TestModuleRegistry:
    def setup_method(self):
        _flags.clear()

    def test_default_enabled(self):
        assert is_enabled("nonexistent_flag", default=True) is True

    def test_default_disabled(self):
        assert is_enabled("nonexistent_flag", default=False) is False

    def test_flag_enabled(self):
        _flags["test.flag"] = True
        assert is_enabled("test.flag") is True

    def test_flag_disabled(self):
        _flags["test.flag"] = False
        assert is_enabled("test.flag") is False

    def test_module_check(self):
        _flags["module.discounts"] = True
        _flags["module.ai_intake"] = False
        assert is_enabled("module.discounts")
        assert not is_enabled("module.ai_intake")
