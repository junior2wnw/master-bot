"""Signed web app launch data validation for supported messengers."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs, unquote, urlsplit

SIGNED_PAYLOAD_KEYS = ("WebAppData", "tgWebAppData", "init_data", "initData")


def normalize_webapp_init_data(raw_value: str) -> str:
    """Extract signed Mini App payload from raw init data, hash fragments, or full URLs."""
    if not raw_value:
        return ""

    candidate = raw_value.strip()
    if not candidate:
        return ""

    if "://" in candidate:
        parsed_url = urlsplit(candidate)
        for container in (parsed_url.fragment, parsed_url.query):
            extracted = _extract_signed_payload(container)
            if extracted:
                return extracted
        candidate = parsed_url.fragment or parsed_url.query or candidate

    if candidate.startswith("#"):
        candidate = candidate[1:]

    return _extract_signed_payload(candidate) or candidate


def _extract_signed_payload(container: str) -> str | None:
    if not container:
        return None

    parsed = parse_qs(container, keep_blank_values=True)
    for key in SIGNED_PAYLOAD_KEYS:
        value = parsed.get(key, [None])[0]
        if value:
            return value
    return None


def validate_webapp_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_sec: int = 86400,
) -> dict | None:
    """Validate signed init data and return the parsed user object."""
    if not init_data or not bot_token:
        return None

    try:
        normalized_init_data = normalize_webapp_init_data(init_data)
        parsed = parse_qs(normalized_init_data, keep_blank_values=True)
        check_hash = parsed.get("hash", [None])[0]
        if not check_hash:
            return None

        items: list[str] = []
        for key in sorted(parsed.keys()):
            if key == "hash":
                continue
            values = parsed.get(key) or []
            if len(values) != 1:
                return None
            items.append(f"{key}={values[0]}")
        data_check_string = "\n".join(items)

        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed, check_hash):
            return None

        auth_date = int(parsed.get("auth_date", ["0"])[0])
        if auth_date <= 0 or time.time() - auth_date > max_age_sec:
            return None

        user_str = parsed.get("user", [None])[0]
        if not user_str:
            return None
        return json.loads(unquote(user_str))
    except Exception:
        return None
