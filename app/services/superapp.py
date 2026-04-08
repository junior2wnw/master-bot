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
from app.models.superapp import JobPost, JobPostResponse, PublicMasterProfile, WorkspaceLayout
from app.models.user import User, UserRole
from app.services.profile import get_profile_payload, profile_has_bank_details
from app.services.workspace import count_unread_notifications_for_user, get_dashboard_data

ACTIVE_JOB_RESPONSE_STATUSES = {"submitted", "shortlisted", "accepted"}
PROVIDER_ROLE_CODES = {"master", "senior_master"}
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

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
        "top_panel": "analytics-overview",
        "bottom_panel": "approvals-queue",
        "visibility": "admin",
    },
)


def _can_publish_master_profile(user: User) -> bool:
    return has_permission(user, Permission.ESTIMATE_CREATE)


def _can_respond_to_board(user: User) -> bool:
    return has_permission(user, Permission.ESTIMATE_CREATE)


def _can_view_control(user: User) -> bool:
    return has_permission(user, Permission.ADMIN_PANEL) or has_role(user, Role.PRODUCT_OWNER)


def _panel_is_visible(user: User, visibility: str) -> bool:
    if visibility == "all":
        return True
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

    return {
        "version": 1,
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

    return {
        "version": 1,
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
    computed_completed = max(int(public.completed_jobs or 0), completed_jobs)

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
        "portfolio": list(public.portfolio_json or []),
        "accent_color": public.accent_color or "#95c7ff",
        "is_public": bool(public.is_public),
        "tier": _role_tier(user),
        "specialization": specialization or "",
        "response_time_label": public.response_time_label or "",
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

    return _serialize_public_profile(
        user=user,
        public_profile=public_profile,
        master_profile=master_profile,
        completed_jobs=completed_jobs,
        active_jobs=active_jobs,
    )


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
            "can_publish_master_profile": _can_publish_master_profile(user),
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
