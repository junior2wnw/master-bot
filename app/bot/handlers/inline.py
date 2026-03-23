"""Inline query handler: instant search via @bot_name query."""

import hashlib

from aiogram import Router
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.middleware import DatabaseMiddleware
from app.bot.ui import money
from app.services import catalog as catalog_svc

router = Router()


@router.inline_query()
async def inline_search(query: InlineQuery, session: AsyncSession) -> None:
    """Handle inline queries: @bot розетка → instant results."""
    text = query.query.strip()

    if len(text) < 2:
        # Show help when query is too short
        await query.answer(
            results=[
                InlineQueryResultArticle(
                    id="help",
                    title="🔍 Поиск работ",
                    description="Введите минимум 2 символа для поиска",
                    input_message_content=InputTextMessageContent(
                        message_text="📋 <b>Каталог работ МастерБот</b>\n\n"
                        "Используйте @бот + запрос для быстрого поиска.",
                        parse_mode="HTML",
                    ),
                )
            ],
            cache_time=60,
            is_personal=True,
        )
        return

    # Search items
    items = await catalog_svc.search_items(session, text, limit=20)
    if not items:
        items = await catalog_svc.search_items_simple(session, text, limit=20)

    results = []
    for item in items[:20]:
        # Unique ID for each result
        result_id = hashlib.md5(f"{item.id}:{text}".encode()).hexdigest()

        price_text = f"{item.price_recommended:,}₽" if item.price_recommended else "по запросу"
        price_range = ""
        if item.price_min and item.price_max:
            price_range = f"\nДиапазон: {item.price_min:,}–{item.price_max:,}₽"

        description = f"{price_text} · {item.unit}"
        if item.complexity:
            complexity_map = {"basic": "простая", "std": "стандарт", "complex": "сложная", "hard": "тяжёлая"}
            description += f" · {complexity_map.get(item.complexity, '')}"

        message_text = (
            f"🔧 <b>{item.name}</b>\n\n"
            f"Код: <code>{item.code}</code>\n"
            f"Цена: <b>{price_text}</b>{price_range}\n"
            f"Ед.: {item.unit}\n"
        )
        if item.note:
            message_text += f"\n📝 {item.note}"

        # Add keyboard with link to bot
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Открыть в боте", url=f"https://t.me/{(await query.bot.me()).username}")]
        ])

        results.append(
            InlineQueryResultArticle(
                id=result_id,
                title=f"🔧 {item.name}",
                description=description,
                input_message_content=InputTextMessageContent(
                    message_text=message_text,
                    parse_mode="HTML",
                ),
                reply_markup=kb,
            )
        )

    if not results:
        results.append(
            InlineQueryResultArticle(
                id="not_found",
                title=f"🔍 «{text}» — ничего не найдено",
                description="Попробуйте другие слова",
                input_message_content=InputTextMessageContent(
                    message_text=f"🔍 По запросу «{text}» ничего не найдено.",
                ),
            )
        )

    await query.answer(
        results=results,
        cache_time=30,
        is_personal=True,
    )
