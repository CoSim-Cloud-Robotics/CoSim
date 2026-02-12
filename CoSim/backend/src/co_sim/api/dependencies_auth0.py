"""
Unified authentication dependency that supports both Auth0 and legacy JWT tokens.
"""
from __future__ import annotations

from co_sim.typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from co_sim.core.auth0_config import get_auth0_settings
from co_sim.db.session import get_db
from co_sim.models.user import User
from co_sim.services.auth0 import verify_auth0_token
from co_sim.services.token import decode_token

# Support both Bearer token schemes
security = HTTPBearer(auto_error=False)


async def get_or_create_user_from_auth0(
    session: AsyncSession,
    auth0_payload: dict,
) -> User:
    """
    Get or create a user from Auth0 payload.
    
    Auth0 'sub' format: 'auth0|xxxxx', 'google-oauth2|xxxxx', 'github|xxxxx', etc.
    """
    auth0_sub = auth0_payload.get("sub")
    email = auth0_payload.get("email")
    
    if not auth0_sub or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Auth0 token: missing sub or email",
        )
    
    # Try to find user by Auth0 sub (stored in external_id)
    result = await session.execute(
        select(User).where(User.external_id == auth0_sub)
    )
    user = result.scalar_one_or_none()
    
    # If not found, try by email
    if not user:
        result = await session.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()
        
        # If found by email, update external_id
        if user:
            user.external_id = auth0_sub
            await session.commit()
            await session.refresh(user)
    
    # Create new user if not found
    if not user:
        user = User(
            email=email,
            full_name=auth0_payload.get("name") or auth0_payload.get("nickname"),
            external_id=auth0_sub,
            is_active=True,
            email_verified=auth0_payload.get("email_verified", False),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    
    return user


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    authorization: Annotated[str | None, Header()] = None,
    session: Annotated[AsyncSession, Depends(get_db)] = None,
) -> User:
    """
    Unified dependency that supports both Auth0 and legacy JWT tokens.
    
    - If Auth0 is configured, attempts Auth0 verification first
    - Falls back to legacy JWT verification if Auth0 fails or is not configured
    - Automatically creates users from Auth0 tokens
    """
    settings = get_auth0_settings()
    
    # Extract token from credentials or header
    token = None
    if credentials:
        token = credentials.credentials
    elif authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Try Auth0 verification first if configured
    if settings.is_configured:
        try:
            auth0_payload = await verify_auth0_token(
                HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
                settings,
            )
            # Get or create user from Auth0 data
            user = await get_or_create_user_from_auth0(session, auth0_payload)
            
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User account is disabled",
                )
            
            return user
        except HTTPException as e:
            # Only raise if this is a non-authentication error (e.g., misconfiguration)
            if e.status_code not in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN):
                raise
            # Otherwise fall through to legacy verification
    
    # Legacy JWT verification (fallback)
    try:
        payload = decode_token(token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        ) from exc
    
    subject = payload.get("sub")
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    
    try:
        user_id = UUID(subject)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        ) from exc
    
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )
    
    return user
