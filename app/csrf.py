from __future__ import annotations

import secrets
from typing import Any

from fastapi import HTTPException, Request


def get_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


async def csrf_protect(request: Request, form_data: object | None = None) -> None:
    expected = request.session.get("csrf_token")
    payload = form_data or await request.form()
    token = payload.get("csrf_token") if hasattr(payload, "get") else None
    if not expected:
        if token:
            raise HTTPException(status_code=403, detail="Invalid CSRF token.")
        raise HTTPException(status_code=422, detail="CSRF token missing")

    if not token or token != expected:
        if token:
            raise HTTPException(status_code=403, detail="Invalid CSRF token.")
        raise HTTPException(status_code=422, detail="CSRF token missing")


__all__ = ["get_csrf_token", "csrf_protect"]
