"""Client-facing handlers: catalog browsing, search, popular items, voice."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, messages
from app.bot.ui import paginate
from app.models.catalog import ServiceItem
from app.services import catalog as catalog_svc

router = Router()

PER_PAGE = 8


# ═══════════════════════════════════════════════════════════════
# CATALOG NAVIGATION: Professions → Groups → Subgroups → Items
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "catalog")
async def cb_catalog(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show professions with item counts."""
    professions = await catalog_svc.get_professions_with_counts(session)
    await callback.message.edit_text(
        messages.catalog_header(),
        reply_markup=keyboards.professions_list(professions),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("prof:"))
async def cb_profession(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show groups within a profession."""
    profession_id = int(callback.data.split(":")[1])
    groups = await catalog_svc.get_groups_with_counts(session, profession_id)

    # Get profession name for header
    profs = await catalog_svc.get_professions(session)
    prof = next((p for p in profs if p.id == profession_id), None)
    prof_name = prof.name if prof else "Каталог"

    await callback.message.edit_text(
        messages.group_header(prof_name),
        reply_markup=keyboards.groups_list(groups, profession_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("grp:"))
async def cb_group(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show subgroups or items if no subgroups exist."""
    group_id = int(callback.data.split(":")[1])
    subgroups = await catalog_svc.get_subgroups_with_counts(session, group_id)

    if subgroups:
        # Has subgroups — show them
        groups = await catalog_svc.get_groups(session, profession_id=0)  # we need the group name
        from sqlalchemy import select as sel
        from app.models.catalog import ServiceGroup
        grp_result = await session.execute(sel(ServiceGroup).where(ServiceGroup.id == group_id))
        grp = grp_result.scalar_one_or_none()
        grp_name = grp.name if grp else "Группа"

        # Fix back button to correct profession
        kb_markup = keyboards.subgroups_list(subgroups, group_id)
        # Override back button with correct profession_id
        if grp:
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            from aiogram.types import InlineKeyboardButton
            kb = InlineKeyboardBuilder()
            for s in subgroups:
                count = f" ({s['count']})" if s.get("count") else ""
                kb.row(InlineKeyboardButton(
                    text=f"{s['name']}{count}",
                    callback_data=f"sub:{s['id']}",
                ))
            kb.row(InlineKeyboardButton(text="📋 Все работы группы", callback_data=f"grp_items:{group_id}:1"))
            kb.row(InlineKeyboardButton(text=f"← Группы", callback_data=f"prof:{grp.profession_id}"))
            kb_markup = kb.as_markup()

        await callback.message.edit_text(
            messages.subgroup_header(grp_name),
            reply_markup=kb_markup,
        )
    else:
        # No subgroups — show items directly
        await _show_group_items(callback, session, group_id, page=1)

    await callback.answer()


@router.callback_query(F.data.regexp(r"^grp_items:(\d+):(\d+)$"))
async def cb_group_items_page(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show paginated items for a group."""
    parts = callback.data.split(":")
    group_id, page = int(parts[1]), int(parts[2])
    await _show_group_items(callback, session, group_id, page)
    await callback.answer()


@router.callback_query(F.data.startswith("sub:"))
async def cb_subgroup(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show items in a subgroup."""
    subgroup_id = int(callback.data.split(":")[1])
    items = await catalog_svc.get_items_by_subgroup(session, subgroup_id)
    all_items = [
        {"id": it.id, "name": it.name, "price": it.price_recommended}
        for it in items
    ]
    page_items, total_pages, current = paginate(all_items, 1, PER_PAGE)

    # Get subgroup info for back navigation
    from app.models.catalog import ServiceSubgroup
    sub_result = await session.execute(select(ServiceSubgroup).where(ServiceSubgroup.id == subgroup_id))
    sub = sub_result.scalar_one_or_none()
    back_cb = f"grp:{sub.group_id}" if sub else "catalog"

    count = len(all_items)
    await callback.message.edit_text(
        messages.items_header(sub.name if sub else "Работы", count),
        reply_markup=keyboards.items_list(
            page_items, back_cb, current, total_pages,
            page_prefix=f"sub_items:{subgroup_id}",
        ),
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^sub_items:(\d+):(\d+)$"))
async def cb_subgroup_items_page(callback: CallbackQuery, session: AsyncSession) -> None:
    """Paginate subgroup items."""
    parts = callback.data.split(":")
    subgroup_id, page = int(parts[1]), int(parts[2])
    items = await catalog_svc.get_items_by_subgroup(session, subgroup_id)
    all_items = [{"id": it.id, "name": it.name, "price": it.price_recommended} for it in items]
    page_items, total_pages, current = paginate(all_items, page, PER_PAGE)

    from app.models.catalog import ServiceSubgroup
    sub_result = await session.execute(select(ServiceSubgroup).where(ServiceSubgroup.id == subgroup_id))
    sub = sub_result.scalar_one_or_none()
    back_cb = f"grp:{sub.group_id}" if sub else "catalog"

    await callback.message.edit_text(
        messages.items_header(sub.name if sub else "Работы", len(all_items)),
        reply_markup=keyboards.items_list(
            page_items, back_cb, current, total_pages,
            page_prefix=f"sub_items:{subgroup_id}",
        ),
    )
    await callback.answer()


# ═══════════════════════════════════════════════════════════════
# ITEM DETAIL
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("item:"))
async def cb_item_detail(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show item details with price range and add-to-estimate button."""
    item_id = int(callback.data.split(":")[1])
    result = await session.execute(select(ServiceItem).where(ServiceItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        await callback.answer("Работа не найдена", show_alert=True)
        return

    data = {
        "name": item.name,
        "code": item.code,
        "unit": item.unit,
        "price_min": item.price_min,
        "price_max": item.price_max,
        "price_recommended": item.price_recommended,
        "complexity": item.complexity,
        "note": item.note,
        "aliases": item.aliases,
    }

    # Determine back callback from item's group
    back_cb = f"grp:{item.group_id}" if item.group_id else "catalog"

    await callback.message.edit_text(
        messages.item_detail(data),
        reply_markup=keyboards.item_detail(item.id, back_cb=back_cb),
    )
    await callback.answer()


# ═══════════════════════════════════════════════════════════════
# POPULAR ITEMS
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "popular")
async def cb_popular(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show popular items across all professions."""
    items = await catalog_svc.get_popular_items(session, limit=20)
    all_items = [{"id": it.id, "name": it.name, "price": it.price_recommended} for it in items]
    page_items, total_pages, current = paginate(all_items, 1, PER_PAGE)

    await callback.message.edit_text(
        messages.popular_items_header(),
        reply_markup=keyboards.items_list(
            page_items, "catalog", current, total_pages, page_prefix="popular_page",
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("popular_page:"))
async def cb_popular_page(callback: CallbackQuery, session: AsyncSession) -> None:
    page = int(callback.data.split(":")[1])
    items = await catalog_svc.get_popular_items(session, limit=20)
    all_items = [{"id": it.id, "name": it.name, "price": it.price_recommended} for it in items]
    page_items, total_pages, current = paginate(all_items, page, PER_PAGE)

    await callback.message.edit_text(
        messages.popular_items_header(),
        reply_markup=keyboards.items_list(
            page_items, "catalog", current, total_pages, page_prefix="popular_page",
        ),
    )
    await callback.answer()


# ═══════════════════════════════════════════════════════════════
# SEARCH
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "search")
async def cb_search_prompt(callback: CallbackQuery, session: AsyncSession) -> None:
    """Prompt user to enter search query."""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Меню", callback_data="main_menu"))

    await callback.message.edit_text(
        messages.search_prompt(),
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.message(F.text & ~F.text.startswith("/"))
async def msg_search(message: Message, session: AsyncSession, state: FSMContext) -> None:
    """Handle free text as search queries (only when no FSM state is active)."""
    current_state = await state.get_state()
    if current_state is not None:
        return

    query = message.text.strip()
    if len(query) < 2:
        return

    items = await catalog_svc.search_items(session, query, limit=20)
    if not items:
        # Try simple fallback
        items = await catalog_svc.search_items_simple(session, query, limit=20)

    if not items:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        kb = InlineKeyboardBuilder()
        kb.row(
            InlineKeyboardButton(text="📋 Каталог", callback_data="catalog"),
            InlineKeyboardButton(text="← Меню", callback_data="main_menu"),
        )
        await message.answer(
            messages.search_results([], query),
            reply_markup=kb.as_markup(),
        )
        return

    all_items = [
        {"id": it.id, "name": it.name, "price": it.price_recommended}
        for it in items
    ]
    page_items, total_pages, current = paginate(all_items, 1, PER_PAGE)

    await message.answer(
        messages.search_results(
            [{"name": it.name, "price_recommended": it.price_recommended} for it in items],
            query,
            total=len(items),
        ),
        reply_markup=keyboards.search_results(page_items, query, current, total_pages),
    )


# ═══════════════════════════════════════════════════════════════
# VOICE
# ═══════════════════════════════════════════════════════════════

@router.message(F.voice)
async def msg_voice(message: Message, session: AsyncSession) -> None:
    """Handle voice messages — transcribe and parse with AI."""
    from app.core.module_registry import is_enabled
    if not is_enabled("module.ai_intake", default=False):
        await message.answer(messages.voice_disabled())
        return

    processing_msg = await message.answer(messages.voice_processing())

    try:
        from app.services.ai_intake import process_voice

        # Download voice file
        file = await message.bot.get_file(message.voice.file_id)
        audio_bytes = await message.bot.download_file(file.file_path)
        audio_data = audio_bytes.read() if hasattr(audio_bytes, 'read') else audio_bytes

        # Process with AI
        result = await process_voice(session, audio_data, message.voice.mime_type or "audio/ogg")

        if result.confidence == 0 or not result.detected_items:
            text = "🎤 <b>Распознанный текст:</b>\n"
            text += f"<i>{result.raw_text or 'не распознано'}</i>\n\n"
            if result.summary:
                text += f"{result.summary}\n\n"
            text += "💡 Попробуйте описать задачу подробнее или используйте каталог."

            from aiogram.utils.keyboard import InlineKeyboardBuilder
            from aiogram.types import InlineKeyboardButton
            kb = InlineKeyboardBuilder()
            kb.row(
                InlineKeyboardButton(text="📋 Каталог", callback_data="catalog"),
                InlineKeyboardButton(text="🔍 Поиск", callback_data="search"),
            )
            await processing_msg.edit_text(text, reply_markup=kb.as_markup())
            return

        # Build response with detected items
        text = f"🎤 <b>Распознано:</b> <i>{result.raw_text}</i>\n\n"
        if result.summary:
            text += f"📋 {result.summary}\n\n"

        text += "<b>Предложенные работы:</b>\n"
        for i, item in enumerate(result.detected_items, 1):
            text += f"  {i}. {item.get('name', '?')} × {item.get('qty', 1)}\n"

        if result.unresolved_questions:
            text += "\n❓ <b>Уточните:</b>\n"
            for q in result.unresolved_questions:
                text += f"  • {q}\n"

        if result.risk_flags:
            text += "\n⚠️ <b>Обратите внимание:</b>\n"
            for r in result.risk_flags:
                text += f"  • {r}\n"

        text += f"\n🎯 Уверенность: {int(result.confidence * 100)}%"

        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        kb = InlineKeyboardBuilder()
        kb.row(
            InlineKeyboardButton(text="📋 Каталог", callback_data="catalog"),
            InlineKeyboardButton(text="← Меню", callback_data="main_menu"),
        )
        await processing_msg.edit_text(text, reply_markup=kb.as_markup())

    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Voice processing error: %s", e)
        await processing_msg.edit_text(
            "⚠️ Ошибка обработки голосового сообщения.\n"
            "Попробуйте описать задачу текстом."
        )


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

async def _show_group_items(
    callback: CallbackQuery, session: AsyncSession, group_id: int, page: int,
) -> None:
    """Show paginated items for a group."""
    items = await catalog_svc.get_items_by_group(session, group_id)
    all_items = [
        {"id": it.id, "name": it.name, "price": it.price_recommended}
        for it in items
    ]
    page_items, total_pages, current = paginate(all_items, page, PER_PAGE)

    # Get group info
    from app.models.catalog import ServiceGroup
    grp_result = await session.execute(select(ServiceGroup).where(ServiceGroup.id == group_id))
    grp = grp_result.scalar_one_or_none()
    back_cb = f"prof:{grp.profession_id}" if grp else "catalog"
    grp_name = grp.name if grp else "Работы"

    await callback.message.edit_text(
        messages.items_header(grp_name, len(all_items)),
        reply_markup=keyboards.items_list(
            page_items, back_cb, current, total_pages,
            page_prefix=f"grp_items:{group_id}",
        ),
    )
