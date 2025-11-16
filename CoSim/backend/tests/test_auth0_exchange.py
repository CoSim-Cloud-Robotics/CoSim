from __future__ import annotations

import os
from pathlib import Path
import atexit

DB_PATH = Path(__file__).resolve().parent / "auth0_test.db"
if DB_PATH.exists():
    DB_PATH.unlink()

os.environ["COSIM_DATABASE_URI"] = f"sqlite+aiosqlite:///{DB_PATH}"
os.environ["COSIM_SYNC_DRIVER"] = "pysqlite"

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, delete, select  # type: ignore[import]
from sqlalchemy.orm import Session  # type: ignore[import]
import uuid

from co_sim.agents.auth.main import create_app  # type: ignore[import]
import co_sim.core.config as config  # type: ignore[import]
from co_sim.core.config import get_settings  # type: ignore[import]
from co_sim.core import redis as redis_helpers  # type: ignore[import]
import co_sim.api.v1.routes.auth as auth_routes  # type: ignore[import]
import co_sim.db.session as db_session  # type: ignore[import]
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker  # type: ignore[import]
from co_sim.models.user import User  # type: ignore[import]
from co_sim.services.auth0 import get_current_user_auth0  # type: ignore[import]
from co_sim.services import refresh_tokens as refresh_tokens_service  # type: ignore[import]


pytestmark = pytest.mark.asyncio(loop_scope="module")

get_settings.cache_clear()
settings = get_settings()
config.settings = settings
auth_routes.settings = settings

# Reinitialize async SQLAlchemy session to use the overridden database URI
try:
    db_session.engine.sync_engine.dispose(close=False)
except Exception:
    pass
db_session.engine = create_async_engine(settings.database_uri, echo=settings.debug, future=True)
db_session.async_session = async_sessionmaker(
    bind=db_session.engine,
    autoflush=False,
    expire_on_commit=False,
)


@atexit.register
def _cleanup_db_file() -> None:
    try:
        if DB_PATH.exists():
            DB_PATH.unlink()
    except OSError:
        pass


SYNC_ENGINE = create_engine(settings.sync_database_uri, future=True)
User.__table__.create(bind=SYNC_ENGINE, checkfirst=True)


@pytest.fixture(autouse=True)
def _mock_refresh_and_redis(monkeypatch):
    store: dict[str, uuid.UUID] = {}

    async def issue_refresh_token(user_id: uuid.UUID) -> str:
        token = f"refresh-{uuid.uuid4()}"
        store[token] = user_id
        return token

    async def rotate_refresh_token(old_token: str | None, user_id: uuid.UUID) -> str:
        if old_token:
            store.pop(old_token, None)
        return await issue_refresh_token(user_id)

    async def validate_refresh_token(token: str) -> uuid.UUID | None:
        return store.get(token)

    async def revoke_refresh_token(token: str | None) -> None:
        if token:
            store.pop(token, None)

    monkeypatch.setattr(refresh_tokens_service, "issue_refresh_token", issue_refresh_token)
    monkeypatch.setattr(refresh_tokens_service, "rotate_refresh_token", rotate_refresh_token)
    monkeypatch.setattr(refresh_tokens_service, "validate_refresh_token", validate_refresh_token)
    monkeypatch.setattr(refresh_tokens_service, "revoke_refresh_token", revoke_refresh_token)
    monkeypatch.setattr(auth_routes, "issue_refresh_token", issue_refresh_token)
    monkeypatch.setattr(auth_routes, "rotate_refresh_token", rotate_refresh_token)
    monkeypatch.setattr(auth_routes, "validate_refresh_token", validate_refresh_token)

    class DummyRedis:
        async def ping(self):
            return True

        async def close(self):
            return None

    dummy = DummyRedis()

    async def fake_init(force: bool = False):
        return dummy

    async def fake_get_redis():
        return dummy

    async def fake_close():
        return None

    monkeypatch.setattr(redis_helpers, "init_redis", fake_init)
    monkeypatch.setattr(redis_helpers, "get_redis", fake_get_redis)
    monkeypatch.setattr(redis_helpers, "close_redis", fake_close)


def cleanup_user(email: str) -> None:
    with Session(SYNC_ENGINE) as session:
        session.execute(delete(User).where(User.email == email))
        session.commit()


def get_user(email: str) -> User | None:
    with Session(SYNC_ENGINE) as session:
        result = session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()


def seed_user(**kwargs) -> User:
    user = User(**kwargs)
    with Session(SYNC_ENGINE) as session:
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


@pytest.mark.asyncio
async def test_exchange_auth0_token_creates_or_updates_user() -> None:
    app = create_app()

    async def override_get_current_user_auth0() -> dict[str, str | bool]:
        return {
            "sub": "auth0|test-user",
            "email": "auth0_test@example.com",
            "name": "Auth0 Test",
            "nickname": "Auth0",
            "email_verified": True,
        }

    app.dependency_overrides[get_current_user_auth0] = override_get_current_user_auth0

    try:
        # Ensure a clean slate for this email before running the test
        cleanup_user("auth0_test@example.com")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response_first = await client.post("/v1/auth/auth0/exchange")
            response_second = await client.post("/v1/auth/auth0/exchange")

        assert response_first.status_code == 200
        assert response_second.status_code == 200

        payload = response_first.json()
        assert "access_token" in payload and payload["access_token"]
        assert payload["expires_in"] > 0

        user = get_user("auth0_test@example.com")
        assert user is not None
        assert user.external_id == "auth0|test-user"
        assert user.email_verified is True
        assert user.full_name == "Auth0 Test"
        assert user.hashed_password is None

        # Clean up created user for isolation
        cleanup_user("auth0_test@example.com")
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_exchange_auth0_token_updates_existing_user() -> None:
    app = create_app()

    async def override_get_current_user_auth0() -> dict[str, str | bool]:
        return {
            "sub": "auth0|existing-user",
            "email": "auth0_existing@example.com",
            "name": "Updated Name",
            "nickname": "Updated",
            "email_verified": True,
        }

    app.dependency_overrides[get_current_user_auth0] = override_get_current_user_auth0

    try:
        # Seed an existing user without external_id to verify update path
        cleanup_user("auth0_existing@example.com")
        seed_user(
            email="auth0_existing@example.com",
            full_name="Old Name",
            email_verified=False,
            hashed_password="",
            plan="free",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post("/v1/auth/auth0/exchange")

        assert response.status_code == 200

        user = get_user("auth0_existing@example.com")
        assert user is not None
        assert user.external_id == "auth0|existing-user"
        assert user.full_name == "Updated Name"
        assert user.email_verified is True
        assert user.hashed_password is None

        # Clean up seeded user
        cleanup_user("auth0_existing@example.com")
    finally:
        app.dependency_overrides.clear()
