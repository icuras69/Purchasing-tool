from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.security import (
    CurrentUser,
    INVALID_LOGIN,
    create_access_token,
    get_current_user,
    login_rate_limit_key,
    login_rate_limiter,
    verify_admin_credentials,
)
from app.schemas.auth import CurrentUserResponse, LoginRequest, TokenResponse


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, response: Response) -> TokenResponse:
    key = login_rate_limit_key(request, payload.email)
    login_rate_limiter.check(key)

    if not verify_admin_credentials(payload.email, payload.password):
        login_rate_limiter.record_failure(key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_LOGIN)

    login_rate_limiter.clear(key)
    token, expires_in = create_access_token(payload.email)
    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=CurrentUserResponse)
def me(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse(email=current_user.email, role=current_user.role)
