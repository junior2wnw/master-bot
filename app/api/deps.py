"""FastAPI dependencies."""

from collections.abc import AsyncGenerator

from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session():
        yield session


async def verify_admin_token(x_admin_token: str = Header(...)) -> None:
    """Simple token-based auth for admin API.

    In production, replace with proper JWT or session auth.
    """
    settings = get_settings()
    if x_admin_token != settings.app_secret_key:
        raise HTTPException(status_code=403, detail="Invalid admin token")
