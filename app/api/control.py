"""Control Center API for Mini App operations workflows."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.shared import get_current_user
from app.core.exceptions import NotFoundError, PermissionDenied, ValidationError
from app.models.user import User
from app.services.control_center import (
    build_control_center_bootstrap,
    create_control_invite,
    create_control_staffing_action,
    list_accessible_branches,
    list_control_feature_flags,
    list_control_invite_activations,
    list_control_invites,
    list_control_staffing_actions,
    list_control_users,
    moderate_control_staffing_action,
    moderate_invite_activation,
    toggle_control_feature_flag,
)

router = APIRouter(prefix="/api/v1/control", tags=["control"])


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, ValidationError):
        raise HTTPException(400, exc.message) from exc
    if isinstance(exc, PermissionDenied):
        raise HTTPException(403, exc.message) from exc
    if isinstance(exc, NotFoundError):
        raise HTTPException(404, exc.message) from exc
    raise exc


class CreateInviteRequest(BaseModel):
    role_code: str = Field(min_length=3, max_length=30)
    branch_id: int | None = Field(default=None, ge=1)
    profession_id: int | None = Field(default=None, ge=1)
    max_uses: int = Field(default=1, ge=1, le=100)
    requires_approval: bool = False
    expires_in_days: int | None = Field(default=None, ge=1, le=365)


class ModerateInviteRequest(BaseModel):
    action: Literal["approve", "reject"]


class CreateStaffingActionRequest(BaseModel):
    external_user_id: int
    action_type: str = Field(min_length=3, max_length=30)
    reason: str = Field(min_length=4, max_length=500)
    role_code: str | None = Field(default=None, max_length=30)
    new_branch_id: int | None = Field(default=None, ge=1)


class ModerateStaffingRequest(BaseModel):
    action: Literal["approve", "reject"]
    comment: str | None = Field(default=None, max_length=240)


class FeatureFlagUpdateRequest(BaseModel):
    enabled: bool


@router.get("/bootstrap")
async def control_bootstrap(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await build_control_center_bootstrap(session, viewer=user)
    except (ValidationError, PermissionDenied, NotFoundError) as exc:
        _raise_http(exc)


@router.get("/users")
async def control_users(
    q: str | None = Query(default=None),
    role: str | None = Query(default=None),
    status: str = Query(default="active"),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await list_control_users(
            session,
            viewer=user,
            query_text=q,
            role_code=role,
            status=status,
            limit=limit,
            offset=offset,
        )
    except (ValidationError, PermissionDenied, NotFoundError) as exc:
        _raise_http(exc)


@router.get("/branches")
async def control_branches(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await list_accessible_branches(session, viewer=user)
    except (ValidationError, PermissionDenied, NotFoundError) as exc:
        _raise_http(exc)


@router.get("/invites")
async def control_invites(
    status: str = Query(default="active"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await list_control_invites(
            session,
            viewer=user,
            status=status,
            limit=limit,
            offset=offset,
        )
    except (ValidationError, PermissionDenied, NotFoundError) as exc:
        _raise_http(exc)


@router.post("/invites")
async def control_create_invite(
    body: CreateInviteRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await create_control_invite(
            session,
            viewer=user,
            **body.model_dump(),
        )
    except (ValidationError, PermissionDenied, NotFoundError) as exc:
        _raise_http(exc)


@router.get("/invite-activations")
async def control_invite_activations(
    status: str = Query(default="pending"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await list_control_invite_activations(
            session,
            viewer=user,
            status=status,
            limit=limit,
            offset=offset,
        )
    except (ValidationError, PermissionDenied, NotFoundError) as exc:
        _raise_http(exc)


@router.post("/invite-activations/{activation_id}")
async def control_moderate_invite(
    activation_id: int,
    body: ModerateInviteRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await moderate_invite_activation(
            session,
            viewer=user,
            activation_id=activation_id,
            action=body.action,
        )
    except (ValidationError, PermissionDenied, NotFoundError) as exc:
        _raise_http(exc)


@router.get("/staffing")
async def control_staffing(
    status: str = Query(default="pending"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await list_control_staffing_actions(
            session,
            viewer=user,
            status=status,
            limit=limit,
            offset=offset,
        )
    except (ValidationError, PermissionDenied, NotFoundError) as exc:
        _raise_http(exc)


@router.post("/staffing")
async def control_create_staffing(
    body: CreateStaffingActionRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await create_control_staffing_action(
            session,
            viewer=user,
            **body.model_dump(),
        )
    except (ValidationError, PermissionDenied, NotFoundError) as exc:
        _raise_http(exc)


@router.post("/staffing/{action_id}")
async def control_moderate_staffing(
    action_id: int,
    body: ModerateStaffingRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await moderate_control_staffing_action(
            session,
            viewer=user,
            action_id=action_id,
            action=body.action,
            comment=body.comment,
        )
    except (ValidationError, PermissionDenied, NotFoundError) as exc:
        _raise_http(exc)


@router.get("/flags")
async def control_flags(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await list_control_feature_flags(session, viewer=user)
    except (ValidationError, PermissionDenied, NotFoundError) as exc:
        _raise_http(exc)


@router.patch("/flags/{code}")
async def control_toggle_flag(
    code: str,
    body: FeatureFlagUpdateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await toggle_control_feature_flag(
            session,
            viewer=user,
            code=code,
            enabled=body.enabled,
        )
    except (ValidationError, PermissionDenied, NotFoundError) as exc:
        _raise_http(exc)
