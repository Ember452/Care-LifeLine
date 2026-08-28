from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from care_lifeline.api.security import (
    ROLE_PATIENT,
    VALID_ROLES,
    CurrentUser,
    create_access_token,
    get_current_user,
)
from care_lifeline.db import session_store

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class TokenResponse(BaseModel):
    """登录/注册成功后的凭证响应（契约 §7.1）。"""

    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    role: str = ROLE_PATIENT


class MeResponse(BaseModel):
    id: int
    username: str
    role: str


def _issue_token(user) -> TokenResponse:
    token = create_access_token(
        f"user:{user.id}",
        expires_minutes=None,
        role=user.role or ROLE_PATIENT,
        username=user.username,
    )
    return TokenResponse(access_token=token, username=user.username, role=user.role or ROLE_PATIENT)


def _verify(username: str, password: str) -> TokenResponse:
    user = session_store.verify_user(username, password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials", "message": "用户名或密码错误"},
        )
    return _issue_token(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    username: Annotated[str | None, Form()] = None,
    password: Annotated[str | None, Form()] = None,
) -> TokenResponse:
    """登录：同时接受 OAuth2 form 与 JSON body（契约 §7.1 / P2-22）。

    form 优先（保持 OAuth2PasswordBearer 兼容）；无 form 字段时按 JSON 解析。
    """
    if username is None or password is None:
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "invalid_request", "message": "请提供 username 与 password"},
            ) from None
        username = payload.get("username")
        password = payload.get("password")
    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_request", "message": "请提供 username 与 password"},
        )
    return _verify(username, password)


@router.post("/register", response_model=TokenResponse)
def register(body: RegisterRequest) -> TokenResponse:
    """注册新用户并直接签发 token；角色默认 patient。"""
    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_request",
                "message": f"role 必须为 {VALID_ROLES} 之一",
                "detail": {"valid_roles": list(VALID_ROLES)},
            },
        )
    try:
        user = session_store.create_user(body.username, body.password, role=body.role)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "conflict", "message": "用户名已存在"},
        ) from None
    return _issue_token(user)


@router.get("/me", response_model=MeResponse)
def me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> MeResponse:
    """返回当前登录用户信息。"""
    return MeResponse(id=user.user_id, username=user.username, role=user.role)
