"""Health and readiness endpoints."""

from fastapi import APIRouter
from redis.asyncio import from_url
from sqlalchemy import text

from app.config import get_settings
from app.database import get_async_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "pridel"}


@router.get("/ready")
async def readiness() -> dict:
    """Check database and Redis connectivity."""
    checks = {}

    # DB check
    try:
        async with get_async_session()() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # Redis check
    try:
        r = from_url(get_settings().redis_url)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "ok" if all_ok else "degraded", "checks": checks}
