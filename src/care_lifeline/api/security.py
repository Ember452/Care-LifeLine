from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

from care_lifeline.config import get_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login", auto_error=True)

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail={"code": "unauthorized", "message": "无效或过期的凭证"},
    headers={"WWW-Authenticate": "Bearer"},
)


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 100_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt = stored.split("$", 1)[0]
    return hmac.compare_digest(hash_password(password, salt), stored)


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    expire = time.time() + (expires_minutes or settings.access_token_expire_minutes) * 60
    payload: dict[str, Any] = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise _CREDENTIALS_ERROR from exc


class CurrentUser(BaseModel):
    """Lightweight authenticated principal."""

    user_id: int
    username: str


def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    payload = decode_access_token(token)
    sub = payload.get("sub")
    if not isinstance(sub, str) or ":" not in sub:
        raise _CREDENTIALS_ERROR
    kind, value = sub.split(":", 1)
    if kind != "user":
        raise _CREDENTIALS_ERROR
    try:
        user_id = int(value)
    except ValueError as exc:
        raise _CREDENTIALS_ERROR from exc
    username = payload.get("username", "")
    return CurrentUser(user_id=user_id, username=username)
