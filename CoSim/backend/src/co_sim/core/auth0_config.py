"""
Auth0 configuration and utilities for backend authentication.
"""
from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Auth0Settings(BaseSettings):
    """Auth0 configuration settings."""
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
    # Auth0 domain (e.g., dev-abc123.us.auth0.com)
    auth0_domain: str = ""
    
    # Auth0 API audience/identifier (optional)
    auth0_audience: Optional[str] = None
    
    # JWT signing algorithms (RS256 for Auth0)
    auth0_algorithms: str = "RS256"
    
    # Auth0 issuer URL
    auth0_issuer: Optional[str] = None
    
    # Auth0 Management API credentials (optional, for user management)
    auth0_client_id: Optional[str] = None
    auth0_client_secret: Optional[str] = None
    
    @property
    def issuer_url(self) -> str:
        """Get the issuer URL."""
        if self.auth0_issuer:
            return self.auth0_issuer
        return f"https://{self.auth0_domain}/"
    
    @property
    def jwks_url(self) -> str:
        """Get the JWKS URL for verifying JWT signatures."""
        return f"https://{self.auth0_domain}/.well-known/jwks.json"
    
    @property
    def algorithms_list(self) -> List[str]:
        """Get list of allowed algorithms."""
        return [alg.strip() for alg in self.auth0_algorithms.split(",")]
    
    @property
    def is_configured(self) -> bool:
        """Check if Auth0 is properly configured."""
        return bool(self.auth0_domain)

    @property
    def default_audience(self) -> Optional[str]:
        """Return the configured audience or default userinfo audience."""
        if not self.auth0_domain:
            return None
        if self.auth0_audience:
            return self.auth0_audience
        if self.auth0_client_id:
            return self.auth0_client_id
        return f"https://{self.auth0_domain}/userinfo"


@lru_cache
def get_auth0_settings() -> Auth0Settings:
    """Get cached Auth0 settings."""
    return Auth0Settings()
