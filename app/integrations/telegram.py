"""Telegram-specific adapter for notification delivery."""

import logging

from aiogram import Bot

logger = logging.getLogger(__name__)


async def send_notification(bot: Bot, telegram_id: int, text: str) -> bool:
    """Send a text message to a Telegram user. Returns True on success."""
    try:
        await bot.send_message(chat_id=telegram_id, text=text, parse_mode="HTML")
        return True
    except Exception as e:
        logger.error("Failed to send TG message to %s: %s", telegram_id, e)
        return False


async def send_notification_with_keyboard(
    bot: Bot, telegram_id: int, text: str, keyboard
) -> bool:
    """Send message with inline keyboard."""
    try:
        await bot.send_message(
            chat_id=telegram_id, text=text, parse_mode="HTML", reply_markup=keyboard
        )
        return True
    except Exception as e:
        logger.error("Failed to send TG message to %s: %s", telegram_id, e)
        return False
