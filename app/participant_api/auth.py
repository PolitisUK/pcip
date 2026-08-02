from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PublicAuthSession
from app.security import new_token, token_hash

PARTICIPANT_API_SCOPE = "participant_api"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _unexpired(value: datetime | None) -> bool:
    return bool(value and value.replace(tzinfo=None) > _now().replace(tzinfo=None))


def create_participant_api_session(
    db: Session,
    *,
    participant_invitation_id: int,
    ttl_seconds: int,
) -> tuple[str, PublicAuthSession]:
    raw_token = new_token()
    row = PublicAuthSession(
        scope=PARTICIPANT_API_SCOPE,
        session_hash=token_hash(raw_token),
        participant_invitation_id=participant_invitation_id,
        expires_at=_now() + timedelta(seconds=ttl_seconds),
    )
    db.add(row)
    db.flush()
    return raw_token, row


def resolve_participant_api_session(
    db: Session,
    *,
    raw_token: str,
) -> PublicAuthSession | None:
    if not raw_token:
        return None
    row = db.scalar(
        select(PublicAuthSession).where(
            PublicAuthSession.scope == PARTICIPANT_API_SCOPE,
            PublicAuthSession.session_hash == token_hash(raw_token),
            PublicAuthSession.revoked_at.is_(None),
        )
    )
    if not row or not _unexpired(row.expires_at):
        return None
    return row
