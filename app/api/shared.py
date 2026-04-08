"""Shared API dependencies and helpers."""

from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.config import get_settings
from app.models.user import User
from app.services.auth import get_user_by_id, get_user_by_telegram_id
from app.services.session_auth import verify_session_token


async def get_current_user(
    user_id: int | None = Query(default=None),
    x_telegram_id: int | None = Query(default=None, alias="tg_id"),
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Resolve current user by signed session token or dev-only query parameter."""
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(401, "Invalid authorization header")

        claims = verify_session_token(token)
        if not claims:
            raise HTTPException(401, "Invalid or expired session")

        user = await get_user_by_id(session, claims.user_id)
        if not user or not user.is_active or user.telegram_id != claims.external_user_id:
            raise HTTPException(401, "User not found or inactive")
        return user

    settings = get_settings()
    external_user_id = user_id if user_id is not None else x_telegram_id
    if external_user_id is None:
        raise HTTPException(401, "Authorization required")
    if not settings.is_dev:
        raise HTTPException(401, "Signed session required")

    user = await get_user_by_telegram_id(session, external_user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "User not found or inactive")
    return user
