"""Tests for signed Mini App session auth."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.api.shared as shared_api
import app.services.session_auth as session_auth
from app.api.shared import get_current_user
from app.database import Base
from app.models.hierarchy import Branch, BranchMember
from app.models.user import User, UserRole
from app.services.session_auth import create_session_token, verify_session_token


async def _make_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    User.__table__,
                    UserRole.__table__,
                    Branch.__table__,
                    BranchMember.__table__,
                ],
            )
        )
    return engine, session_factory


def test_session_token_rejects_tampering_and_expiry():
    token, expires_at = create_session_token(
        user_id=7,
        external_user_id=7007,
        platform="max",
        secret_key="test-secret",
        ttl_sec=60,
    )

    claims = verify_session_token(token, secret_key="test-secret", now_ts=expires_at - 1)
    assert claims is not None
    assert claims.user_id == 7
    assert claims.external_user_id == 7007

    tampered = f"{token[:-1]}A"
    assert verify_session_token(tampered, secret_key="test-secret") is None
    assert verify_session_token(token, secret_key="test-secret", now_ts=expires_at + 1) is None


@pytest.mark.asyncio
async def test_get_current_user_requires_signed_session_in_production(monkeypatch):
    engine, session_factory = await _make_session_factory()
    monkeypatch.setattr(
        session_auth,
        "get_settings",
        lambda: SimpleNamespace(app_secret_key="test-secret", webapp_session_ttl_sec=3600),
    )
    monkeypatch.setattr(shared_api, "get_settings", lambda: SimpleNamespace(is_dev=False))

    async with session_factory() as session:
        user = User(telegram_id=71142489, first_name="Алик")
        session.add(user)
        await session.flush()
        session.add(UserRole(user_id=user.id, role_code="product_owner"))
        await session.flush()

        token, _ = create_session_token(
            user_id=user.id,
            external_user_id=user.telegram_id,
            platform="max",
            secret_key="test-secret",
            ttl_sec=3600,
        )

        resolved = await get_current_user(
            user_id=None,
            x_telegram_id=None,
            authorization=f"Bearer {token}",
            session=session,
        )
        assert resolved.id == user.id

        with pytest.raises(HTTPException) as exc:
            await get_current_user(
                user_id=user.telegram_id,
                x_telegram_id=None,
                authorization=None,
                session=session,
            )

        assert exc.value.status_code == 401
        assert exc.value.detail == "Signed session required"

    await engine.dispose()
