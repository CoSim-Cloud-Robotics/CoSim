from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from co_sim.models.api_key import APIKey
from co_sim.models.user import User
from co_sim.schemas.user import UserCreate, UserRead
from co_sim.services.password import get_password_hash, verify_password
from co_sim.services.token import create_access_token


class UserAlreadyExistsError(Exception):
    pass


async def register_user(session: AsyncSession, payload: UserCreate) -> UserRead:
    hashed_password = get_password_hash(payload.password)
    user = User(
        email=payload.email.lower(),
        hashed_password=hashed_password,
        full_name=payload.full_name,
        plan=payload.plan,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:  # pragma: no cover
        await session.rollback()
        raise UserAlreadyExistsError from exc
    await session.refresh(user)
    return UserRead.model_validate(user)


async def authenticate_user(session: AsyncSession, email: str, password: str) -> tuple[User, str, int] | None:
    result = await session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password) or not user.is_active:
        return None
    token, expires_in = create_access_token(subject=user.id)
    return user, token, expires_in


async def create_api_key(session: AsyncSession, user: User, name: str, scopes: str = "*") -> APIKey:
    api_key = APIKey(user_id=user.id, name=name, key_hash=get_password_hash(name), scopes=scopes)
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)
    return api_key


async def get_user_by_id(session: AsyncSession, user_id: UUID) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()
