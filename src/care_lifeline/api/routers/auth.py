from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from care_lifeline.api.security import create_access_token
from care_lifeline.db import session_store


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    user = session_store.verify_user(form.username, form.password)
    if user is None:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials", "message": "用户名或密码错误"},
        )
    token = create_access_token(f"user:{user.id}", expires_minutes=None)
    return TokenResponse(access_token=token, username=user.username)
