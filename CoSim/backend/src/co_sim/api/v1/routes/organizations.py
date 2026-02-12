from __future__ import annotations

from typing import List

from co_sim.typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from co_sim.api.dependencies import get_current_user
from co_sim.db.session import get_db
from co_sim.models.user import User
from co_sim.schemas.organization import OrganizationCreate, OrganizationRead, OrganizationUpdate
from co_sim.services import organizations as org_service

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreate,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationRead:
    return await org_service.create_organization(session, payload)


@router.get("", response_model=List[OrganizationRead])
async def list_organizations(
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[OrganizationRead]:
    return await org_service.list_organizations(session)


@router.get("/{organization_id}", response_model=OrganizationRead)
async def get_organization_detail(
    organization_id: UUID,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationRead:
    organization = await org_service.get_organization(session, organization_id)
    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return OrganizationRead.model_validate(organization)


@router.patch("/{organization_id}", response_model=OrganizationRead)
async def update_organization(
    organization_id: UUID,
    payload: OrganizationUpdate,
    _: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationRead:
    organization = await org_service.get_organization(session, organization_id)
    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return await org_service.update_organization(session, organization, payload)
