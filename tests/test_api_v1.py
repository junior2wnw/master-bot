"""Tests for REST API v1 — auth validation, catalog endpoints, estimate operations."""

import hashlib
import hmac
import json
import time
from urllib.parse import quote

from app.api.v1 import _validate_init_data


class TestInitDataValidation:
    """Test signed Mini App initData HMAC validation."""

    def _make_init_data(self, user_data: dict, bot_token: str) -> str:
        """Generate valid initData string with correct HMAC."""
        user_json = json.dumps(user_data, separators=(',', ':'))
        auth_date = str(int(time.time()))

        params = {
            "user": user_json,
            "auth_date": auth_date,
        }

        # Build data-check-string
        items = sorted(f"{k}={v}" for k, v in params.items())
        data_check_string = "\n".join(items)

        # Compute HMAC
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        hash_value = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        # Build query string
        parts = [f"{k}={v}" for k, v in params.items()]
        parts.append(f"hash={hash_value}")
        return "&".join(parts)

    def test_valid_init_data(self):
        """Valid initData should return user data."""
        bot_token = "123456:ABC-DEF"
        user = {"id": 12345, "first_name": "Test", "username": "testuser"}
        init_data = self._make_init_data(user, bot_token)

        result = _validate_init_data(init_data, bot_token)
        assert result is not None
        assert result["id"] == 12345
        assert result["first_name"] == "Test"

    def test_invalid_hash(self):
        """Tampered initData should return None."""
        bot_token = "123456:ABC-DEF"
        user = {"id": 12345, "first_name": "Test"}
        init_data = self._make_init_data(user, bot_token)
        # Tamper with the hash
        init_data = init_data.replace(init_data[-10:], "0000000000")

        result = _validate_init_data(init_data, bot_token)
        assert result is None

    def test_wrong_bot_token(self):
        """Wrong bot token should fail validation."""
        user = {"id": 12345, "first_name": "Test"}
        init_data = self._make_init_data(user, "correct_token")

        result = _validate_init_data(init_data, "wrong_token")
        assert result is None

    def test_expired_auth_date(self):
        """Expired auth_date should return None."""
        bot_token = "123456:ABC-DEF"
        user_json = json.dumps({"id": 1, "first_name": "X"}, separators=(',', ':'))
        auth_date = str(int(time.time()) - 90000)  # > 24h ago

        params = {"user": user_json, "auth_date": auth_date}
        items = sorted(f"{k}={v}" for k, v in params.items())
        data_check_string = "\n".join(items)
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        hash_value = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        init_data = f"user={user_json}&auth_date={auth_date}&hash={hash_value}"
        result = _validate_init_data(init_data, bot_token)
        assert result is None

    def test_missing_hash(self):
        """Missing hash should return None."""
        result = _validate_init_data("user={}&auth_date=123", "token")
        assert result is None

    def test_empty_string(self):
        """Empty string should return None."""
        result = _validate_init_data("", "token")
        assert result is None

    def test_valid_init_data_with_extra_max_fields(self):
        """Validation should allow MAX-style launch params beyond user/auth_date."""
        bot_token = "123456:ABC-DEF"
        user_json = json.dumps({"id": 67890, "first_name": "Max", "username": "maxuser"}, separators=(',', ':'))
        auth_date = str(int(time.time()))
        chat_json = json.dumps({"id": 12345, "type": "DIALOG"}, separators=(',', ':'))

        params = {
            "auth_date": auth_date,
            "chat": chat_json,
            "query_id": "test-query-id",
            "user": user_json,
        }

        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        hash_value = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        init_data = "&".join([*(f"{k}={v}" for k, v in params.items()), f"hash={hash_value}"])
        result = _validate_init_data(init_data, bot_token)

        assert result is not None
        assert result["id"] == 67890
        assert result["first_name"] == "Max"

    def test_valid_init_data_inside_max_hash_fragment(self):
        """Validation should extract signed payload from MAX hash fragment."""
        bot_token = "123456:ABC-DEF"
        user = {"id": 24680, "first_name": "Hash", "username": "hashuser"}
        init_data = self._make_init_data(user, bot_token)
        fragment = f"#WebAppData={quote(init_data, safe='')}&WebAppVersion=8.0&WebAppPlatform=android"

        result = _validate_init_data(fragment, bot_token)

        assert result is not None
        assert result["id"] == 24680
        assert result["username"] == "hashuser"

    def test_valid_init_data_inside_full_url_fragment(self):
        """Validation should extract signed payload from a full Mini App URL."""
        bot_token = "123456:ABC-DEF"
        user = {"id": 13579, "first_name": "Url", "username": "urluser"}
        init_data = self._make_init_data(user, bot_token)
        full_url = f"https://4-2.xn--p1ai/app#WebAppData={quote(init_data, safe='')}&WebAppVersion=8.0"

        result = _validate_init_data(full_url, bot_token)

        assert result is not None
        assert result["id"] == 13579
        assert result["first_name"] == "Url"


class TestMoneyFormatting:
    """Test frontend money formatting logic (mirrors JS)."""

    def test_money_format(self):
        """Verify money formatting matches expected output."""
        # This tests the Python money formatting used in messages
        from app.bot.ui import money
        assert money(0) == "0₽"
        assert money(1500) == "1 500₽"
        assert money(12500) == "12 500₽"
        assert money(100) == "100₽"
