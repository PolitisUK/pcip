from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from itsdangerous import (
    BadSignature,
    SignatureExpired,
    URLSafeTimedSerializer,
)
from passlib.context import CryptContext

from .config import settings


pwd = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto",
)

serializer = URLSafeTimedSerializer(
    settings.secret_key,
    salt="pcip-session-v2",
)


@dataclass(frozen=True)
class SessionIdentity:
    user_id: int
    session_version: int


def hash_password(value: str) -> str:
    return pwd.hash(value)


def verify_password(value: str, hashed: str) -> bool:
    return pwd.verify(value, hashed)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def encode_session(
    user_id: int,
    session_version: int,
) -> str:
    return serializer.dumps(
        {
            "user_id": int(user_id),
            "session_version": int(session_version),
        }
    )


def decode_session(
    value: str,
    max_age: int | None = None,
) -> SessionIdentity | None:
    if not value:
        return None

    try:
        payload = serializer.loads(
            value,
            max_age=max_age or settings.session_max_age_seconds,
        )

        return SessionIdentity(
            user_id=int(payload["user_id"]),
            session_version=int(payload["session_version"]),
        )

    except (
        BadSignature,
        SignatureExpired,
        KeyError,
        TypeError,
        ValueError,
    ):
        return None