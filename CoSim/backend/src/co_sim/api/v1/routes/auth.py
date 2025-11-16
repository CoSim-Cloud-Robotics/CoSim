from __future__ import annotations

from co_sim.typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from co_sim.api.dependencies import get_current_user
from co_sim.db.session import get_db
from co_sim.models.user import User
from co_sim.schemas.auth import (
    RefreshTokenRequest,
    RefreshTokenResponse,
    TokenResponse,
    VerificationCodeConfirmRequest,
    VerificationCodeRequest,
)
from co_sim.schemas.user import UserCreate, UserRead
from co_sim.services import auth as auth_service
from co_sim.services.auth0 import get_current_user_auth0
from co_sim.services.login_throttle import LoginThrottledError, register_login_attempt, reset_login_attempts
from co_sim.services.refresh_tokens import issue_refresh_token, rotate_refresh_token, validate_refresh_token
from co_sim.services.token import create_access_token
from co_sim.services.verification_codes import generate_code, validate_code

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register_user(payload: UserCreate, session: Annotated[AsyncSession, Depends(get_db)]) -> UserRead:
    try:
        return await auth_service.register_user(session, payload)
    except auth_service.UserAlreadyExistsError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")


@router.post("/token", response_model=RefreshTokenResponse)
async def login_for_access_token(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RefreshTokenResponse:
    identifier = _login_identifier(request, form_data.username)
    try:
        await register_login_attempt(identifier)
    except LoginThrottledError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"message": "Too many login attempts", "retry_after": exc.retry_after},
        )

    user_data = await auth_service.authenticate_user(session, form_data.username, form_data.password)
    if not user_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect credentials")
    await reset_login_attempts(identifier)
    user, token, expires_in = user_data
    refresh_token = await issue_refresh_token(user.id)
    return RefreshTokenResponse(access_token=token, expires_in=expires_in, refresh_token=refresh_token)


@router.get("/me", response_model=UserRead)
async def read_current_user(current_user: Annotated[User, Depends(get_current_user)]) -> UserRead:
    return UserRead.model_validate(current_user)


@router.post("/auth0/exchange", response_model=RefreshTokenResponse)
async def exchange_auth0_token(
    auth0_user: Annotated[dict, Depends(get_current_user_auth0)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RefreshTokenResponse:
    """
    Exchange an Auth0 JWT for a CoSim backend JWT.
    Creates a new user in the database if one doesn't exist.
    """
    auth0_id = auth0_user.get("sub")
    email = auth0_user.get("email")
    email_verified = bool(auth0_user.get("email_verified", False))
    
    if not auth0_id or not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Auth0 token: missing sub or email",
        )
    
    # Look for existing user by Auth0 ID first, then fall back to email (backwards compatibility)
    user = None
    if auth0_id:
        result = await session.execute(select(User).where(User.external_id == auth0_id))
        user = result.scalar_one_or_none()

    if not user:
        result = await session.execute(select(User).where(User.email == email.lower()))
        user = result.scalar_one_or_none()
    
    # Create user if doesn't exist
    if not user:
        user = User(
            email=email.lower(),
            full_name=auth0_user.get("name") or auth0_user.get("nickname"),
            hashed_password=None,  # Auth0 users don't have passwords in our system
            external_id=auth0_id,
            email_verified=email_verified,
            is_active=True,
            plan="free",  # Default plan for new Auth0 users
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    else:
        updated = False
        if auth0_id and user.external_id != auth0_id:
            user.external_id = auth0_id
            updated = True
        normalized_email = email.lower()
        if normalized_email and user.email != normalized_email:
            user.email = normalized_email
            updated = True
        full_name = auth0_user.get("name") or auth0_user.get("nickname")
        if full_name and user.full_name != full_name:
            user.full_name = full_name
            updated = True
        if user.email_verified != email_verified:
            user.email_verified = email_verified
            updated = True
        if user.hashed_password not in (None, ""):
            user.hashed_password = None
            updated = True
        elif user.hashed_password == "":
            user.hashed_password = None
            updated = True

        if updated:
            await session.commit()
            await session.refresh(user)
    
    # Generate our backend JWT
    token, expires_in = create_access_token(subject=user.id)
    refresh_token = await issue_refresh_token(user.id)
    
    return RefreshTokenResponse(access_token=token, expires_in=expires_in, refresh_token=refresh_token)


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_tokens(
    payload: RefreshTokenRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RefreshTokenResponse:
    user_id = await validate_refresh_token(payload.refresh_token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = await auth_service.get_user_by_id(session, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    token, expires_in = create_access_token(subject=user.id)
    new_refresh = await rotate_refresh_token(payload.refresh_token, user.id)
    return RefreshTokenResponse(access_token=token, expires_in=expires_in, refresh_token=new_refresh)


@router.post("/verification/code")
async def request_verification_code(
    payload: VerificationCodeRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    user = await auth_service.get_user_by_email(session, payload.email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    code = await generate_code(payload.email)
    return {"message": "Verification code generated", "code": code}


@router.post("/verification/confirm")
async def confirm_verification_code(
    payload: VerificationCodeConfirmRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    user = await auth_service.get_user_by_email(session, payload.email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not await validate_code(payload.email, payload.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code")
    user.email_verified = True
    await session.commit()
    await session.refresh(user)
    return {"message": "Email verified"}


def _login_identifier(request: Request, username: str) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    elif request.client and request.client.host:
        client_ip = request.client.host
    else:  # pragma: no cover - fallback path
        client_ip = "unknown"
    return f"{username.lower()}:{client_ip}"
