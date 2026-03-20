"""Client-facing bot handlers: catalog browsing, search, voice intake."""

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, messages
from app.services import catalog as catalog_svc
from app.services.auth import get_or_create_user

router = Router()


@router.callback_query(F.data == "catalog")
async def cb_catalog(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show list of professions."""
    professions = await catalog_svc.get_professions(session)
    data = [{"id": p.id, "name": p.name, "icon": p.icon or "🔧"} for p in professions]
    await callback.message.edit_text(
        "📋 <b>Каталог работ</b>\n\nВыберите направление:",
        reply_markup=keyboards.professions_list(data),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("prof:"))
async def cb_profession(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show groups within a profession."""
    profession_id = int(callback.data.split(":")[1])
    groups = await catalog_svc.get_groups(session, profession_id)
    data = [{"id": g.id, "name": g.name} for g in groups]
    await callback.message.edit_text(
        "📂 <b>Группы работ</b>\n\nВыберите категорию:",
        reply_markup=keyboards.groups_list(data, profession_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("grp:"))
async def cb_group(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show items in a group."""
    group_id = int(callback.data.split(":")[1])
    items = await catalog_svc.get_items_by_group(session, group_id)
    data = [
        {"id": it.id, "name": it.name, "price_recommended": it.price_recommended}
        for it in items[:20]
    ]
    await callback.message.edit_text(
        "📋 <b>Работы</b>\n\nВыберите для подробностей:",
        reply_markup=keyboards.items_list(data, f"prof:{items[0].profession_id}" if items else "catalog"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("item:"))
async def cb_item_detail(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show item details with price range."""
    item_id = int(callback.data.split(":")[1])
    from sqlalchemy import select
    from app.models.catalog import ServiceItem
    result = await session.execute(select(ServiceItem).where(ServiceItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        await callback.answer("Работа не найдена", show_alert=True)
        return

    text = (
        f"🔧 <b>{item.name}</b>\n\n"
        f"Код: {item.code}\n"
        f"Ед.: {item.unit}\n"
        f"Цена: {item.price_min}–{item.price_max}₽\n"
        f"Рекомендовано: <b>{item.price_recommended}₽</b>\n"
    )
    if item.note:
        text += f"\n📝 {item.note}"
    if item.aliases:
        text += f"\n🔍 Алиасы: {item.aliases}"

    await callback.message.edit_text(
        text,
        reply_markup=keyboards.item_actions(item.id),
    )
    await callback.answer()


@router.callback_query(F.data == "search")
async def cb_search_prompt(callback: CallbackQuery, session: AsyncSession) -> None:
    """Prompt user to enter search query."""
    await callback.message.edit_text(
        "🔍 <b>Поиск работ</b>\n\n"
        "Введите название работы, ключевое слово или хэштег.\n"
        "Например: <i>розетка</i>, <i>люстра</i>, <i>замена смесителя</i>",
    )
    await callback.answer()


@router.message(F.text & ~F.text.startswith("/"))
async def msg_search(message: Message, session: AsyncSession) -> None:
    """Handle text messages as search queries."""
    query = message.text.strip()
    if len(query) < 2:
        return

    items = await catalog_svc.search_items(session, query, limit=10)
    if not items:
        await message.answer(f"🔍 По запросу «{query}» ничего не найдено.\n\nПопробуйте другие слова.")
        return

    data = [
        {"id": it.id, "name": it.name, "price_recommended": it.price_recommended}
        for it in items
    ]
    await message.answer(
        messages.search_results(
            [{"name": it.name, "price_recommended": it.price_recommended} for it in items],
            query,
        ),
        reply_markup=keyboards.items_list(data, "search"),
    )


@router.message(F.voice)
async def msg_voice(message: Message, session: AsyncSession) -> None:
    """Handle voice messages — transcribe and parse with AI."""
    from app.core.module_registry import is_enabled
    if not is_enabled("module.ai_intake", default=False):
        await message.answer(
            "🎤 Голосовые заявки пока в разработке.\n"
            "Опишите задачу текстом или используйте каталог."
        )
        return

    await message.answer("🎤 Обрабатываю голосовое сообщение...")
    # AI processing would go here
