from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from co_sim.api.dependencies import get_current_user
from co_sim.db.session import get_db
from co_sim.models.user import User
from co_sim.schemas.secret import SecretCreate, SecretRead, SecretReveal, SecretRotate
from co_sim.services import secrets as secret_service
from co_sim.typing import Annotated

router = APIRouter(prefix="/secrets", tags=["secrets"])


@router.post("", response_model=SecretRead, status_code=status.HTTP_201_CREATED)
async def create_secret(
    payload: SecretCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SecretRead:
    _ = current_user
    return await secret_service.create_secret(session, payload)


@router.get("", response_model=List[SecretRead])
async def list_secrets(
    workspace_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[SecretRead]:
    _ = current_user
    return await secret_service.list_secrets(session, workspace_id)


@router.get("/{secret_id}", response_model=SecretReveal)
async def reveal_secret(
    secret_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SecretReveal:
    _ = current_user
    secret = await secret_service.reveal_secret(session, secret_id)
    if not secret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret not found")
    return secret


@router.delete("/{secret_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_secret(
    secret_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    _ = current_user
    await secret_service.delete_secret(session, secret_id)


@router.post("/{secret_id}/rotate", response_model=SecretRead)
async def rotate_secret(
    secret_id: UUID,
    payload: SecretRotate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SecretRead:
    _ = current_user
    existing = await secret_service.reveal_secret(session, secret_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret not found")
    await secret_service.delete_secret(session, secret_id)
    new_secret = await secret_service.create_secret(
        session,
        SecretCreate(workspace_id=existing.workspace_id, name=existing.name, value=payload.value),
    )
    return new_secret
