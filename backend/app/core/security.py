from __future__ import annotations

import datetime as dt
import uuid

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def _get_secret() -> str:
    secret = get_settings().jwt_secret_key
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY is required")
    return secret


def create_access_token(
    *,
    subject: str,
    expires_in_minutes: int,
) -> tuple[str, int]:
    now = dt.datetime.now(tz=dt.UTC)
    exp = now + dt.timedelta(minutes=expires_in_minutes)
    payload = {
        "sub": subject,
        "type": "access",
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }

    settings = get_settings()
    token = jwt.encode(
        payload,
        _get_secret(),
        algorithm=settings.jwt_algorithm,
    )
    return token, int((exp - now).total_seconds())


def create_refresh_token(
    *,
    subject: str,
    expires_in_days: int,
) -> tuple[str, str, dt.datetime]:
    now = dt.datetime.now(tz=dt.UTC)
    exp_dt = now + dt.timedelta(days=expires_in_days)
    jti = uuid.uuid4().hex
    payload = {
        "sub": subject,
        "type": "refresh",
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(exp_dt.timestamp()),
    }

    settings = get_settings()
    token = jwt.encode(
        payload,
        _get_secret(),
        algorithm=settings.jwt_algorithm,
    )
    return token, jti, exp_dt


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            _get_secret(),
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise ValueError("Invalid token") from exc
