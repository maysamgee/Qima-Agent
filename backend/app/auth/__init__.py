from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

bearer = HTTPBearer(auto_error=False)


@dataclass
class Actor:
    id: str
    name: str
    roles: set[str]


@lru_cache
def jwks_client():
    settings = get_settings()
    return jwt.PyJWKClient(
        f"https://cognito-idp.{settings.aws_region}.amazonaws.com/{settings.cognito_user_pool_id}/.well-known/jwks.json",
        cache_keys=True,
        lifespan=300,
        timeout=5,
    )


def current_actor(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Actor:
    settings = get_settings()
    if settings.auth_mode == "local" and settings.app_env in {"local", "test"}:
        return Actor("local-admin", "Local development user", {"ADMIN"})
    if not credentials:
        raise HTTPException(401, "Sign in required")
    try:
        token = credentials.credentials
        key = jwks_client().get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=f"https://cognito-idp.{settings.aws_region}.amazonaws.com/{settings.cognito_user_pool_id}",
            options={"verify_aud": False, "require": ["exp", "iat", "sub", "iss", "token_use", "client_id"]},
        )
        if claims["token_use"] != "access" or claims["client_id"] != settings.cognito_app_client_id:
            raise ValueError("Wrong token use/client")
        return Actor(
            claims["sub"],
            claims.get("username", claims["sub"]),
            set(claims.get("cognito:groups", [])) & {"ADMIN", "MARKETING", "SOURCING", "REVIEWER", "VIEWER"},
        )
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(401, "Invalid or expired authentication") from None


def authorize(actor: Actor, mode: str | None = None, *, review=False, admin=False):
    if "ADMIN" in actor.roles:
        return
    if admin or (review and "REVIEWER" not in actor.roles):
        raise HTTPException(403, "Your role cannot perform this action")
    if review and "REVIEWER" in actor.roles:
        return
    role = "MARKETING" if mode == "LEAD" else "SOURCING"
    if role not in actor.roles:
        raise HTTPException(403, "Your role cannot modify this business mode")


def reader(actor: Actor = Depends(current_actor)):
    if not actor.roles:
        raise HTTPException(403, "No platform role assigned")
    return actor
