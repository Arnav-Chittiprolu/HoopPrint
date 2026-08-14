import ssl
from dataclasses import dataclass
from functools import lru_cache

import certifi
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import (
    InvalidTokenError,
    PyJWKClient,
    PyJWKClientConnectionError,
    decode as jwt_decode,
)

from app.config import Settings, get_settings

security = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None = None


@lru_cache
def _jwks_client(supabase_url: str) -> PyJWKClient:
    jwks_url = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    return PyJWKClient(jwks_url, cache_keys=True, ssl_context=ssl_context)


def _decode_with_jwks(token: str, settings: Settings) -> dict:
    supabase_url = settings.supabase_url.rstrip("/")
    issuer = f"{supabase_url}/auth/v1"
    signing_key = _jwks_client(supabase_url).get_signing_key_from_jwt(token)
    try:
        return jwt_decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            issuer=issuer,
        )
    except InvalidTokenError:
        return jwt_decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            options={"verify_iss": False},
        )


def _decode_with_secret(token: str, settings: Settings) -> dict:
    return jwt_decode(
        token,
        settings.supabase_jwt_secret,
        algorithms=["HS256"],
        audience="authenticated",
    )


def _verify_with_supabase_auth(token: str, settings: Settings) -> dict:
    """Fallback: ask Supabase Auth to validate the user JWT."""
    apikey = settings.supabase_anon_key or settings.supabase_service_role_key
    if not apikey:
        raise InvalidTokenError("Supabase anon key is not configured")

    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/user"
    headers = {
        "apikey": apikey,
        "Authorization": f"Bearer {token}",
    }
    with httpx.Client(timeout=15.0, verify=certifi.where()) as client:
        response = client.get(url, headers=headers)
    if response.status_code != 200:
        raise InvalidTokenError(f"Supabase rejected token ({response.status_code})")
    user = response.json()
    return {"sub": user["id"], "email": user.get("email")}


def _decode_supabase_jwt(token: str, settings: Settings) -> dict:
    if not settings.supabase_url:
        raise InvalidTokenError("Supabase URL is not configured")

    errors: list[Exception] = []

    # Fast path: Supabase Auth validates the session (works for ES256 user tokens)
    if settings.supabase_anon_key or settings.supabase_service_role_key:
        try:
            return _verify_with_supabase_auth(token, settings)
        except (InvalidTokenError, httpx.HTTPError) as exc:
            errors.append(exc)

    try:
        return _decode_with_jwks(token, settings)
    except (InvalidTokenError, PyJWKClientConnectionError) as exc:
        errors.append(exc)

    if settings.supabase_jwt_secret:
        try:
            return _decode_with_secret(token, settings)
        except InvalidTokenError as exc:
            errors.append(exc)

    raise InvalidTokenError("JWT verification failed") from (errors[-1] if errors else None)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        payload = _decode_supabase_jwt(token, settings)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token — try signing out and back in",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user_id = payload.get("sub")
    if not user_id or not isinstance(user_id, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject",
        )

    email = payload.get("email")
    return CurrentUser(id=user_id, email=email if isinstance(email, str) else None)
