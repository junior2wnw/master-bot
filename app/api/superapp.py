"""Superapp API: board, network, layouts, bootstrap."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.shared import get_current_user
from app.core.exceptions import ConflictError, NotFoundError, PermissionDenied, ValidationError
from app.models.user import User
from app.services.superapp import (
    build_superapp_bootstrap,
    create_job_post,
    get_master_network_profile,
    get_public_master_profile_for_edit,
    get_workspace_layout,
    list_job_post_responses,
    list_job_posts,
    list_master_network,
    respond_to_job_post,
    save_workspace_layout,
    update_public_master_profile,
)

router = APIRouter(prefix="/api/v1", tags=["superapp"])


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, ValidationError):
        raise HTTPException(400, exc.message) from exc
    if isinstance(exc, ConflictError):
        raise HTTPException(409, exc.message) from exc
    if isinstance(exc, PermissionDenied):
        raise HTTPException(403, exc.message) from exc
    if isinstance(exc, NotFoundError):
        raise HTTPException(404, exc.message) from exc
    raise exc


class LayoutUpdateRequest(BaseModel):
    preset: str = Field(min_length=2, max_length=32)
    layout: dict


class JobPostCreateRequest(BaseModel):
    title: str = Field(min_length=4, max_length=160)
    description: str = Field(min_length=12, max_length=1200)
    city: str | None = Field(default=None, max_length=120)
    budget_from: int | None = Field(default=None, ge=0)
    budget_to: int | None = Field(default=None, ge=0)
    urgency: str = Field(default="normal")
    desired_start_label: str | None = Field(default=None, max_length=120)
    preferred_contact: str | None = Field(default=None, max_length=30)


class JobPostResponseRequest(BaseModel):
    message: str = Field(min_length=8, max_length=500)
    price_offer: int | None = Field(default=None, ge=0)
    eta_label: str | None = Field(default=None, max_length=120)


class PublicMasterProfileUpdateRequest(BaseModel):
    headline: str | None = Field(default=None, max_length=160)
    bio: str | None = Field(default=None, max_length=700)
    city: str | None = Field(default=None, max_length=120)
    experience_years: int = Field(default=0, ge=0, le=80)
    hourly_rate_from: int | None = Field(default=None, ge=0)
    hourly_rate_to: int | None = Field(default=None, ge=0)
    availability_status: str = Field(default="open")
    response_time_label: str | None = Field(default=None, max_length=80)
    skills: list[str] = Field(default_factory=list)
    portfolio: list[dict] = Field(default_factory=list)
    is_public: bool = False
    accent_color: str | None = Field(default=None, max_length=20)


@router.get("/superapp/bootstrap")
async def superapp_bootstrap(
    preset: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await build_superapp_bootstrap(session, user=user, preset_code=preset)


@router.get("/superapp/layout")
async def get_layout(
    preset: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await get_workspace_layout(session, user=user, preset_code=preset)


@router.put("/superapp/layout")
async def put_layout(
    body: LayoutUpdateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await save_workspace_layout(
            session,
            user=user,
            preset_code=body.preset,
            payload=body.layout,
        )
    except (ValidationError, ConflictError, PermissionDenied, NotFoundError) as exc:
        _raise_http(exc)


@router.get("/board/posts")
async def get_board_posts(
    status: str = Query(default="open"),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    only_own: bool = False,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await list_job_posts(
        session,
        viewer=user,
        status=status,
        limit=limit,
        offset=offset,
        only_own=only_own,
    )


@router.post("/board/posts")
async def post_board_job(
    body: JobPostCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await create_job_post(session, author=user, **body.model_dump())
    except (ValidationError, ConflictError, PermissionDenied, NotFoundError) as exc:
        _raise_http(exc)


@router.post("/board/posts/{post_id}/responses")
async def post_board_response(
    post_id: int,
    body: JobPostResponseRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await respond_to_job_post(
            session,
            viewer=user,
            post_id=post_id,
            **body.model_dump(),
        )
    except (ValidationError, ConflictError, PermissionDenied, NotFoundError) as exc:
        _raise_http(exc)


@router.get("/board/posts/{post_id}/responses")
async def get_board_post_responses(
    post_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await list_job_post_responses(
            session,
            viewer=user,
            post_id=post_id,
        )
    except (ValidationError, ConflictError, PermissionDenied, NotFoundError) as exc:
        _raise_http(exc)


@router.get("/network/masters")
async def get_network_masters(
    q: str | None = Query(default=None),
    availability: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await list_master_network(
        session,
        viewer=user,
        query_text=q,
        availability=availability,
        limit=limit,
        offset=offset,
    )


@router.get("/network/masters/{external_user_id}")
async def get_network_master(
    external_user_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await get_master_network_profile(
            session,
            viewer=user,
            external_user_id=external_user_id,
        )
    except (ValidationError, ConflictError, PermissionDenied, NotFoundError) as exc:
        _raise_http(exc)


@router.get("/network/profile")
async def get_network_profile(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await get_public_master_profile_for_edit(session, user=user)
    except (ValidationError, ConflictError, PermissionDenied, NotFoundError) as exc:
        _raise_http(exc)


@router.put("/network/profile")
async def put_network_profile(
    body: PublicMasterProfileUpdateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await update_public_master_profile(
            session,
            user=user,
            payload=body.model_dump(),
        )
    except (ValidationError, ConflictError, PermissionDenied, NotFoundError) as exc:
        _raise_http(exc)
