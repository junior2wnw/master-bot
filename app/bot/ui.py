"""UI framework: pagination, formatting, navigation helpers.

Modern Telegram bot UX building blocks — compact, visual, consistent.
"""

from math import ceil

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ─── Pagination ───────────────────────────────────────────────

def paginate(
    items: list,
    page: int = 1,
    per_page: int = 8,
) -> tuple[list, int, int]:
    """Return (page_items, total_pages, current_page)."""
    total = ceil(len(items) / per_page) if items else 1
    page = max(1, min(page, total))
    start = (page - 1) * per_page
    return items[start:start + per_page], total, page


def add_pagination_row(
    kb: InlineKeyboardBuilder,
    current_page: int,
    total_pages: int,
    callback_prefix: str,
) -> None:
    """Add ◀ 1/3 ▶ navigation row to keyboard."""
    if total_pages <= 1:
        return
    buttons = []
    if current_page > 1:
        buttons.append(InlineKeyboardButton(
            text="◀", callback_data=f"{callback_prefix}:{current_page - 1}",
        ))
    buttons.append(InlineKeyboardButton(
        text=f"·{current_page}/{total_pages}·", callback_data="noop",
    ))
    if current_page < total_pages:
        buttons.append(InlineKeyboardButton(
            text="▶", callback_data=f"{callback_prefix}:{current_page + 1}",
        ))
    kb.row(*buttons)


# ─── Navigation ───────────────────────────────────────────────

def back_button(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=f"← {text}", callback_data=callback_data)


def add_back_row(kb: InlineKeyboardBuilder, text: str, callback_data: str) -> None:
    kb.row(back_button(text, callback_data))


# ─── Formatting ───────────────────────────────────────────────

THIN_LINE = "─" * 26
BLOCK_LINE = "━" * 26


def header(icon: str, title: str, subtitle: str = "") -> str:
    sub = f"\n<i>{subtitle}</i>" if subtitle else ""
    return f"{icon} <b>{title}</b>{sub}"


def stat_line(label: str, value, icon: str = "") -> str:
    prefix = f"{icon} " if icon else "  "
    return f"{prefix}{label}: <b>{value}</b>"


def stat_block(stats: list[tuple[str, str, str]]) -> str:
    """Build stat block: [(icon, label, value), ...]."""
    return "\n".join(f"{icon} {label}  <b>{val}</b>" for icon, label, val in stats)


def money(amount: int | float) -> str:
    """Format money: 12500 → '12 500₽'."""
    return f"{int(amount):,}₽".replace(",", " ")


def badge(status: str, mapping: dict[str, str]) -> str:
    """Get emoji badge for status."""
    return mapping.get(status, "○")


# ─── Common Status Maps ──────────────────────────────────────

ESTIMATE_STATUS = {
    "draft": "📝", "estimated": "📊", "master_proposed": "📤",
    "client_review": "👁", "approved": "✅", "in_progress": "🔨",
    "completed": "☑️", "paid": "💰", "disputed": "⚠️", "cancelled": "❌",
}

ESTIMATE_STATUS_RU = {
    "draft": "Черновик", "estimated": "Рассчитана", "master_proposed": "Предложена",
    "client_review": "На проверке", "approved": "Согласована", "in_progress": "В работе",
    "completed": "Завершена", "paid": "Оплачена", "disputed": "Спор", "cancelled": "Отменена",
}

ORDER_STATUS = {
    "draft": "📝", "submitted": "📤", "assigned": "👷",
    "in_progress": "🔨", "completed": "✅", "paid": "💰",
    "cancelled": "❌", "disputed": "⚠️",
}

ORDER_STATUS_RU = {
    "draft": "Черновик", "submitted": "Отправлен", "assigned": "Назначен",
    "in_progress": "В работе", "completed": "Завершён", "paid": "Оплачен",
    "cancelled": "Отменён", "disputed": "Спор",
}

URGENCY_RU = {"normal": "Обычная", "urgent": "Срочно", "emergency": "Экстренно"}


# ─── Grid layout ──────────────────────────────────────────────

def grid_buttons(
    buttons: list[InlineKeyboardButton],
    kb: InlineKeyboardBuilder,
    columns: int = 2,
) -> None:
    """Add buttons in a grid layout."""
    for i in range(0, len(buttons), columns):
        kb.row(*buttons[i:i + columns])
