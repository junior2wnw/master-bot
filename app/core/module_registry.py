"""Module registry and feature flag checks.

Provides a simple way to check if a module/feature is enabled.
Flags are loaded from DB on startup and cached. Admin can toggle via API.
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# In-memory cache of feature flags: code -> is_enabled
_flags: dict[str, bool] = {}

# In-memory cache of system settings: key -> value
_settings: dict[str, Any] = {}


async def load_flags(session: AsyncSession) -> None:
    """Load all feature flags from DB into memory."""
    from app.models.feature_flag import FeatureFlag
    result = await session.execute(select(FeatureFlag))
    flags = result.scalars().all()
    _flags.clear()
    for f in flags:
        _flags[f.code] = f.is_enabled
    logger.info("Loaded %d feature flags", len(_flags))


async def load_settings(session: AsyncSession) -> None:
    """Load system settings from DB into memory."""
    from app.models.feature_flag import SystemSetting
    result = await session.execute(select(SystemSetting))
    settings = result.scalars().all()
    _settings.clear()
    for s in settings:
        _settings[s.key] = s.value
    logger.info("Loaded %d system settings", len(_settings))


def is_enabled(flag_code: str, default: bool = True) -> bool:
    """Check if a feature flag is enabled."""
    return _flags.get(flag_code, default)


def get_setting(key: str, default: Any = None) -> Any:
    """Get a system setting value."""
    return _settings.get(key, default)


async def set_flag(session: AsyncSession, code: str, enabled: bool, user_id: int) -> None:
    """Toggle a feature flag and update cache."""
    from app.models.feature_flag import FeatureFlag
    result = await session.execute(select(FeatureFlag).where(FeatureFlag.code == code))
    flag = result.scalar_one_or_none()
    if flag:
        flag.is_enabled = enabled
        flag.updated_by = user_id
        _flags[code] = enabled


async def set_setting(session: AsyncSession, key: str, value: Any, user_id: int) -> None:
    """Update a system setting and refresh cache."""
    from app.models.feature_flag import SystemSetting
    result = await session.execute(select(SystemSetting).where(SystemSetting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
        setting.updated_by = user_id
        _settings[key] = value


# Default feature flags to seed
DEFAULT_FLAGS = [
    ("module.ai_intake", "AI-парсинг заявок", "ai", False),
    ("module.orders", "Публичные заявки от клиентов", "orders", False),
    ("module.payments", "Платежи и QR", "payments", True),
    ("module.discounts", "Скидки и согласование", "discounts", True),
    ("module.invites", "Инвайт-система", "invites", True),
    ("module.notifications", "Уведомления", "notifications", True),
    ("module.analytics", "Аналитика", "analytics", True),
    ("registration.masters", "Регистрация новых мастеров", "invites", True),
    ("registration.clients", "Регистрация клиентов", "auth", True),
]
