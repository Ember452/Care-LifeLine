from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

from care_lifeline.config import get_settings

# 角色枚举：与 db/models.User.role 保持一致的常量（单一事实来源在契约 §6）。
ROLE_ADMIN = "admin"
ROLE_CLINICIAN = "clinician"
ROLE_PATIENT = "patient"
VALID_ROLES: tuple[str, ...] = (ROLE_ADMIN, ROLE_CLINICIAN, ROLE_PATIENT)

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


def create_access_token(
    subject: str,
    expires_minutes: int | None = None,
    role: str = ROLE_PATIENT,
    username: str = "",
) -> str:
    """签发 JWT。

    Args:
        subject: 主体标识，形如 ``user:{id}``。
        expires_minutes: 过期分钟数；``None`` 时取配置默认值。
        role: 用户角色（admin/clinician/patient），随 token 携带供无状态鉴权。
        username: 用户名，随 token 携带供 ``/v1/auth/me`` 与审计留痕。

    Returns:
        HS256 签名后的 JWT 字符串。
    """
    settings = get_settings()
    expire = time.time() + (expires_minutes or settings.access_token_expire_minutes) * 60
    payload: dict[str, Any] = {"sub": subject, "exp": expire, "role": role, "username": username}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise _CREDENTIALS_ERROR from exc


class CurrentUser(BaseModel):
    """Authenticated principal（已解析的登录主体）。"""

    user_id: int
    username: str
    role: str = ROLE_PATIENT


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> CurrentUser:
    """解析 Bearer token 为当前登录用户。

    Raises:
        HTTPException: token 缺失/无效/主体格式非法时返回 401。
    """
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
    role = payload.get("role", ROLE_PATIENT)
    if role not in VALID_ROLES:
        role = ROLE_PATIENT
    return CurrentUser(user_id=user_id, username=username, role=role)


def require_roles(*roles: str):
    """依赖工厂：限定当前登录用户的角色。

    Args:
        roles: 允许的角色集合；空集合表示「仅需登录」。

    Returns:
        一个 FastAPI 依赖函数；角色不满足时抛 403（``{"code":"forbidden"}``）。
    """

    def _checker(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if roles and user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "forbidden", "message": "角色权限不足"},
            )
        return user

    return _checker
