from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict



class ServiceEndpointSettings(BaseModel):
    auth_base_url: str = Field(
        default="http://auth-agent:8001",
        description="Base URL for the Auth agent service.",
    )
    project_base_url: str = Field(
        default="http://project-agent:8002",
        description="Base URL for the Project/Workspace agent service.",
    )
    session_base_url: str = Field(
        default="http://session-orchestrator:8003",
        description="Base URL for the Session Orchestrator service.",
    )
    collab_base_url: str = Field(
        default="http://collab-agent:8004",
        description="Base URL for the collaboration service.",
    )
    simulation_base_url: str = Field(
        default="http://simulation-agent:8005",
        description="Base URL for the Simulation agent service.",
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env",), env_nested_delimiter="__", env_prefix="COSIM_", extra="ignore")

    environment: str = Field(default="development")
    debug: bool = Field(default=True)

    database_uri: str = Field(
        default="postgresql+asyncpg://cosim:cosim@localhost:5432/cosim", description="Async SQLAlchemy URI"
    )
    sync_driver: str = Field(default="psycopg")

    alembic_database_uri: str | None = Field(default=None)

    jwt_secret_key: str = Field(default="changemechangemechangemechangeme", min_length=32)
    jwt_algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=30)
    refresh_token_expire_minutes: int = Field(default=60 * 24 * 7)

    redis_url: str = Field(default="redis://localhost:6379/0")

    workspace_root: str = Field(default="/tmp/cosim/workspaces")
    workspace_fs_enabled: bool = Field(default=True)

    webrtc_signaling_url: str = Field(default="ws://localhost:3000")
    webrtc_enabled: bool = Field(default=True)

    rate_limit_per_minute: int = Field(default=120)
    api_cache_ttl_seconds: int = Field(default=5)
    login_max_attempts: int = Field(default=5)
    login_throttle_window_seconds: int = Field(default=5 * 60)
    verification_code_ttl_seconds: int = Field(default=10 * 60)

    service_endpoints: ServiceEndpointSettings = Field(default_factory=ServiceEndpointSettings)

    nats_url: str = Field(default="nats://localhost:4222")
    nats_creds_file: str | None = Field(default=None)

    def model_dump_for_logging(self) -> Dict[str, Any]:
        data = self.model_dump()
        if "jwt_secret_key" in data:
            data["jwt_secret_key"] = "***"
        return data

    @property
    def sync_database_uri(self) -> str:
        if self.alembic_database_uri:
            return self.alembic_database_uri
        uri = self.database_uri
        if "+asyncpg" in uri:
            return uri.replace("+asyncpg", f"+{self.sync_driver}")
        if "+aiosqlite" in uri:
            return uri.replace("+aiosqlite", f"+{self.sync_driver}")
        return uri


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
