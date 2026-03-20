"""Notification dispatcher: delivers pending notifications via Telegram.

Runs as a background task during bot polling. Picks up pending notifications
from the DB, delivers them via the appropriate channel, marks them sent/failed.

Integrates with the event bus to deliver notifications in near real-time
when they are created, with a periodic sweep for retries.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.models.notification import Notification
from app.models.user import User

logger = logging.getLogger(__name__)

# Will be set by bot startup
_bot_instance = None


def set_bot(bot) -> None:
    """Set the bot instance for notification delivery. Called once at startup."""
    global _bot_instance
    _bot_instance = bot


async def deliver_notification(session: AsyncSession, notification: Notification) -> bool:
    """Deliver a single notification via its channel."""
    if _bot_instance is None:
        logger.warning("Bot not initialized, cannot deliver notification %d", notification.id)
        return False

    if notification.channel != "telegram":
        logger.warning("Unsupported channel '%s' for notification %d", notification.channel, notification.id)
        return False

    # Get user's telegram_id
    result = await session.execute(select(User).where(User.id == notification.user_id))
    user = result.scalar_one_or_none()
    if not user:
        logger.error("User %d not found for notification %d", notification.user_id, notification.id)
        return False

    # Build message
    text = f"<b>{notification.title}</b>\n\n{notification.body}"

    try:
        await _bot_instance.send_message(
            chat_id=user.telegram_id,
            text=text,
            parse_mode="HTML",
        )
        notification.status = "sent"
        notification.sent_at = datetime.now(timezone.utc)
        await session.flush()
        logger.info("Notification %d delivered to user %d (tg=%d)", notification.id, user.id, user.telegram_id)
        return True
    except Exception as e:
        notification.status = "failed"
        notification.retry_count += 1
        await session.flush()
        logger.error("Failed to deliver notification %d: %s", notification.id, e)
        return False


async def dispatch_pending(batch_size: int = 20) -> int:
    """Dispatch all pending notifications. Returns count of successfully sent."""
    session_factory = get_async_session()
    sent = 0

    async with session_factory() as session:
        result = await session.execute(
            select(Notification)
            .where(
                Notification.status.in_(["pending", "failed"]),
                Notification.retry_count < 3,
            )
            .order_by(Notification.created_at)
            .limit(batch_size)
        )
        notifications = result.scalars().all()

        for n in notifications:
            if await deliver_notification(session, n):
                sent += 1
            # Small delay between sends to avoid rate limits
            await asyncio.sleep(0.05)

        await session.commit()

    return sent


async def notification_worker(interval: float = 10.0) -> None:
    """Background worker that periodically dispatches notifications.

    Runs as a long-lived asyncio task alongside the bot.
    """
    logger.info("Notification worker started (interval=%ss)", interval)
    while True:
        try:
            sent = await dispatch_pending()
            if sent:
                logger.info("Dispatched %d notifications", sent)
        except Exception as e:
            logger.error("Notification worker error: %s", e)
        await asyncio.sleep(interval)
