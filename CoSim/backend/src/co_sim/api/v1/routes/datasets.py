from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from co_sim.api.dependencies import get_current_user
from co_sim.db.session import get_db
from co_sim.models.user import User
from co_sim.schemas.dataset import DatasetCreate, DatasetRead, DatasetUpdate
from co_sim.services import datasets as dataset_service
from co_sim.typing import Annotated

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post("", response_model=DatasetRead, status_code=status.HTTP_201_CREATED)
async def create_dataset(
    payload: DatasetCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DatasetRead:
    _ = current_user
    return await dataset_service.create_dataset(session, payload)


@router.get("", response_model=List[DatasetRead])
async def list_datasets(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    organization_id: UUID | None = Query(default=None),
) -> list[DatasetRead]:
    _ = current_user
    return await dataset_service.list_datasets(session, organization_id=organization_id)


@router.get("/{dataset_id}", response_model=DatasetRead)
async def get_dataset(
    dataset_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DatasetRead:
    _ = current_user
    dataset = await dataset_service.get_dataset(session, dataset_id)
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    return DatasetRead.model_validate(dataset)


@router.patch("/{dataset_id}", response_model=DatasetRead)
async def update_dataset(
    dataset_id: UUID,
    payload: DatasetUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DatasetRead:
    _ = current_user
    dataset = await dataset_service.get_dataset(session, dataset_id)
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    return await dataset_service.update_dataset(session, dataset, payload)


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataset(
    dataset_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    _ = current_user
    await dataset_service.delete_dataset(session, dataset_id)
