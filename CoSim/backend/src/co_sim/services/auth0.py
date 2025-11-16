"""
Auth0 JWT verification for FastAPI.
Validates Auth0 JWT tokens and extracts user information.
"""
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from jose.backends.base import Key
from typing import Dict, Optional

from co_sim.core.auth0_config import Auth0Settings, get_auth0_settings

# HTTP Bearer token scheme
security = HTTPBearer()

# Cache for JWKS (JSON Web Key Set)
_jwks_cache: Optional[Dict[str, Key]] = None


async def get_jwks(settings: Auth0Settings) -> dict:
    """Fetch JWKS from Auth0."""
    global _jwks_cache
    
    if _jwks_cache is not None:
        return _jwks_cache
    
    async with httpx.AsyncClient() as client:
        response = await client.get(settings.jwks_url)
        response.raise_for_status()
        _jwks_cache = response.json()
        return _jwks_cache


async def verify_auth0_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    settings: Auth0Settings = Depends(get_auth0_settings),
) -> dict:
    """
    Verify Auth0 JWT token and return decoded payload.
    
    Args:
        credentials: HTTP Bearer token from request header
        settings: Auth0 configuration settings
    
    Returns:
        dict: Decoded JWT payload containing user information
    
    Raises:
        HTTPException: If token is invalid or verification fails
    """
    if not settings.is_configured:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth0 is not configured",
        )
    
    token = credentials.credentials
    audience = settings.default_audience

    if not audience:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth0 audience is not configured",
        )
    
    try:
        # Get the unverified header to find the key ID
        unverified_header = jwt.get_unverified_header(token)
        
        # Get JWKS from Auth0
        jwks = await get_jwks(settings)
        
        # Find the matching key
        rsa_key = {}
        for key in jwks["keys"]:
            if key["kid"] == unverified_header["kid"]:
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"],
                }
                break
        
        if not rsa_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to find appropriate key",
            )
        
        # Verify and decode the token
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=settings.algorithms_list,
            audience=audience,
            issuer=settings.issuer_url,
        )
        
        return payload
    
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_auth0(
    payload: dict = Depends(verify_auth0_token),
) -> dict:
    """
    Extract user information from verified Auth0 token.
    
    Args:
        payload: Decoded JWT payload from verify_auth0_token
    
    Returns:
        dict: User information from token
            - sub: User ID (Auth0 user identifier)
            - email: User's email address
            - name: User's full name (if available)
            - nickname: User's nickname (if available)
            - picture: User's profile picture URL (if available)
    """
    return {
        "sub": payload.get("sub"),
        "email": payload.get("email"),
        "name": payload.get("name"),
        "nickname": payload.get("nickname"),
        "picture": payload.get("picture"),
        "email_verified": payload.get("email_verified", False),
    }
