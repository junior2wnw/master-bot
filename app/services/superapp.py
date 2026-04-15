"""Mini App superapp services: board, network, workspace layouts."""

from __future__ import annotations

import re

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.exceptions import ConflictError, NotFoundError, PermissionDenied, ValidationError
from app.core.security import Permission, Role, has_permission, has_role
from app.models.master_profile import MasterProfile
from app.models.notification import Notification
from app.models.order import Order
from app.models.superapp import (
    JobPost,
    JobPostResponse,
    MasterReview,
    PublicMasterProfile,
    WorkspaceLayout,
)
from app.models.user import User, UserRole
from app.services.profile import get_profile_payload, profile_has_bank_details
from app.services.workspace import count_unread_notifications_for_user, get_dashboard_data

ACTIVE_JOB_RESPONSE_STATUSES = {"submitted", "shortlisted", "accepted"}
PROVIDER_ROLE_CODES = {"master", "senior_master"}
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
REVIEWABLE_ORDER_STATUSES = {"completed", "paid"}
MAX_LAYOUT_DEPTH = 5
MAX_LAYOUT_WINDOWS = 8
MAX_LAYOUT_CHILDREN = 4

PANEL_DEFINITIONS = (
    {
        "id": "board-feed",
        "title": "Доска",
        "subtitle": "Публикации и отклики по работам",
        "group": "market",
        "icon": "layers",
        "visibility": "all",
    },
    {
        "id": "network-directory",
        "title": "Мастера",
        "subtitle": "Публичные страницы и быстрый подбор",
        "group": "market",
        "icon": "users",
        "visibility": "all",
    },
    {
        "id": "workspace-overview",
        "title": "Рабочий стол",
        "subtitle": "Дела, фокус и быстрые действия",
        "group": "workspace",
        "icon": "spark",
        "visibility": "all",
    },
    {
        "id": "catalog-browser",
        "title": "Каталог",
        "subtitle": "Поиск услуг и быстрый старт сметы",
        "group": "workspace",
        "icon": "grid",
        "visibility": "all",
    },
    {
        "id": "estimates-list",
        "title": "Сметы",
        "subtitle": "Черновики, согласование и экспорт",
        "group": "workspace",
        "icon": "receipt",
        "visibility": "all",
    },
    {
        "id": "orders-list",
        "title": "Заказы",
        "subtitle": "Активная работа и история статусов",
        "group": "workspace",
        "icon": "briefcase",
        "visibility": "all",
    },
    {
        "id": "notifications-list",
        "title": "Уведомления",
        "subtitle": "Сигналы, требующие реакции",
        "group": "workspace",
        "icon": "bell",
        "visibility": "all",
    },
    {
        "id": "profile-card",
        "title": "Профиль",
        "subtitle": "Личные и платёжные данные",
        "group": "account",
        "icon": "id",
        "visibility": "all",
    },
    {
        "id": "control-center",
        "title": "Операции",
        "subtitle": "Команда, инвайты, модерация и флаги",
        "group": "control",
        "icon": "spark",
        "visibility": "ops",
    },
    {
        "id": "approvals-queue",
        "title": "Согласования",
        "subtitle": "Очередь скидок и решений по доступам",
        "group": "control",
        "icon": "check",
        "visibility": "approver",
    },
    {
        "id": "analytics-overview",
        "title": "Аналитика",
        "subtitle": "Платформа, воронка и финансовая картина",
        "group": "control",
        "icon": "chart",
        "visibility": "admin",
    },
)

PRESET_DEFINITIONS = (
    {
        "id": "market",
        "title": "Рынок",
        "subtitle": "Спрос сверху, мастера снизу",
        "default_ratio": 56,
        "top_panel": "board-feed",
        "bottom_panel": "network-directory",
        "visibility": "all",
    },
    {
        "id": "workbench",
        "title": "Работа",
        "subtitle": "Текущие задачи и выполнение",
        "default_ratio": 50,
        "top_panel": "workspace-overview",
        "bottom_panel": "orders-list",
        "visibility": "all",
    },
    {
        "id": "control",
        "title": "Контроль",
        "subtitle": "Управление, approvals и обзор платформы",
        "default_ratio": 48,
        "top_panel": "control-center",
        "bottom_panel": "approvals-queue",
        "visibility": "ops",
    },
)


def _can_publish_master_profile(user: User) -> bool:
    return has_permission(user, Permission.ESTIMATE_CREATE)


def _can_respond_to_board(user: User) -> bool:
    return has_permission(user, Permission.ESTIMATE_CREATE)


def _can_view_control(user: User) -> bool:
    return has_permission(user, Permission.ADMIN_PANEL) or has_role(user, Role.PRODUCT_OWNER)


def _can_create_estimate(user: User) -> bool:
    return has_permission(user, Permission.ESTIMATE_CREATE)


def _can_create_order(user: User) -> bool:
    return has_permission(user, Permission.ORDER_CREATE)


def _can_process_approvals(user: User) -> bool:
    return has_permission(user, Permission.DISCOUNT_APPROVE_BRANCH)


def _can_view_ops(user: User) -> bool:
    return any(
        (
            _can_view_control(user),
            has_permission(user, Permission.INVITE_CREATE),
            has_permission(user, Permission.INVITE_MODERATE),
            has_permission(user, Permission.STAFFING_INITIATE_BRANCH),
            has_permission(user, Permission.STAFFING_APPROVE),
            has_role(user, Role.SENIOR_MASTER),
        )
    )


def _panel_is_visible(user: User, visibility: str) -> bool:
    if visibility == "all":
        return True
    if visibility == "ops":
        return _can_view_ops(user)
    if visibility == "approver":
        return has_permission(user, Permission.DISCOUNT_APPROVE_BRANCH)
    if visibility == "admin":
        return _can_view_control(user)
    return False


def get_available_panels(user: User) -> list[dict]:
    return [
        {
            "id": panel["id"],
            "title": panel["title"],
            "subtitle": panel["subtitle"],
            "group": panel["group"],
            "icon": panel["icon"],
        }
        for panel in PANEL_DEFINITIONS
        if _panel_is_visible(user, panel["visibility"])
    ]


def get_available_presets(user: User) -> list[dict]:
    return [
        {
            "id": preset["id"],
            "title": preset["title"],
            "subtitle": preset["subtitle"],
        }
        for preset in PRESET_DEFINITIONS
        if _panel_is_visible(user, preset["visibility"])
    ]


def _default_layout_for_preset(user: User, preset_code: str | None) -> dict:
    available_presets = {item["id"] for item in get_available_presets(user)}
    selected = next(
        (
            preset
            for preset in PRESET_DEFINITIONS
            if preset["id"] == preset_code and preset["id"] in available_presets
        ),
        None,
    )
    if selected is None:
        selected = next(preset for preset in PRESET_DEFINITIONS if preset["id"] in available_presets)

    layout = {
        "version": 2,
        "preset": selected["id"],
        "ratio": float(selected["default_ratio"]),
        "panes": {
            "top": selected["top_panel"],
            "bottom": selected["bottom_panel"],
        },
        "chrome": {
            "density": "cozy",
            "dock_compact": False,
        },
    }
    layout["composer"] = _default_composer_from_layout(layout)
    return layout


def _normalize_layout_sizes(values: list[float] | None, count: int) -> list[float]:
    if count <= 0:
        return []
    if not isinstance(values, list) or len(values) != count:
        even = round(100 / count, 1)
        sizes = [even for _ in range(count)]
        sizes[-1] = round(100 - sum(sizes[:-1]), 1)
        return sizes

    cleaned: list[float] = []
    for value in values:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = 100 / count
        cleaned.append(max(12.0, numeric))

    total = sum(cleaned)
    if total <= 0:
        even = round(100 / count, 1)
        sizes = [even for _ in range(count)]
        sizes[-1] = round(100 - sum(sizes[:-1]), 1)
        return sizes

    normalized = [round((value / total) * 100, 1) for value in cleaned]
    normalized[-1] = round(normalized[-1] + (100 - sum(normalized)), 1)
    return normalized


def _default_composer_from_layout(layout: dict) -> dict:
    return {
        "root": {
            "id": "split-root",
            "kind": "split",
            "axis": "vertical",
            "children": [
                {
                    "id": "window-top",
                    "kind": "window",
                    "panel_id": layout["panes"]["top"],
                },
                {
                    "id": "window-bottom",
                    "kind": "window",
                    "panel_id": layout["panes"]["bottom"],
                },
            ],
            "sizes": [
                round(float(layout["ratio"]), 1),
                round(100 - float(layout["ratio"]), 1),
            ],
        },
        "focus_window_id": "window-top",
        "spotlight_window_id": None,
    }


def _collect_window_ids(node: dict) -> list[str]:
    if node.get("kind") == "window":
        return [str(node.get("id"))]
    result: list[str] = []
    for child in node.get("children", []):
        if isinstance(child, dict):
            result.extend(_collect_window_ids(child))
    return result


def _sanitize_composer_layout(raw: dict | None, *, allowed_panels: list[str], fallback_layout: dict) -> dict:
    fallback = _default_composer_from_layout(fallback_layout)
    if not isinstance(raw, dict):
        return fallback

    state = {"counter": 0, "windows": 0}
    used_ids: set[str] = set()
    fallback_panel = fallback_layout["panes"]["top"]

    def _next_id(prefix: str) -> str:
        state["counter"] += 1
        return f"{prefix}-{state['counter']}"

    def _safe_id(raw_id: object, prefix: str) -> str:
        if isinstance(raw_id, str):
            cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", raw_id)[:48]
            if cleaned and cleaned not in used_ids:
                used_ids.add(cleaned)
                return cleaned
        generated = _next_id(prefix)
        used_ids.add(generated)
        return generated

    def _sanitize_node(node: dict | None, depth: int = 0) -> dict:
        if not isinstance(node, dict) or depth > MAX_LAYOUT_DEPTH:
            state["windows"] += 1
            return {
                "id": _safe_id(None, "window"),
                "kind": "window",
                "panel_id": fallback_panel,
            }

        if node.get("kind") == "split":
            axis = node.get("axis")
            if axis not in {"horizontal", "vertical"}:
                axis = "horizontal"

            children_raw = node.get("children") if isinstance(node.get("children"), list) else []
            children: list[dict] = []
            for child in children_raw[:MAX_LAYOUT_CHILDREN]:
                if state["windows"] >= MAX_LAYOUT_WINDOWS:
                    break
                children.append(_sanitize_node(child, depth + 1))

            if len(children) < 2:
                state["windows"] += 1
                return {
                    "id": _safe_id(node.get("id"), "window"),
                    "kind": "window",
                    "panel_id": fallback_panel,
                }

            return {
                "id": _safe_id(node.get("id"), "split"),
                "kind": "split",
                "axis": axis,
                "children": children,
                "sizes": _normalize_layout_sizes(node.get("sizes"), len(children)),
            }

        panel_id = node.get("panel_id")
        if panel_id not in allowed_panels:
            panel_id = fallback_panel
        state["windows"] += 1
        return {
            "id": _safe_id(node.get("id"), "window"),
            "kind": "window",
            "panel_id": panel_id,
        }

    root = _sanitize_node(raw.get("root"))
    leaf_ids = _collect_window_ids(root)
    if not leaf_ids:
        return fallback

    focus_window_id = raw.get("focus_window_id")
    if focus_window_id not in leaf_ids:
        focus_window_id = leaf_ids[0]

    spotlight_window_id = raw.get("spotlight_window_id")
    if spotlight_window_id not in leaf_ids:
        spotlight_window_id = None

    return {
        "root": root,
        "focus_window_id": focus_window_id,
        "spotlight_window_id": spotlight_window_id,
    }


def sanitize_layout_payload(user: User, payload: dict | None, preset_code: str | None = None) -> dict:
    fallback = _default_layout_for_preset(user, preset_code)
    if not isinstance(payload, dict):
        return fallback

    allowed_panels = {panel["id"] for panel in get_available_panels(user)}
    ratio_raw = payload.get("ratio", fallback["ratio"])
    try:
        ratio = round(min(70.0, max(34.0, float(ratio_raw))), 1)
    except (TypeError, ValueError):
        ratio = fallback["ratio"]

    panes = payload.get("panes") if isinstance(payload.get("panes"), dict) else {}
    top_panel = panes.get("top")
    bottom_panel = panes.get("bottom")

    if top_panel not in allowed_panels:
        top_panel = fallback["panes"]["top"]
    if bottom_panel not in allowed_panels or bottom_panel == top_panel:
        bottom_panel = fallback["panes"]["bottom"]
    if bottom_panel == top_panel:
        bottom_panel = next((item for item in allowed_panels if item != top_panel), top_panel)

    chrome_payload = payload.get("chrome") if isinstance(payload.get("chrome"), dict) else {}
    density = chrome_payload.get("density", fallback["chrome"]["density"])
    if density not in {"compact", "cozy"}:
        density = fallback["chrome"]["density"]

    layout = {
        "version": 2,
        "preset": fallback["preset"],
        "ratio": ratio,
        "panes": {
            "top": top_panel,
            "bottom": bottom_panel,
        },
        "chrome": {
            "density": density,
            "dock_compact": bool(chrome_payload.get("dock_compact", False)),
        },
    }
    layout["composer"] = _sanitize_composer_layout(
        payload.get("composer") if isinstance(payload, dict) else None,
        allowed_panels=sorted(allowed_panels),
        fallback_layout=layout,
    )
    return layout


async def get_workspace_layout(
    session: AsyncSession,
    *,
    user: User,
    preset_code: str | None = None,
) -> dict:
    layout_preset = preset_code or _default_layout_for_preset(user, None)["preset"]
    record = (
        await session.execute(
            select(WorkspaceLayout).where(
                WorkspaceLayout.user_id == user.id,
                WorkspaceLayout.preset_code == layout_preset,
            )
        )
    ).scalar_one_or_none()
    if not record:
        return sanitize_layout_payload(user, None, layout_preset)
    return sanitize_layout_payload(user, record.layout_json, layout_preset)


async def save_workspace_layout(
    session: AsyncSession,
    *,
    user: User,
    preset_code: str,
    payload: dict | None,
) -> dict:
    layout = sanitize_layout_payload(user, payload, preset_code)
    record = (
        await session.execute(
            select(WorkspaceLayout).where(
                WorkspaceLayout.user_id == user.id,
                WorkspaceLayout.preset_code == layout["preset"],
            )
        )
    ).scalar_one_or_none()

    if record is None:
        record = WorkspaceLayout(
            user_id=user.id,
            preset_code=layout["preset"],
            layout_json=layout,
        )
        session.add(record)
    else:
        record.layout_json = layout

    await session.flush()
    await log_audit(
        session,
        user_id=user.id,
        action="workspace.layout.saved",
        entity_type="workspace_layout",
        entity_id=record.id,
        new_value=layout,
    )
    return layout


def _clean_text(value: str | None, *, field: str, max_length: int, allow_empty: bool = False) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        return "" if allow_empty else None
    if len(cleaned) > max_length:
        raise ValidationError(f"Поле '{field}' слишком длинное")
    return cleaned


def _clean_string_list(values: list[str] | None, *, field: str, max_items: int, max_length: int) -> list[str]:
    if not values:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        cleaned = _clean_text(raw, field=field, max_length=max_length)
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
        if len(result) >= max_items:
            break
    return result


def _clean_portfolio_entries(entries: list[dict] | None) -> list[dict]:
    if not entries:
        return []
    cleaned_entries: list[dict] = []
    for entry in entries[:8]:
        if not isinstance(entry, dict):
            continue
        title = _clean_text(entry.get("title"), field="portfolio.title", max_length=80)
        url = _clean_text(entry.get("url"), field="portfolio.url", max_length=240)
        kind = _clean_text(entry.get("kind"), field="portfolio.kind", max_length=32) or "project"
        if not title and not url:
            continue
        cleaned_entries.append(
            {
                "title": title or "Проект",
                "url": url or "",
                "kind": kind,
            }
        )
    return cleaned_entries


def _serialize_master_review(review: MasterReview) -> dict:
    return {
        "id": review.id,
        "order_id": review.order_id,
        "rating": int(review.rating),
        "headline": review.headline or "",
        "body": review.body or "",
        "is_public": bool(review.is_public),
        "created_at": review.created_at.isoformat() if review.created_at else None,
        "author": {
            "id": review.author.id if review.author else review.author_user_id,
            "name": review.author.display_name if review.author else "Клиент",
            "external_user_id": review.author.telegram_id if review.author else None,
        },
    }


def _build_trust_badges(
    *,
    public_profile: PublicMasterProfile | None,
    completed_jobs: int,
    portfolio_size: int,
) -> list[dict]:
    badges: list[dict] = []
    verification_status = (public_profile.verification_status if public_profile else None) or "community"
    rating_average = float(public_profile.rating_average or 0) if public_profile else 0.0
    rating_count = int(public_profile.rating_count or 0) if public_profile else 0
    response_time_label = (public_profile.response_time_label if public_profile else None) or ""

    if verification_status in {"verified", "trusted", "pro"}:
        badges.append(
            {
                "code": "verified",
                "label": "Проверен платформой",
                "tone": "success",
            }
        )
    if rating_count >= 3 and rating_average >= 4.7:
        badges.append(
            {
                "code": "top-rated",
                "label": f"{rating_average:.1f} рейтинг",
                "tone": "success",
            }
        )
    if completed_jobs >= 10:
        badges.append(
            {
                "code": "experienced",
                "label": f"{completed_jobs}+ завершено",
                "tone": "neutral",
            }
        )
    if portfolio_size >= 2:
        badges.append(
            {
                "code": "portfolio",
                "label": "Есть портфолио",
                "tone": "neutral",
            }
        )
    if response_time_label:
        badges.append(
            {
                "code": "response-time",
                "label": response_time_label,
                "tone": "neutral",
            }
        )
    return badges[:4]


async def _ensure_public_master_profile(session: AsyncSession, user_id: int) -> PublicMasterProfile:
    record = (
        await session.execute(
            select(PublicMasterProfile).where(PublicMasterProfile.user_id == user_id)
        )
    ).scalar_one_or_none()
    if record is not None:
        return record

    record = PublicMasterProfile(user_id=user_id)
    session.add(record)
    await session.flush()
    return record


async def refresh_public_master_profile_metrics(
    session: AsyncSession,
    *,
    master_user_id: int,
) -> PublicMasterProfile:
    record = await _ensure_public_master_profile(session, master_user_id)

    review_stats = (
        await session.execute(
            select(
                func.coalesce(func.avg(MasterReview.rating), 0),
                func.count(MasterReview.id),
            ).where(MasterReview.master_user_id == master_user_id)
        )
    ).one()
    completed_jobs = (
        await session.execute(
            select(func.count(Order.id)).where(
                Order.master_id == master_user_id,
                Order.status.in_(list(REVIEWABLE_ORDER_STATUSES)),
            )
        )
    ).scalar() or 0

    record.rating_average = round(float(review_stats[0] or 0), 2)
    record.rating_count = int(review_stats[1] or 0)
    record.completed_jobs = int(completed_jobs)
    await session.flush()
    return record


async def list_master_reviews(
    session: AsyncSession,
    *,
    viewer: User | None,
    master_user_id: int,
    limit: int = 6,
) -> list[dict]:
    query = (
        select(MasterReview)
        .where(MasterReview.master_user_id == master_user_id)
        .order_by(MasterReview.created_at.desc(), MasterReview.id.desc())
        .limit(min(max(limit, 1), 12))
    )
    if not (
        viewer
        and (
            _can_view_control(viewer)
            or viewer.id == master_user_id
        )
    ):
        query = query.where(MasterReview.is_public == True)  # noqa: E712

    reviews = list((await session.execute(query)).scalars().all())
    return [_serialize_master_review(review) for review in reviews]


def _can_create_master_review(viewer: User, order: Order) -> bool:
    return (
        order.client_id == viewer.id
        and order.master_id is not None
        and order.status in REVIEWABLE_ORDER_STATUSES
    )


async def build_order_review_state(
    session: AsyncSession,
    *,
    viewer: User,
    order: Order,
) -> dict:
    review = (
        await session.execute(
            select(MasterReview).where(MasterReview.order_id == order.id)
        )
    ).scalar_one_or_none()

    return {
        "can_create": review is None and _can_create_master_review(viewer, order),
        "item": _serialize_master_review(review) if review else None,
    }


async def create_master_review(
    session: AsyncSession,
    *,
    viewer: User,
    order_id: int,
    rating: int,
    headline: str | None = None,
    body: str | None = None,
    is_public: bool = True,
) -> dict:
    order = (
        await session.execute(select(Order).where(Order.id == order_id))
    ).scalar_one_or_none()
    if not order:
        raise NotFoundError("Заказ")
    if order.client_id != viewer.id:
        raise PermissionDenied("Оставить отзыв может только клиент по этому заказу")
    if order.master_id is None:
        raise ValidationError("По заказу еще не назначен мастер")
    if order.status not in REVIEWABLE_ORDER_STATUSES:
        raise ValidationError("Отзыв можно оставить только после завершения заказа")

    try:
        normalized_rating = int(rating)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Оценка должна быть числом от 1 до 5") from exc
    if normalized_rating < 1 or normalized_rating > 5:
        raise ValidationError("Оценка должна быть от 1 до 5")

    existing = (
        await session.execute(
            select(MasterReview).where(MasterReview.order_id == order_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("Отзыв по этому заказу уже сохранен")

    review = MasterReview(
        order_id=order.id,
        master_user_id=order.master_id,
        author_user_id=viewer.id,
        rating=normalized_rating,
        headline=_clean_text(headline, field="headline", max_length=120, allow_empty=True),
        body=_clean_text(body, field="body", max_length=1200, allow_empty=True),
        is_public=bool(is_public),
        author=viewer,
    )
    session.add(review)
    await session.flush()

    updated_profile = await refresh_public_master_profile_metrics(
        session,
        master_user_id=order.master_id,
    )

    session.add(
        Notification(
            user_id=order.master_id,
            event_type="master.review.created",
            title="Новый отзыв по заказу",
            body=f"{viewer.display_name} оставил отзыв {normalized_rating}/5 по заказу #{order.id}",
            channel="max",
            entity_type="order",
            entity_id=order.id,
            status="pending",
        )
    )
    await session.flush()

    await log_audit(
        session,
        user_id=viewer.id,
        action="master_review.created",
        entity_type="master_review",
        entity_id=review.id,
        new_value={
            "order_id": order.id,
            "master_user_id": order.master_id,
            "rating": normalized_rating,
            "is_public": bool(is_public),
            "rating_average": float(updated_profile.rating_average or 0),
            "rating_count": int(updated_profile.rating_count or 0),
        },
    )
    return _serialize_master_review(review)


def _serialize_job_post(
    *,
    post: JobPost,
    author: User,
    response_count: int,
    has_responded: bool,
    viewer: User,
) -> dict:
    budget = None
    if post.budget_from is not None or post.budget_to is not None:
        budget = {
            "from": post.budget_from,
            "to": post.budget_to,
        }

    return {
        "id": post.id,
        "title": post.title,
        "description": post.description,
        "city": post.city,
        "urgency": post.urgency,
        "status": post.status,
        "budget": budget,
        "desired_start_label": post.desired_start_label,
        "preferred_contact": post.preferred_contact,
        "created_at": post.created_at.isoformat() if post.created_at else None,
        "updated_at": post.updated_at.isoformat() if post.updated_at else None,
        "response_count": response_count,
        "has_responded": has_responded,
        "is_owner": author.id == viewer.id,
        "can_respond": author.id != viewer.id and post.status == "open" and _can_respond_to_board(viewer),
        "author": {
            "id": author.id,
            "external_id": author.telegram_id,
            "name": author.display_name,
        },
    }


def _serialize_job_post_response(
    *,
    response: JobPostResponse,
    responder: User,
) -> dict:
    return {
        "id": response.id,
        "job_post_id": response.job_post_id,
        "status": response.status,
        "message": response.message,
        "price_offer": response.price_offer,
        "eta_label": response.eta_label,
        "created_at": response.created_at.isoformat() if response.created_at else None,
        "responder": {
            "id": responder.id,
            "external_id": responder.telegram_id,
            "name": responder.display_name,
            "username": responder.username,
        },
    }


async def list_job_posts(
    session: AsyncSession,
    *,
    viewer: User,
    status: str = "open",
    limit: int = 20,
    offset: int = 0,
    only_own: bool = False,
) -> dict:
    query = (
        select(JobPost, User)
        .join(User, User.id == JobPost.author_user_id)
        .order_by(JobPost.created_at.desc(), JobPost.id.desc())
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 50))
    )
    if status != "all":
        query = query.where(JobPost.status == status)
    if only_own:
        query = query.where(JobPost.author_user_id == viewer.id)

    rows = list((await session.execute(query)).all())
    posts = [row[0] for row in rows]
    authors = {row[1].id: row[1] for row in rows}
    if not posts:
        return {"items": [], "meta": {"limit": limit, "offset": offset}}

    post_ids = [post.id for post in posts]
    response_counts = dict(
        (
            await session.execute(
                select(JobPostResponse.job_post_id, func.count(JobPostResponse.id))
                .where(
                    JobPostResponse.job_post_id.in_(post_ids),
                    JobPostResponse.status.in_(list(ACTIVE_JOB_RESPONSE_STATUSES)),
                )
                .group_by(JobPostResponse.job_post_id)
            )
        ).all()
    )
    responded = set(
        (
            await session.execute(
                select(JobPostResponse.job_post_id).where(
                    JobPostResponse.job_post_id.in_(post_ids),
                    JobPostResponse.responder_user_id == viewer.id,
                    JobPostResponse.status.in_(list(ACTIVE_JOB_RESPONSE_STATUSES)),
                )
            )
        ).scalars().all()
    )

    return {
        "items": [
            _serialize_job_post(
                post=post,
                author=authors[post.author_user_id],
                response_count=response_counts.get(post.id, 0),
                has_responded=post.id in responded,
                viewer=viewer,
            )
            for post in posts
        ],
        "meta": {"limit": limit, "offset": offset},
    }


async def list_job_post_responses(
    session: AsyncSession,
    *,
    viewer: User,
    post_id: int,
) -> dict:
    post = await session.get(JobPost, post_id)
    if not post:
        raise NotFoundError("Заявка")
    if post.author_user_id != viewer.id and not _can_view_control(viewer):
        raise PermissionDenied("Отклики доступны только автору заявки")

    rows = list(
        (
            await session.execute(
                select(JobPostResponse, User)
                .join(User, User.id == JobPostResponse.responder_user_id)
                .where(JobPostResponse.job_post_id == post_id)
                .order_by(JobPostResponse.created_at.desc(), JobPostResponse.id.desc())
            )
        ).all()
    )

    return {
        "post": _serialize_job_post(
            post=post,
            author=viewer if post.author_user_id == viewer.id else (await session.get(User, post.author_user_id)),
            response_count=len(rows),
            has_responded=False,
            viewer=viewer,
        ),
        "items": [
            _serialize_job_post_response(
                response=response,
                responder=responder,
            )
            for response, responder in rows
        ],
        "meta": {
            "count": len(rows),
        },
    }


async def create_job_post(
    session: AsyncSession,
    *,
    author: User,
    title: str,
    description: str,
    city: str | None = None,
    budget_from: int | None = None,
    budget_to: int | None = None,
    urgency: str = "normal",
    desired_start_label: str | None = None,
    preferred_contact: str | None = None,
) -> dict:
    title_clean = _clean_text(title, field="title", max_length=160)
    description_clean = _clean_text(description, field="description", max_length=1200)
    city_clean = _clean_text(city, field="city", max_length=120)
    desired_clean = _clean_text(
        desired_start_label,
        field="desired_start_label",
        max_length=120,
    )
    contact_clean = _clean_text(preferred_contact, field="preferred_contact", max_length=30)

    if not title_clean or len(title_clean) < 4:
        raise ValidationError("Название заявки слишком короткое")
    if not description_clean or len(description_clean) < 12:
        raise ValidationError("Опишите задачу чуть подробнее")
    if urgency not in {"normal", "urgent", "asap"}:
        raise ValidationError("Некорректная срочность")
    if budget_from is not None and budget_from < 0:
        raise ValidationError("Бюджет 'от' не может быть отрицательным")
    if budget_to is not None and budget_to < 0:
        raise ValidationError("Бюджет 'до' не может быть отрицательным")
    if budget_from is not None and budget_to is not None and budget_from > budget_to:
        raise ValidationError("Минимальный бюджет не может быть больше максимального")

    post = JobPost(
        author_user_id=author.id,
        title=title_clean,
        description=description_clean,
        city=city_clean,
        budget_from=budget_from,
        budget_to=budget_to,
        urgency=urgency,
        desired_start_label=desired_clean,
        preferred_contact=contact_clean,
        source_channel="max",
    )
    session.add(post)
    await session.flush()

    await log_audit(
        session,
        user_id=author.id,
        action="job_post.created",
        entity_type="job_post",
        entity_id=post.id,
        new_value={
            "title": post.title,
            "city": post.city,
            "urgency": post.urgency,
        },
    )
    return _serialize_job_post(
        post=post,
        author=author,
        response_count=0,
        has_responded=False,
        viewer=author,
    )


async def respond_to_job_post(
    session: AsyncSession,
    *,
    viewer: User,
    post_id: int,
    message: str,
    price_offer: int | None = None,
    eta_label: str | None = None,
) -> dict:
    if not _can_respond_to_board(viewer):
        raise PermissionDenied("Откликаться на заявки могут только мастера")

    post = await session.get(JobPost, post_id)
    if not post:
        raise NotFoundError("Заявка")
    if post.author_user_id == viewer.id:
        raise ConflictError("Нельзя откликнуться на собственную заявку")
    if post.status != "open":
        raise ValidationError("Эта заявка уже закрыта")

    message_clean = _clean_text(message, field="message", max_length=500)
    eta_clean = _clean_text(eta_label, field="eta_label", max_length=120)
    if not message_clean or len(message_clean) < 8:
        raise ValidationError("Сообщение отклика слишком короткое")
    if price_offer is not None and price_offer < 0:
        raise ValidationError("Предложенная цена не может быть отрицательной")

    response = (
        await session.execute(
            select(JobPostResponse).where(
                JobPostResponse.job_post_id == post_id,
                JobPostResponse.responder_user_id == viewer.id,
            )
        )
    ).scalar_one_or_none()

    if response and response.status in ACTIVE_JOB_RESPONSE_STATUSES:
        raise ConflictError("Вы уже откликались на эту заявку")

    if response is None:
        response = JobPostResponse(
            job_post_id=post_id,
            responder_user_id=viewer.id,
            message=message_clean,
            price_offer=price_offer,
            eta_label=eta_clean,
            status="submitted",
        )
        session.add(response)
    else:
        response.message = message_clean
        response.price_offer = price_offer
        response.eta_label = eta_clean
        response.status = "submitted"

    session.add(
        Notification(
            user_id=post.author_user_id,
            event_type="job_post.response_created",
            title="Новый отклик на заявку",
            body=f"{viewer.display_name} откликнулся на «{post.title}».",
            channel="max",
            entity_type="job_post",
            entity_id=post.id,
        )
    )
    await session.flush()

    await log_audit(
        session,
        user_id=viewer.id,
        action="job_post.responded",
        entity_type="job_post",
        entity_id=post.id,
        new_value={"response_id": response.id},
    )

    return {
        "id": response.id,
        "status": response.status,
        "job_post_id": post.id,
        "message": response.message,
        "price_offer": response.price_offer,
        "eta_label": response.eta_label,
    }


def _role_tier(user: User) -> str:
    if has_role(user, Role.SENIOR_MASTER):
        return "senior"
    if has_role(user, Role.MASTER):
        return "master"
    return "specialist"


def _serialize_public_profile(
    *,
    user: User,
    public_profile: PublicMasterProfile | None,
    master_profile: MasterProfile | None,
    completed_jobs: int,
    active_jobs: int,
) -> dict:
    public = public_profile or PublicMasterProfile(user_id=user.id)
    specialization = master_profile.specialization if master_profile else None
    title = public.headline or specialization or "Мастер"
    skills = list(public.skills_json or [])
    if not skills and specialization:
        skills = [specialization]
    portfolio = list(public.portfolio_json or [])
    computed_completed = max(int(public.completed_jobs or 0), completed_jobs)
    trust_badges = _build_trust_badges(
        public_profile=public_profile,
        completed_jobs=computed_completed,
        portfolio_size=len(portfolio),
    )

    return {
        "user_id": user.id,
        "external_user_id": user.telegram_id,
        "name": user.display_name,
        "username": user.username,
        "title": title,
        "bio": public.bio or "",
        "city": public.city or "",
        "experience_years": int(public.experience_years or 0),
        "hourly_rate_from": public.hourly_rate_from,
        "hourly_rate_to": public.hourly_rate_to,
        "availability_status": public.availability_status or "open",
        "verification_status": public.verification_status or "community",
        "rating_average": float(public.rating_average or 0),
        "rating_count": int(public.rating_count or 0),
        "completed_jobs": computed_completed,
        "active_jobs": active_jobs,
        "skills": skills,
        "portfolio": portfolio,
        "accent_color": public.accent_color or "#95c7ff",
        "is_public": bool(public.is_public),
        "tier": _role_tier(user),
        "specialization": specialization or "",
        "response_time_label": public.response_time_label or "",
        "trust_badges": trust_badges,
    }


async def list_master_network(
    session: AsyncSession,
    *,
    viewer: User,
    query_text: str | None = None,
    availability: str | None = None,
    limit: int = 20,
    offset: int = 0,
    include_private: bool = False,
) -> dict:
    user_query = (
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .where(User.is_active == True)  # noqa: E712
        .where(UserRole.role_code.in_(list(PROVIDER_ROLE_CODES)))
        .distinct()
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 50))
    )

    if query_text:
        search = f"%{query_text.strip().lower()}%"
        user_query = (
            user_query.outerjoin(MasterProfile, MasterProfile.user_id == User.id)
            .outerjoin(PublicMasterProfile, PublicMasterProfile.user_id == User.id)
            .where(
                or_(
                    func.lower(User.first_name).like(search),
                    func.lower(func.coalesce(User.last_name, "")).like(search),
                    func.lower(func.coalesce(PublicMasterProfile.headline, "")).like(search),
                    func.lower(func.coalesce(MasterProfile.specialization, "")).like(search),
                    func.lower(func.coalesce(PublicMasterProfile.city, "")).like(search),
                )
            )
        )

    if availability in {"open", "busy", "offline"}:
        user_query = user_query.outerjoin(
            PublicMasterProfile,
            PublicMasterProfile.user_id == User.id,
        ).where(PublicMasterProfile.availability_status == availability)

    users = list((await session.execute(user_query)).scalars().all())
    if not users:
        return {"items": [], "meta": {"limit": limit, "offset": offset}}

    user_ids = [user.id for user in users]
    public_profiles = {
        item.user_id: item
        for item in (
            await session.execute(
                select(PublicMasterProfile).where(PublicMasterProfile.user_id.in_(user_ids))
            )
        ).scalars().all()
    }
    master_profiles = {
        item.user_id: item
        for item in (
            await session.execute(
                select(MasterProfile).where(MasterProfile.user_id.in_(user_ids))
            )
        ).scalars().all()
    }
    completed_counts = dict(
        (
            await session.execute(
                select(Order.master_id, func.count(Order.id))
                .where(
                    Order.master_id.in_(user_ids),
                    Order.status.in_(["completed", "paid"]),
                )
                .group_by(Order.master_id)
            )
        ).all()
    )
    active_counts = dict(
        (
            await session.execute(
                select(Order.master_id, func.count(Order.id))
                .where(
                    Order.master_id.in_(user_ids),
                    Order.status.in_(["assigned", "in_progress", "client_review"]),
                )
                .group_by(Order.master_id)
            )
        ).all()
    )

    viewer_is_control = _can_view_control(viewer)
    items = []
    for user in users:
        public_profile = public_profiles.get(user.id)
        if not public_profile and not include_private:
            continue
        if public_profile and not public_profile.is_public and not viewer_is_control and viewer.id != user.id:
            continue
        items.append(
            _serialize_public_profile(
                user=user,
                public_profile=public_profile,
                master_profile=master_profiles.get(user.id),
                completed_jobs=completed_counts.get(user.id, 0),
                active_jobs=active_counts.get(user.id, 0),
            )
        )

    return {
        "items": items,
        "meta": {"limit": limit, "offset": offset},
    }


async def get_master_network_profile(
    session: AsyncSession,
    *,
    viewer: User,
    external_user_id: int,
) -> dict:
    user = (
        await session.execute(
            select(User).where(User.telegram_id == external_user_id)
        )
    ).scalar_one_or_none()
    if not user:
        raise NotFoundError("Мастер")

    public_profile = (
        await session.execute(
            select(PublicMasterProfile).where(PublicMasterProfile.user_id == user.id)
        )
    ).scalar_one_or_none()
    if (
        public_profile is None or not public_profile.is_public
    ) and not _can_view_control(viewer) and viewer.id != user.id:
        raise NotFoundError("Мастер")

    master_profile = (
        await session.execute(
            select(MasterProfile).where(MasterProfile.user_id == user.id)
        )
    ).scalar_one_or_none()
    completed_jobs = (
        await session.execute(
            select(func.count(Order.id)).where(
                Order.master_id == user.id,
                Order.status.in_(["completed", "paid"]),
            )
        )
    ).scalar() or 0
    active_jobs = (
        await session.execute(
            select(func.count(Order.id)).where(
                Order.master_id == user.id,
                Order.status.in_(["assigned", "in_progress", "client_review"]),
            )
        )
    ).scalar() or 0

    payload = _serialize_public_profile(
        user=user,
        public_profile=public_profile,
        master_profile=master_profile,
        completed_jobs=completed_jobs,
        active_jobs=active_jobs,
    )
    payload["reviews"] = await list_master_reviews(
        session,
        viewer=viewer,
        master_user_id=user.id,
        limit=6,
    )
    return payload


async def get_public_master_profile_for_edit(
    session: AsyncSession,
    *,
    user: User,
) -> dict:
    if not _can_publish_master_profile(user):
        raise PermissionDenied("Публичный профиль доступен только мастерам")

    public_profile = (
        await session.execute(
            select(PublicMasterProfile).where(PublicMasterProfile.user_id == user.id)
        )
    ).scalar_one_or_none()
    master_profile = (
        await session.execute(
            select(MasterProfile).where(MasterProfile.user_id == user.id)
        )
    ).scalar_one_or_none()

    payload = _serialize_public_profile(
        user=user,
        public_profile=public_profile,
        master_profile=master_profile,
        completed_jobs=0,
        active_jobs=0,
    )
    payload["reviews"] = await list_master_reviews(
        session,
        viewer=user,
        master_user_id=user.id,
        limit=6,
    )
    payload["edit"] = {
        "headline": public_profile.headline if public_profile else (master_profile.specialization if master_profile else ""),
        "bio": public_profile.bio if public_profile else "",
        "city": public_profile.city if public_profile else "",
        "experience_years": int(public_profile.experience_years or 0) if public_profile else 0,
        "hourly_rate_from": public_profile.hourly_rate_from if public_profile else None,
        "hourly_rate_to": public_profile.hourly_rate_to if public_profile else None,
        "availability_status": public_profile.availability_status if public_profile else "open",
        "response_time_label": public_profile.response_time_label if public_profile else "",
        "skills": list(public_profile.skills_json or []) if public_profile else [],
        "portfolio": list(public_profile.portfolio_json or []) if public_profile else [],
        "is_public": bool(public_profile.is_public) if public_profile else False,
        "accent_color": public_profile.accent_color if public_profile else "#95c7ff",
    }
    return payload


async def update_public_master_profile(
    session: AsyncSession,
    *,
    user: User,
    payload: dict,
) -> dict:
    if not _can_publish_master_profile(user):
        raise PermissionDenied("Публичный профиль доступен только мастерам")

    record = (
        await session.execute(
            select(PublicMasterProfile).where(PublicMasterProfile.user_id == user.id)
        )
    ).scalar_one_or_none()
    if record is None:
        record = PublicMasterProfile(user_id=user.id)
        session.add(record)

    availability_status = payload.get("availability_status", record.availability_status or "open")
    if availability_status not in {"open", "busy", "offline"}:
        raise ValidationError("Некорректный статус доступности")

    accent_color = payload.get("accent_color")
    if accent_color:
        accent_color = accent_color.strip()
        if not HEX_COLOR_RE.match(accent_color):
            raise ValidationError("accent_color должен быть в формате #RRGGBB")

    experience_years = payload.get("experience_years", record.experience_years or 0)
    if experience_years is None:
        experience_years = 0
    try:
        experience_years = int(experience_years)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Стаж должен быть числом") from exc
    if experience_years < 0 or experience_years > 80:
        raise ValidationError("Стаж вне допустимого диапазона")

    hourly_rate_from = payload.get("hourly_rate_from", record.hourly_rate_from)
    hourly_rate_to = payload.get("hourly_rate_to", record.hourly_rate_to)
    if hourly_rate_from is not None and hourly_rate_from < 0:
        raise ValidationError("Ставка 'от' не может быть отрицательной")
    if hourly_rate_to is not None and hourly_rate_to < 0:
        raise ValidationError("Ставка 'до' не может быть отрицательной")
    if hourly_rate_from is not None and hourly_rate_to is not None and hourly_rate_from > hourly_rate_to:
        raise ValidationError("Ставка 'от' не может быть больше ставки 'до'")

    record.headline = _clean_text(payload.get("headline"), field="headline", max_length=160, allow_empty=True)
    record.bio = _clean_text(payload.get("bio"), field="bio", max_length=700, allow_empty=True)
    record.city = _clean_text(payload.get("city"), field="city", max_length=120, allow_empty=True)
    record.experience_years = experience_years
    record.hourly_rate_from = hourly_rate_from
    record.hourly_rate_to = hourly_rate_to
    record.availability_status = availability_status
    record.response_time_label = _clean_text(
        payload.get("response_time_label"),
        field="response_time_label",
        max_length=80,
        allow_empty=True,
    )
    record.skills_json = _clean_string_list(
        payload.get("skills"),
        field="skills",
        max_items=12,
        max_length=32,
    )
    record.portfolio_json = _clean_portfolio_entries(payload.get("portfolio"))
    record.is_public = bool(payload.get("is_public", record.is_public))
    record.accent_color = accent_color or record.accent_color or "#95c7ff"

    await session.flush()
    await log_audit(
        session,
        user_id=user.id,
        action="public_master_profile.updated",
        entity_type="public_master_profile",
        entity_id=record.id,
        new_value={"is_public": record.is_public},
    )
    return await get_public_master_profile_for_edit(session, user=user)


async def build_superapp_bootstrap(
    session: AsyncSession,
    *,
    user: User,
    preset_code: str | None = None,
) -> dict:
    layout = await get_workspace_layout(session, user=user, preset_code=preset_code)
    dashboard = await get_dashboard_data(session, user)
    board = await list_job_posts(session, viewer=user, limit=4, offset=0, status="open")
    network = await list_master_network(
        session,
        viewer=user,
        limit=6,
        offset=0,
        include_private=_can_view_control(user),
    )
    profile = await get_profile_payload(session, user)
    onboarding = []
    if not profile_has_bank_details(profile):
        onboarding.append(
            {
                "id": "payments-profile",
                "title": "Заполнить платёжные данные",
                "description": "Нужны для QR и нормального завершения сделок.",
            }
        )
    if _can_publish_master_profile(user):
        public_profile = (
            await session.execute(
                select(PublicMasterProfile).where(PublicMasterProfile.user_id == user.id)
            )
        ).scalar_one_or_none()
        if not public_profile or not public_profile.is_public:
            onboarding.append(
                {
                    "id": "publish-profile",
                    "title": "Опубликовать страницу мастера",
                    "description": "Без публичного профиля вас не увидят в сети мастеров.",
                }
            )

    return {
        "layout": layout,
        "presets": get_available_presets(user),
        "panels": get_available_panels(user),
        "capabilities": {
            "can_post_jobs": True,
            "can_respond_to_jobs": _can_respond_to_board(user),
            "can_create_estimate": _can_create_estimate(user),
            "can_create_order": _can_create_order(user),
            "can_publish_master_profile": _can_publish_master_profile(user),
            "can_process_approvals": _can_process_approvals(user),
            "can_view_control": _can_view_control(user),
        },
        "workspace": {
            **dashboard,
            "onboarding": onboarding,
        },
        "board": {
            "items": board["items"],
            "total": len(board["items"]),
        },
        "network": {
            "items": network["items"],
            "total": len(network["items"]),
        },
        "profile": {
            "name": user.display_name,
            "external_user_id": user.telegram_id,
            "roles": [role.role_code for role in user.roles],
            "phone": profile.get("phone") or "",
            "specialization": profile.get("specialization") or "",
        },
        "notifications": {
            "unread": await count_unread_notifications_for_user(session, user_id=user.id),
        },
    }
