from __future__ import annotations

from copy import deepcopy
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from co_sim.api.dependencies import get_current_user
from co_sim.db.session import get_db
from co_sim.models.project import Project
from co_sim.models.session import Session, SessionParticipant, SessionStatus
from co_sim.models.user import User
from co_sim.schemas.user import (
    UserActivityStats,
    UserPreferences,
    UserPreferencesUpdate,
    UserProfileResponse,
    UserProfileUpdate,
)


router = APIRouter(prefix="/users", tags=["users"])

DEFAULT_PREFERENCES_DICT = UserPreferences().model_dump()


def _deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(dict(base[key]), value)
        else:
            base[key] = value
    return base


def _resolved_preferences(user: User) -> dict[str, Any]:
    current = deepcopy(DEFAULT_PREFERENCES_DICT)
    if user.preferences:
        current = _deep_merge(current, user.preferences)
    return current


async def _compute_activity_stats(session: AsyncSession, user_id) -> UserActivityStats:
    projects_result = await session.execute(
        select(func.count(Project.id)).where(Project.created_by_id == user_id)
    )
    projects_created = int(projects_result.scalar() or 0)

    active_sessions_result = await session.execute(
        select(func.count(func.distinct(Session.id)))
        .join(SessionParticipant, SessionParticipant.session_id == Session.id)
        .where(
            SessionParticipant.user_id == user_id,
            Session.status == SessionStatus.RUNNING,
        )
    )
    active_sessions = int(active_sessions_result.scalar() or 0)

    duration_seconds_result = await session.execute(
        select(
            func.coalesce(
                func.sum(
                    func.extract(
                        'epoch',
                        func.coalesce(Session.ended_at, func.now()) - func.coalesce(Session.started_at, func.now()),
                    )
                ),
                0.0,
            )
        )
        .join(SessionParticipant, SessionParticipant.session_id == Session.id)
        .where(SessionParticipant.user_id == user_id, Session.started_at.is_not(None))
    )
    total_seconds = float(duration_seconds_result.scalar() or 0.0)
    compute_hours = round(total_seconds / 3600.0, 2)

    return UserActivityStats(
        projects_created=projects_created,
        active_sessions=active_sessions,
        compute_hours=compute_hours,
    )


async def _build_profile_response(session: AsyncSession, user: User) -> UserProfileResponse:
    preferences = _resolved_preferences(user)
    stats = await _compute_activity_stats(session, user.id)

    payload = {
        "id": user.id,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "email": user.email,
        "full_name": user.full_name,
        "display_name": user.display_name,
        "bio": user.bio,
        "plan": user.plan,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "preferences": preferences,
    }

    return UserProfileResponse(**payload, activity_stats=stats)


@router.get("/me", response_model=UserProfileResponse)
async def get_user_profile(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UserProfileResponse:
    return await _build_profile_response(session, current_user)


@router.patch("/me", response_model=UserProfileResponse)
async def update_user_profile(
    payload: UserProfileUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UserProfileResponse:
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        if field == "display_name":
            current_user.display_name = value
        elif field == "bio":
            current_user.bio = value
        elif field == "full_name":
            current_user.full_name = value

    if updates:
        await session.commit()
        await session.refresh(current_user)

    return await _build_profile_response(session, current_user)


@router.get("/me/settings", response_model=UserPreferences)
async def get_user_preferences(current_user: Annotated[User, Depends(get_current_user)]) -> UserPreferences:
    preferences = _resolved_preferences(current_user)
    return UserPreferences(**preferences)


@router.patch("/me/settings", response_model=UserPreferences)
async def update_user_preferences(
    payload: UserPreferencesUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UserPreferences:
    preferences = _resolved_preferences(current_user)
    updates = payload.model_dump(exclude_unset=True, exclude_none=True)
    if updates:
        preferences = _deep_merge(preferences, updates)
        current_user.preferences = preferences
        await session.commit()
        await session.refresh(current_user)
    return UserPreferences(**preferences)
