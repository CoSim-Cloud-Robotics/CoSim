from __future__ import annotations

from typing import Any, Optional
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from co_sim.schemas.base import TimestampedModel


PLAN_CHOICES = {"free", "student", "pro", "team", "enterprise"}


def _normalize_plan(value: str | None) -> str:
    if not value:
        return "free"
    plan = value.lower()
    if plan not in PLAN_CHOICES:
        return "free"
    return plan


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: Optional[str] = Field(default=None, max_length=120)
    plan: str = Field(default="free", max_length=50)

    @field_validator("plan", mode="before")
    @classmethod
    def validate_plan(cls, value: Any) -> str:
        return _normalize_plan(value if isinstance(value, str) else None)


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=120)
    password: Optional[str] = Field(default=None, min_length=8)
    is_active: Optional[bool] = None
    plan: Optional[str] = Field(default=None, max_length=50)

    @field_validator("plan", mode="before")
    @classmethod
    def validate_plan(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        return _normalize_plan(value)


class UserRead(TimestampedModel):
    email: EmailStr
    full_name: Optional[str]
    display_name: Optional[str]
    bio: Optional[str]
    plan: str
    is_active: bool
    is_superuser: bool
    preferences: 'UserPreferences'

    @field_validator("preferences", mode="before")
    @classmethod
    def _ensure_preferences(cls, value: Any) -> 'UserPreferences':
        if isinstance(value, UserPreferences):
            return value
        if not value:
            return UserPreferences()
        return UserPreferences(**value)


class NotificationPreferences(BaseModel):
    email_enabled: bool = True
    project_updates: bool = True
    session_alerts: bool = True
    billing_alerts: bool = True


class AppearancePreferences(BaseModel):
    theme: Literal['light', 'dark', 'auto'] = 'auto'
    editor_font_size: int = Field(default=14, ge=10, le=32)


class PrivacyPreferences(BaseModel):
    profile_visibility: Literal['public', 'private'] = 'private'
    show_activity: bool = False


class ResourcePreferences(BaseModel):
    auto_hibernate: bool = True
    hibernate_minutes: int = Field(default=5, ge=1, le=120)


class UserPreferences(BaseModel):
    notifications: NotificationPreferences = Field(default_factory=NotificationPreferences)
    appearance: AppearancePreferences = Field(default_factory=AppearancePreferences)
    privacy: PrivacyPreferences = Field(default_factory=PrivacyPreferences)
    resources: ResourcePreferences = Field(default_factory=ResourcePreferences)


class NotificationPreferencesUpdate(BaseModel):
    email_enabled: Optional[bool] = None
    project_updates: Optional[bool] = None
    session_alerts: Optional[bool] = None
    billing_alerts: Optional[bool] = None


class AppearancePreferencesUpdate(BaseModel):
    theme: Optional[Literal['light', 'dark', 'auto']] = None
    editor_font_size: Optional[int] = Field(default=None, ge=10, le=32)


class PrivacyPreferencesUpdate(BaseModel):
    profile_visibility: Optional[Literal['public', 'private']] = None
    show_activity: Optional[bool] = None


class ResourcePreferencesUpdate(BaseModel):
    auto_hibernate: Optional[bool] = None
    hibernate_minutes: Optional[int] = Field(default=None, ge=1, le=120)


class UserPreferencesUpdate(BaseModel):
    notifications: Optional[NotificationPreferencesUpdate] = None
    appearance: Optional[AppearancePreferencesUpdate] = None
    privacy: Optional[PrivacyPreferencesUpdate] = None
    resources: Optional[ResourcePreferencesUpdate] = None


class UserActivityStats(BaseModel):
    projects_created: int = 0
    active_sessions: int = 0
    compute_hours: float = 0.0


class UserProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=120)
    bio: Optional[str] = Field(default=None, max_length=2000)
    full_name: Optional[str] = Field(default=None, max_length=120)

    @field_validator("display_name", "bio", "full_name", mode="before")
    @classmethod
    def _normalize_optional_str(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return str(value).strip() or None


class UserProfileResponse(UserRead):
    activity_stats: UserActivityStats = Field(default_factory=UserActivityStats)


class UserInDB(UserRead):
    hashed_password: str


class TokenPayload(BaseModel):
    sub: UUID
    exp: int
    scopes: str | None = None


class AccessToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
