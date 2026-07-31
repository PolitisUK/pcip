import secrets

from fastapi import Form, HTTPException, Request

CSRF_SESSION_KEY = "_csrf_token"


def get_csrf_token(request: Request) -> str:
    token = request.session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token
    return token


def validate_csrf(request: Request, submitted: str | None) -> None:
    expected = request.session.get(CSRF_SESSION_KEY)

    if (
        not expected
        or not submitted
        or submitted != expected
    ):
        raise HTTPException(
            status_code=403,
            detail="Invalid CSRF token.",
        )


async def csrf_protect(
    request: Request,
    csrf_token: str = Form(...),
) -> None:
    validate_csrf(request, csrf_token)
