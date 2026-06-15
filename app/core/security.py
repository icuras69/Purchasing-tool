import hmac
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt import ExpiredSignatureError, InvalidTokenError
from pwdlib import PasswordHash

from app.core.config import settings


AUTH_ERROR = "Invalid or expired authentication credentials."
INVALID_LOGIN = "Invalid email or password."

password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


@dataclass(frozen=True)
class CurrentUser:
    email: str
    role: str = "admin"


class LoginRateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = monotonic()
        attempts = self._attempts[key]
        while attempts and now - attempts[0] > self.window_seconds:
            attempts.popleft()
        if len(attempts) >= self.max_attempts:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Try again later.",
            )

    def record_failure(self, key: str) -> None:
        self._attempts[key].append(monotonic())

    def clear(self, key: str) -> None:
        self._attempts.pop(key, None)


login_rate_limiter = LoginRateLimiter(
    settings.login_rate_limit_attempts,
    settings.login_rate_limit_window_seconds,
)


def verify_admin_credentials(email: str, password: str) -> bool:
    email_matches = hmac.compare_digest(
        email.strip().casefold(),
        settings.admin_email.strip().casefold(),
    )
    password_matches = False
    if settings.admin_password_hash:
        try:
            password_matches = password_hash.verify(password, settings.admin_password_hash)
        except Exception:
            password_matches = False
    return email_matches and password_matches


def create_access_token(email: str, role: str = "admin") -> tuple[str, int]:
    expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    expire = datetime.now(UTC) + expires_delta
    payload: dict[str, Any] = {
        "sub": email,
        "role": role,
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str) -> CurrentUser:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTH_ERROR) from exc
    except InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTH_ERROR) from exc

    subject = payload.get("sub")
    role = payload.get("role")
    if not isinstance(subject, str) or not hmac.compare_digest(
        subject.strip().casefold(),
        settings.admin_email.strip().casefold(),
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTH_ERROR)
    if role != "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AUTH_ERROR)
    return CurrentUser(email=settings.admin_email, role="admin")


def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    return decode_access_token(token)


def require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return current_user


def login_rate_limit_key(request: Request, email: str) -> str:
    client_host = request.client.host if request.client else "unknown"
    return f"{client_host}:{email.strip().casefold()}"
