"""Signed Mini App session tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from app.config import get_settings

TOKEN_VERSION = 1


@dataclass(slots=True)
class SessionClaims:
    user_id: int
    external_user_id: int
    platform: str
    issued_at: int
    expires_at: int


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def _resolve_secret(secret_key: str | None = None) -> bytes:
    settings = get_settings()
    return (secret_key or settings.app_secret_key).encode("utf-8")


def create_session_token(
    *,
    user_id: int,
    external_user_id: int,
    platform: str,
    secret_key: str | None = None,
    ttl_sec: int | None = None,
) -> tuple[str, int]:
    settings = get_settings()
    now = int(time.time())
    expires_at = now + (ttl_sec or settings.webapp_session_ttl_sec)
    payload = {
        "v": TOKEN_VERSION,
        "uid": user_id,
        "ext": external_user_id,
        "platform": platform,
        "iat": now,
        "exp": expires_at,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(_resolve_secret(secret_key), payload_bytes, hashlib.sha256).digest()
    token = f"{_b64url_encode(payload_bytes)}.{_b64url_encode(signature)}"
    return token, expires_at


def verify_session_token(
    token: str,
    *,
    secret_key: str | None = None,
    now_ts: int | None = None,
) -> SessionClaims | None:
    if not token or "." not in token:
        return None

    payload_part, signature_part = token.split(".", 1)
    try:
        payload_bytes = _b64url_decode(payload_part)
        signature = _b64url_decode(signature_part)
        payload = json.loads(payload_bytes)
    except (ValueError, TypeError, json.JSONDecodeError):
        return None

    expected_signature = hmac.new(_resolve_secret(secret_key), payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected_signature):
        return None

    if payload.get("v") != TOKEN_VERSION:
        return None

    current_ts = int(time.time()) if now_ts is None else now_ts
    expires_at = int(payload.get("exp", 0))
    if expires_at <= current_ts:
        return None

    try:
        return SessionClaims(
            user_id=int(payload["uid"]),
            external_user_id=int(payload["ext"]),
            platform=str(payload["platform"]),
            issued_at=int(payload["iat"]),
            expires_at=expires_at,
        )
    except (KeyError, TypeError, ValueError):
        return None
