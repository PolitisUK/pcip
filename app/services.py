from datetime import datetime, timedelta, timezone
import smtplib
from email.message import EmailMessage
from sqlalchemy import delete
from sqlalchemy.orm import Session
from .config import settings
from .models import AuditEvent, OutboxEmail

def audit(db: Session, organisation_id: int, actor_user_id: int | None, action: str, entity_type: str, entity_id: str, detail: str = ""):
    db.add(AuditEvent(organisation_id=organisation_id, actor_user_id=actor_user_id, action=action, entity_type=entity_type, entity_id=str(entity_id), detail=detail))

def purge_expired_outbox(db: Session, *, at: datetime | None = None) -> int:
    """Remove expired operational email without relying on recipient matching."""
    result = db.execute(
        delete(OutboxEmail)
        .where(OutboxEmail.retention_expires_at <= (at or datetime.now(timezone.utc)))
        .execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0)


def queue_email(
    db: Session,
    organisation_id: int,
    recipient: str,
    subject: str,
    body: str,
    *,
    participant_id: int | None = None,
    study_id: int | None = None,
):
    retention_days = max(1, int(settings.outbox_email_retention_days))
    created_at = datetime.now(timezone.utc)
    row = OutboxEmail(
        organisation_id=organisation_id,
        participant_id=participant_id,
        study_id=study_id,
        recipient=recipient,
        subject=subject,
        body=body,
        created_at=created_at,
        retention_expires_at=created_at + timedelta(days=retention_days),
    )
    db.add(row); db.flush()
    if not settings.smtp_host:
        return row
    msg=EmailMessage(); msg['From']=settings.smtp_from_email; msg['To']=recipient; msg['Subject']=subject; msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_use_tls: smtp.starttls()
            if settings.smtp_username: smtp.login(settings.smtp_username, settings.smtp_password or "")
            smtp.send_message(msg)
        row.sent_at=datetime.now(timezone.utc)
    except Exception as exc:
        row.error=str(exc)
    return row
