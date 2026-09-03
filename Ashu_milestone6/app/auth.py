"""API security (M5 Step 6, upgraded to a required second layer in M6).

Layer 1 - required baseline: every endpoint is protected by a static API
key, read from the `API_KEY` environment variable and checked against the
`X-API-Key` request header via a FastAPI `Depends`. Missing/wrong key -> 401.

Layer 2 - required JWT (M6): `POST /auth/login` exchanges a hardcoded demo
user's credentials (env-configured, never in source) for a short-lived
signed token, and `require_jwt` verifies it on every business route
(`/research*`, `/approvals*`) *in addition to* the API key - both layers
must pass, neither replaces the other. Only `/`, `/health`, and
`POST /auth/login` itself skip the JWT check, since a client can't present
a token before it has one. M5 treated this as an optional stretch scoped
to one endpoint; M6's build guide requires it everywhere business logic is
reachable, so the same `require_jwt` dependency is now applied more widely
in `app/api.py` rather than rewritten. Crypto itself is `pyjwt`, not
hand-rolled.
"""
from __future__ import annotations

import hmac
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.security.api_key import APIKeyHeader

from app.config import get_settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer = HTTPBearer(auto_error=False)


def require_api_key(api_key: str | None = Depends(_api_key_header)) -> None:
    """Required baseline auth for every route. Rejects with 401 when the
    `X-API-Key` header is missing or doesn't match the server's configured
    key - including when no key is configured at all, so a forgotten
    `.env` fails closed instead of silently letting every request through."""
    settings = get_settings()
    if not settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Server misconfigured: API_KEY is not set.",
        )
    if not api_key or not hmac.compare_digest(api_key, settings.api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid X-API-Key.")


def issue_demo_token(username: str, password: str) -> str:
    """Optional JWT stretch: exchanges the hardcoded demo user's credentials
    for a signed, short-lived token."""
    settings = get_settings()
    if not settings.jwt_secret:
        raise HTTPException(status_code=500, detail="Server misconfigured: JWT_SECRET is not set.")
    valid = hmac.compare_digest(username, settings.demo_username) and hmac.compare_digest(
        password, settings.demo_password or ""
    )
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid demo credentials.")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expires_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def require_jwt(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str:
    """Required second auth layer (M6) for every business route. Verifies a
    Bearer token minted by `/auth/login`. Applied *in addition to*
    `require_api_key` (app-wide), never as a replacement for it."""
    settings = get_settings()
    if not settings.jwt_secret:
        raise HTTPException(status_code=500, detail="Server misconfigured: JWT_SECRET is not set.")
    if creds is None:
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    try:
        payload = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {exc}") from exc
    return payload["sub"]
