from datetime import datetime, timedelta, timezone
from pathlib import Path
from contextlib import asynccontextmanager
import re
import logging
import time
import csv, io, json, secrets
from collections import OrderedDict, deque
from threading import Lock
from .csrf import get_csrf_token, csrf_protect
from fastapi import FastAPI, Request, Form, Depends, HTTPException, UploadFile, File, Response, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select, func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .config import settings, validate_runtime_settings
from .db import Base, engine, get_db, SessionLocal
from .models import (
    Activity,
    ActivityResponse,
    AuditEvent,
    ConsentStatus,
    EvidenceFile,
    Invitation,
    Organisation,
    OrganisationMembership,
    OutboxEmail,
    Participant,
    ParticipantInvitation,
    ParticipantMessage,
    ParticipantStatus,
    PasswordReset,
    Project,
    ProjectStatus,
    PublicAuthSession,
    PublicTokenExchange,
    Role,
    Study,
    StudyAccess,
    StudyEnrolment,
    StudyStatus,
    User,
)
from .security import hash_password, verify_password, new_token, token_hash, encode_session, decode_session
from .services import audit, queue_email
from .storage import storage
from .scanner import scan_file
from .entra import oauth, configured as entra_configured
from .observability import configure_observability
from .participant_services import (
    activity_window,
    apply_response_action,
    build_evidence_file,
    create_participant_invitation,
    create_participant_message,
    create_researcher_message,
    find_live_unaccepted_invitation,
    grant_participant_consent,
    is_evidence_downloadable,
    list_participant_visible_messages,
    mark_invitation_revoked,
    resolve_org_scoped_evidence,
    resolve_invitation_by_token,
    resolve_or_create_activity_response,
    resolve_org_scoped_invitation,
    resolve_participant_invitation,
    serialise_response_payload,
)
from .participant_api.auth import (
    PARTICIPANT_API_SCOPE,
    create_participant_api_session,
    resolve_participant_api_session,
)
from .participant_api.schemas import (
    BearerSession,
    InvitationContext,
    LogoutResponse,
    Pagination,
    ParticipantSessionResponse,
    ParticipantSummary,
    SessionExchangeRequest,
    SessionExchangeResponse,
    SessionInfo,
    StudyListResponse,
    StudySummary,
)

VERSION = "0.6.0"
BASE = Path(__file__).resolve().parent
configure_observability(settings)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    startup()
    yield


app = FastAPI(
    title=settings.app_name,
    version=VERSION,
    lifespan=lifespan,
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="csrf_session",
    https_only=settings.session_cookie_secure,
    same_site="lax",
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=[x.strip() for x in settings.trusted_hosts.split(",") if x.strip()])

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        csp_nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = csp_nonce
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            allowed = {x.strip().rstrip("/") for x in settings.allowed_origins.split(",") if x.strip()}
            if origin and origin.rstrip("/") not in allowed:
                return HTMLResponse("Request origin is not permitted.", status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(self)"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data:; "
            "style-src 'self'; "
            f"script-src 'self' 'nonce-{csp_nonce}'; "
            "form-action 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'"
        )
        if settings.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

app.add_middleware(SecurityHeadersMiddleware)
templates = Jinja2Templates(directory=str(BASE / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


@app.get("/service-worker.js", include_in_schema=False)
def service_worker():
    return FileResponse(
        BASE / "static" / "service-worker.js",
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache",
            "Service-Worker-Allowed": "/",
        },
    )


logger = logging.getLogger("pcip.security")
PUBLIC_AUTH_COOKIE = "public_auth_session"
PUBLIC_SCOPE_PASSWORD_RESET = "password_reset"
PUBLIC_SCOPE_RESEARCHER_INVITE = "researcher_invitation"
PUBLIC_SCOPE_PARTICIPANT_PORTAL = "participant_portal"


def now(): return datetime.now(timezone.utc)
def naive_now(): return now().replace(tzinfo=None)
def unexpired(v): return bool(v and v.replace(tzinfo=None) > naive_now())



class InMemoryRateLimiter:
    def __init__(self, max_keys: int = 10_000):
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()
        self._max_keys = max(1, max_keys)
        self._lock = Lock()

    def reset(self):
        with self._lock:
            self._hits.clear()

    def check(self, key: str, limit: int, window_seconds: int) -> int | None:
        if limit <= 0:
            return 1
        with self._lock:
            now_seconds = time.monotonic()
            window_start = now_seconds - window_seconds
            if key not in self._hits and len(self._hits) >= self._max_keys:
                self._hits.popitem(last=False)
            bucket = self._hits.setdefault(key, deque())
            self._hits.move_to_end(key)
            while bucket and bucket[0] <= window_start:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(window_seconds - (now_seconds - bucket[0])) + 1)
                return retry_after
            bucket.append(now_seconds)
            return None


rate_limiter = InMemoryRateLimiter()


def _rate_limit_key(scope: str, label: str, value: str):
    return f"{scope}:{label}:{value}"


def _enforce_rate_limit(
    request: Request,
    db: Session,
    scope: str,
    ip_limit: int,
    account_key: str | None = None,
    account_limit: int | None = None,
    organisation_id: int | None = None,
    actor_user_id: int | None = None,
):
    if not settings.rate_limit_enabled:
        return
    ip = request.client.host if request.client and request.client.host else "unknown"
    retry = rate_limiter.check(_rate_limit_key(scope, "ip", ip), ip_limit, settings.rate_limit_window_seconds)
    account_retry = None
    if account_key and account_limit is not None:
        account_retry = rate_limiter.check(_rate_limit_key(scope, "account", account_key), account_limit, settings.rate_limit_window_seconds)

    retry_after = max(x for x in [retry, account_retry] if x is not None) if retry is not None or account_retry is not None else None
    if retry_after is None:
        return

    detail = f"scope={scope} ip={ip} retry_after={retry_after}"
    logger.warning("rate_limited %s", detail)
    if organisation_id is not None:
        audit(db, organisation_id, actor_user_id, "security.rate_limited", "security", scope, detail)
    db.commit()
    raise HTTPException(
        429,
        f"Too many requests. Please wait {retry_after} seconds and try again.",
        headers={"Retry-After": str(retry_after)},
    )


def hosted_environment(): return settings.environment.strip().lower() not in {"development","dev","test","testing"}


def configure_logging():
    level_name = (settings.log_level or "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
    else:
        root.setLevel(level)


def validate_startup_environment():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    if hosted_environment() and settings.startup_validate_migrations:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        script = ScriptDirectory.from_config(Config("alembic.ini"))
        expected_heads = {x.lower() for x in script.get_heads()}
        if not expected_heads:
            return

        with engine.connect() as connection:
            try:
                rows = connection.execute(text("SELECT version_num FROM alembic_version")).all()
            except Exception as exc:
                raise RuntimeError("Database migrations have not been applied; alembic_version is unavailable.") from exc
        current = {str(row[0]).lower() for row in rows if row and row[0]}
        if not expected_heads.issubset(current):
            raise RuntimeError(
                "Database migrations are not at head. "
                f"Expected: {', '.join(sorted(expected_heads))}. "
                f"Current: {', '.join(sorted(current)) or 'none'}."
            )


def normalise_scan_status(value: str | None) -> str:
    token = (value or "").strip().lower().replace(" ", "_")
    mapping = {
        "scan_failed": "failed",
        "not_scanned": "not_scanned",
    }
    return mapping.get(token, token)


def allow_unscanned_downloads() -> bool:
    return settings.environment.strip().lower() in {"development", "dev"} and settings.development_allow_unscanned_downloads


def ensure_clean_scan_for_download(scan_status: str | None):
    if is_evidence_downloadable(scan_status):
        return
    if allow_unscanned_downloads():
        return
    raise HTTPException(423, "Evidence is blocked until malware scanning is explicitly CLEAN.")


def delete_stored_object_safely(key: str, reason: str) -> None:
    try:
        storage.delete(key)
    except Exception as exc:
        logger.error(
            "evidence_cleanup_failed key=%s reason=%s error=%s",
            key,
            reason,
            exc.__class__.__name__,
        )


def log_webhook_rejection(request: Request, reason: str):
    client_host = request.client.host if request.client else "unknown"
    logger.warning(
        "webhook_rejected reason=%s ip=%s ua=%s",
        reason,
        client_host,
        request.headers.get("user-agent", ""),
    )


def enum_value(v, e, field):
    if v not in {x.value for x in e}: raise HTTPException(400, f"Invalid {field}.")
    return v


def nonblank(value: str, field: str, min_length: int = 1) -> str:
    cleaned = value.strip()
    if len(cleaned) < min_length:
        if min_length == 1:
            raise HTTPException(400, f"{field} is required.")
        raise HTTPException(400, f"{field} must be at least {min_length} characters long.")
    return cleaned


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
STUDY_METHODOLOGIES = {
    "diary",
    "walk_along",
    "interview",
    "focus_group",
    "co_design",
    "mixed_method",
}
ACTIVITY_TYPES = {
    "short_text",
    "long_text",
    "single_choice",
    "multiple_choice",
    "rating",
    "slider",
    "photo",
    "audio",
    "video",
    "gps",
    "ranking",
    "file",
}
COMMUNICATION_PREFERENCES = {"email", "sms", "phone", "none"}
MAX_CSV_IMPORT_BYTES = 2 * 1024 * 1024
MAX_CSV_IMPORT_ROWS = 10_000


def validated_email(value: str) -> str | None:
    cleaned = value.strip().lower()
    if not cleaned:
        return None
    if not EMAIL_RE.fullmatch(cleaned):
        raise HTTPException(400, "Please enter a valid email address.")
    return cleaned


def active_users_for_email(
    db: Session,
    email: str,
    limit: int = 2,
) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(
                User.email == email,
                User.is_active == True,
            )
            .limit(limit)
        ).all()
    )


def unique_active_user_for_email(
    db: Session,
    email: str,
) -> User | None:
    matches = active_users_for_email(db, email)
    return matches[0] if len(matches) == 1 else None


def entra_identity_from_claims(
    claims: dict,
) -> tuple[str, str, str] | None:
    subject = claims.get("sub") or claims.get("oid")
    email = (
        claims.get("preferred_username")
        or claims.get("email")
        or ""
    ).lower().strip()
    name = claims.get("name") or email
    tenant = claims.get("tid")
    if (
        not subject
        or not email
        or (
            settings.entra_tenant_id
            and tenant != settings.entra_tenant_id
        )
    ):
        return None
    return str(subject), email, str(name)


def bump_session_version(user: User):
    user.session_version = int(user.session_version or 0) + 1


class CurrentUser:
    """A global identity viewed through one active organisation membership."""

    def __init__(self, identity: User, membership: OrganisationMembership):
        self.identity = identity
        self.membership = membership

    @property
    def organisation_id(self):
        return self.membership.organisation_id

    @property
    def organisation(self):
        return self.membership.organisation

    @property
    def role(self):
        return self.membership.role

    @property
    def is_active(self):
        return self.identity.is_active and self.membership.is_active

    @property
    def available_memberships(self):
        return [
            membership
            for membership in self.identity.memberships
            if membership.is_active
        ]

    def __getattr__(self, name):
        return getattr(self.identity, name)


def add_organisation_membership(
    db: Session,
    user: User,
    organisation_id: int,
    role: str,
) -> OrganisationMembership:
    existing = db.scalar(
        select(OrganisationMembership).where(
            OrganisationMembership.user_id == user.id,
            OrganisationMembership.organisation_id == organisation_id,
        )
    )
    if existing:
        return existing
    membership = OrganisationMembership(
        user_id=user.id,
        organisation_id=organisation_id,
        role=role,
        is_active=True,
    )
    db.add(membership)
    return membership


def invalidate_session_cookie_user(request: Request, db: Session):
    identity = decode_session(request.cookies.get("session", ""))
    if not identity:
        return None
    user = db.get(User, identity.user_id)
    if not user:
        return None
    if user.session_version == identity.session_version:
        bump_session_version(user)
        db.commit()
        return user
    return None

def current_user(request: Request, db: Session = Depends(get_db)):
    identity = decode_session(request.cookies.get("session", ""))

    if not identity:
        raise HTTPException(303, headers={"Location": "/login"})

    u = db.get(User, identity.user_id)

    if not u or not u.is_active:
        raise HTTPException(303, headers={"Location": "/login"})

    if u.session_version != identity.session_version:
        raise HTTPException(303, headers={"Location": "/login"})

    organisation_id = identity.organisation_id or u.organisation_id
    membership = db.scalar(
        select(OrganisationMembership).where(
            OrganisationMembership.user_id == u.id,
            OrganisationMembership.organisation_id == organisation_id,
            OrganisationMembership.is_active == True,
        )
    )
    if membership:
        return CurrentUser(u, membership)

    # Compatibility only for local/test databases that have not run 0006.
    if (
        settings.environment in {"development", "test"}
        and organisation_id == u.organisation_id
    ):
        return u
    raise HTTPException(303, headers={"Location": "/login"})

def roles(*allowed):
    def dep(u=Depends(current_user)):
        if u.role not in allowed: raise HTTPException(403, "Insufficient permission")
        return u
    return dep


def set_flash(request: Request, level: str, message: str):
    request.session["flash"] = {"level": level, "message": message}


def consume_flash(request: Request) -> tuple[str | None, str | None]:
    payload = request.session.pop("flash", None)
    if not payload:
        return None, None
    level = str(payload.get("level", "")).strip().lower()
    message = str(payload.get("message", "")).strip()
    if not message:
        return None, None
    if level == "error":
        return None, message
    return message, None


def request_wants_html(request: Request) -> bool:
    if request.url.path.startswith("/api/"):
        return False
    accept = request.headers.get("accept", "").lower()
    return "text/html" in accept

def render(request, name, user=None, **ctx):
    flash_notice, flash_error = consume_flash(request)
    return templates.TemplateResponse(
        request=request,
        name=name,
        context={
            "user": user,
            "app_name": settings.app_name,
            "version": VERSION,
            "can_edit": bool(
                user and user.role in {"owner", "admin", "researcher"}
            ),
            "entra_enabled": entra_configured(),
            "local_login_enabled": settings.local_login_enabled,
            "csrf_token": get_csrf_token(request),
            "csp_nonce": getattr(request.state, "csp_nonce", ""),
            "flash_notice": flash_notice,
            "flash_error": flash_error,
            **ctx,
        },
    )


def render_error(request: Request, status_code: int, title: str, detail: str):
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={
            "app_name": settings.app_name,
            "version": VERSION,
            "entra_enabled": entra_configured(),
            "local_login_enabled": settings.local_login_enabled,
            "csrf_token": get_csrf_token(request),
            "csp_nonce": getattr(request.state, "csp_nonce", ""),
            "status_code": status_code,
            "error_title": title,
            "error_detail": detail,
        },
        status_code=status_code,
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    if not request_wants_html(request):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    return render_error(request, 404, "Page not found", "The page you requested is not available.")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code in {301, 302, 303, 307, 308} and exc.headers and exc.headers.get("Location"):
        return RedirectResponse(exc.headers["Location"], status_code=exc.status_code)

    detail = str(exc.detail) if exc.detail else "Request could not be completed."
    if request_wants_html(request):
        title_map = {
            400: "Check and try again",
            401: "Sign-in required",
            403: "You do not have access",
            404: "Page not found",
            409: "Request conflict",
            422: "Information required",
            429: "Too many requests",
        }
        title = title_map.get(exc.status_code, "Request failed")
        return render_error(request, exc.status_code, title, detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": detail}, headers=exc.headers or None)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    if request_wants_html(request):
        errors = exc.errors()
        if errors:
            first = errors[0]
            field = ".".join(str(x) for x in first.get("loc", [])[1:]) or "field"
            detail = f"Please review {field}: {first.get('msg', 'invalid value')}."
        else:
            detail = "Please review the submitted information and try again."
        return render_error(request, 422, "Please check your information", detail)
    errors = []
    for item in exc.errors():
        errors.append({k: v for k, v in item.items() if k != "input"})
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled_exception path=%s", request.url.path)
    if not request_wants_html(request):
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
    return render_error(request, 500, "Something went wrong", "An unexpected error occurred. Please try again.")

def project(db,i,o):
    r=db.scalar(select(Project).where(Project.id==i,Project.organisation_id==o))
    if not r: raise HTTPException(404)
    return r

def study(db,i,o):
    r=db.scalar(select(Study).where(Study.id==i,Study.organisation_id==o))
    if not r: raise HTTPException(404)
    return r

def participant(db,i,o):
    r=db.scalar(select(Participant).where(Participant.id==i,Participant.organisation_id==o))
    if not r: raise HTTPException(404)
    return r


def privacy_workflow_key(participant_id: int) -> str:
    return f"privacy_delete:{participant_id}"


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def participant_related_counts(db: Session, participant_id: int, organisation_id: int) -> dict[str, int]:
    row = db.execute(
        select(
            select(func.count(StudyEnrolment.id)).where(StudyEnrolment.organisation_id == organisation_id, StudyEnrolment.participant_id == participant_id).scalar_subquery().label("enrolments"),
            select(func.count(ActivityResponse.id)).where(ActivityResponse.organisation_id == organisation_id, ActivityResponse.participant_id == participant_id).scalar_subquery().label("responses"),
            select(func.count(ParticipantMessage.id)).where(ParticipantMessage.organisation_id == organisation_id, ParticipantMessage.participant_id == participant_id).scalar_subquery().label("messages"),
            select(func.count(ParticipantInvitation.id)).where(ParticipantInvitation.organisation_id == organisation_id, ParticipantInvitation.participant_id == participant_id).scalar_subquery().label("invitations"),
            select(func.count(EvidenceFile.id)).where(EvidenceFile.organisation_id == organisation_id, EvidenceFile.participant_id == participant_id).scalar_subquery().label("evidence"),
        )
    ).one()
    return {
        "enrolments": int(row.enrolments or 0),
        "responses": int(row.responses or 0),
        "messages": int(row.messages or 0),
        "invitations": int(row.invitations or 0),
        "evidence": int(row.evidence or 0),
    }


def participant_has_related_data(counts: dict[str, int]) -> bool:
    return any(value > 0 for value in counts.values())


def anonymise_participant_record(row: Participant):
    row.reference = f"ANON-{row.id}"
    row.name = f"Anonymised Participant {row.id}"
    row.email = None
    row.phone = None
    row.tags = ""
    row.demographics_json = "{}"
    row.notes = ""
    row.communication_preference = "none"
    row.status = ParticipantStatus.withdrawn.value
    row.consent_status = ConsentStatus.withdrawn.value


def participant_export_payload(db: Session, row: Participant):
    enrolments = db.scalars(select(StudyEnrolment).where(StudyEnrolment.organisation_id == row.organisation_id, StudyEnrolment.participant_id == row.id).order_by(StudyEnrolment.id.asc())).all()
    responses = db.scalars(select(ActivityResponse).where(ActivityResponse.organisation_id == row.organisation_id, ActivityResponse.participant_id == row.id).order_by(ActivityResponse.id.asc())).all()
    messages = db.scalars(select(ParticipantMessage).where(ParticipantMessage.organisation_id == row.organisation_id, ParticipantMessage.participant_id == row.id).order_by(ParticipantMessage.id.asc())).all()
    invitations = db.scalars(select(ParticipantInvitation).where(ParticipantInvitation.organisation_id == row.organisation_id, ParticipantInvitation.participant_id == row.id).order_by(ParticipantInvitation.id.asc())).all()
    evidence = db.scalars(select(EvidenceFile).where(EvidenceFile.organisation_id == row.organisation_id, EvidenceFile.participant_id == row.id).order_by(EvidenceFile.id.asc())).all()
    return {
        "application_name": "Citizen Centric",
        "branding": "Citizen Centric by Politis",
        "participant": {
            "id": row.id,
            "organisation_id": row.organisation_id,
            "reference": row.reference,
            "name": row.name,
            "email": row.email,
            "phone": row.phone,
            "status": row.status,
            "consent_status": row.consent_status,
            "communication_preference": row.communication_preference,
            "tags": row.tags,
            "demographics_json": row.demographics_json,
            "notes": row.notes,
            "created_by_id": row.created_by_id,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        },
        "study_enrolments": [
            {
                "id": x.id,
                "study_id": x.study_id,
                "status": x.status,
                "enrolled_at": _iso(x.enrolled_at),
            }
            for x in enrolments
        ],
        "activity_responses": [
            {
                "id": x.id,
                "study_id": x.study_id,
                "activity_id": x.activity_id,
                "status": x.status,
                "value_json": x.value_json,
                "submitted_at": _iso(x.submitted_at),
                "updated_at": _iso(x.updated_at),
            }
            for x in responses
        ],
        "participant_messages": [
            {
                "id": x.id,
                "study_id": x.study_id,
                "sender_type": x.sender_type,
                "sender_user_id": x.sender_user_id,
                "body": x.body,
                "internal_note": x.internal_note,
                "created_at": _iso(x.created_at),
            }
            for x in messages
        ],
        "participant_invitations": [
            {
                "id": x.id,
                "study_id": x.study_id,
                "expires_at": _iso(x.expires_at),
                "opened_at": _iso(x.opened_at),
                "accepted_at": _iso(x.accepted_at),
                "revoked_at": _iso(x.revoked_at),
                "created_at": _iso(x.created_at),
            }
            for x in invitations
        ],
        "evidence_files": [
            {
                "id": x.id,
                "study_id": x.study_id,
                "activity_id": x.activity_id,
                "response_id": x.response_id,
                "original_name": x.original_name,
                "content_type": x.content_type,
                "size_bytes": x.size_bytes,
                "sha256_hex": x.sha256_hex,
                "scan_status": x.scan_status,
                "storage_provider": x.storage_provider,
                "created_at": _iso(x.created_at),
            }
            for x in evidence
        ],
    }


def study_permission(db: Session, user: User, study_row: Study) -> str | None:
    if user.role in {"owner", "admin"}:
        return "manage"
    if study_row.created_by_id == user.id:
        return "edit"
    access = db.scalar(select(StudyAccess).where(StudyAccess.study_id == study_row.id, StudyAccess.user_id == user.id, StudyAccess.organisation_id == user.organisation_id))
    if access:
        return access.permission
    return "view" if user.role == "observer" else None


def require_study_permission(db: Session, user: User, study_row: Study, edit: bool = False):
    permission = study_permission(db, user, study_row)
    if not permission or (edit and permission not in {"edit", "manage"}):
        raise HTTPException(403, "You do not have access to this study.")
    return permission


def study_scope_for_user(user: User):
    access_ids = select(StudyAccess.study_id).where(
        StudyAccess.organisation_id == user.organisation_id,
        StudyAccess.user_id == user.id,
    )
    return select(Study.id).where(
        Study.organisation_id == user.organisation_id,
        or_(Study.created_by_id == user.id, Study.id.in_(access_ids)),
    )


def project_scope_for_user(user: User):
    accessible_studies = study_scope_for_user(user)
    accessible_project_ids = select(Study.project_id).where(
        Study.organisation_id == user.organisation_id,
        Study.id.in_(accessible_studies),
    )
    return select(Project.id).where(
        Project.organisation_id == user.organisation_id,
        or_(
            Project.created_by_id == user.id,
            Project.id.in_(accessible_project_ids),
        ),
    )


def project_permission(
    db: Session,
    user: User,
    project_row: Project,
) -> str | None:
    if user.role in {"owner", "admin"}:
        return "manage"
    if user.role == "observer":
        return "view"
    if project_row.created_by_id == user.id:
        return "manage"
    visible_project = db.scalar(
        project_scope_for_user(user).where(Project.id == project_row.id)
    )
    return "view" if visible_project else None


def require_project_permission(
    db: Session,
    user: User,
    project_row: Project,
    edit: bool = False,
):
    permission = project_permission(db, user, project_row)
    if not permission or (edit and permission != "manage"):
        raise HTTPException(403, "You do not have access to this project.")
    return permission


def set_public_auth_cookie(response: RedirectResponse, value: str, max_age_seconds: int):
    response.set_cookie(
        PUBLIC_AUTH_COOKIE,
        value,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
        max_age=max_age_seconds,
    )


def clear_public_auth_cookie(response: RedirectResponse):
    response.delete_cookie(PUBLIC_AUTH_COOKIE)


def create_public_auth_session(
    db: Session,
    scope: str,
    ttl_seconds: int,
    password_reset_id: int | None = None,
    invitation_id: int | None = None,
    participant_invitation_id: int | None = None,
) -> str:
    raw = new_token()
    db.add(
        PublicAuthSession(
            scope=scope,
            session_hash=token_hash(raw),
            password_reset_id=password_reset_id,
            invitation_id=invitation_id,
            participant_invitation_id=participant_invitation_id,
            expires_at=now() + timedelta(seconds=ttl_seconds),
        )
    )
    return raw


def get_public_auth_session(request: Request, db: Session, scope: str):
    raw = request.cookies.get(PUBLIC_AUTH_COOKIE, "")
    if not raw:
        return None
    row = db.scalar(
        select(PublicAuthSession).where(
            PublicAuthSession.scope == scope,
            PublicAuthSession.session_hash == token_hash(raw),
            PublicAuthSession.revoked_at.is_(None),
        )
    )
    if not row or not unexpired(row.expires_at):
        return None
    return row


def revoke_public_auth_session(request: Request, db: Session, scope: str):
    row = get_public_auth_session(request, db, scope)
    if not row:
        return
    row.revoked_at = now()
    db.commit()


def token_already_redeemed(db: Session, scope: str, raw_token: str) -> bool:
    return db.scalar(
        select(PublicTokenExchange.id).where(
            PublicTokenExchange.scope == scope,
            PublicTokenExchange.token_hash == token_hash(raw_token),
        )
    ) is not None


def record_token_redemption(db: Session, scope: str, raw_token: str):
    db.add(
        PublicTokenExchange(
            scope=scope,
            token_hash=token_hash(raw_token),
        )
    )

def paginate(stmt, db, page, per=25):
    page=max(1,page); total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows=db.scalars(stmt.offset((page-1)*per).limit(per)).all()
    return rows,total,max(1,(total+per-1)//per)


def _cache_control_no_store(response: Response):
    response.headers["Cache-Control"] = "no-store"


def _participant_api_unauthorised() -> HTTPException:
    return HTTPException(
        401,
        "Invalid or expired participant API credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _participant_api_exchange_conflict() -> HTTPException:
    return HTTPException(
        409,
        "A participant API session is already active for this invitation.",
    )


def _extract_bearer_token(request: Request) -> str:
    header = (request.headers.get("authorization") or "").strip()
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _participant_api_unauthorised()
    return token.strip()


def _resolve_participant_api_context(
    request: Request,
    db: Session,
) -> tuple[PublicAuthSession, ParticipantInvitation, Participant]:
    raw_token = _extract_bearer_token(request)
    session_row = resolve_participant_api_session(db, raw_token=raw_token)
    if not session_row:
        raise _participant_api_unauthorised()
    invitation = db.get(ParticipantInvitation, session_row.participant_invitation_id)
    if not invitation or invitation.revoked_at or not unexpired(invitation.expires_at):
        raise _participant_api_unauthorised()
    participant_row = db.get(Participant, invitation.participant_id)
    if not participant_row:
        raise _participant_api_unauthorised()
    return session_row, invitation, participant_row


def create_pilot_sample_data(db: Session, user: User) -> dict[str, int]:
    created = {"projects": 0, "studies": 0, "participants": 0, "activities": 0, "enrolments": 0}
    organisation_id = user.organisation_id

    project = db.scalar(
        select(Project).where(
            Project.organisation_id == organisation_id,
            Project.code == "PILOT-001",
        )
    )
    if not project:
        project = Project(
            organisation_id=organisation_id,
            title="Pilot neighbourhood listening",
            code="PILOT-001",
            description="Starter project with example structure for a live authority pilot.",
            status="live",
            created_by_id=user.id,
        )
        db.add(project)
        db.flush()
        created["projects"] += 1

    study_row = db.scalar(
        select(Study).where(
            Study.organisation_id == organisation_id,
            Study.code == "PILOT-ST01",
        )
    )
    if not study_row:
        study_row = Study(
            organisation_id=organisation_id,
            project_id=project.id,
            title="Town centre accessibility pulse",
            code="PILOT-ST01",
            description="Sample study for onboarding and training teams before pilot go-live.",
            methodology="mixed_method",
            status="recruiting",
            created_by_id=user.id,
        )
        db.add(study_row)
        db.flush()
        created["studies"] += 1

    if not db.scalar(select(Activity.id).where(Activity.organisation_id == organisation_id, Activity.study_id == study_row.id)):
        db.add(Activity(organisation_id=organisation_id, study_id=study_row.id, title="First journey reflection", prompt="Describe a recent journey and any challenges.", activity_type="long_text", position=1, required=True, release_offset_days=0))
        db.add(Activity(organisation_id=organisation_id, study_id=study_row.id, title="Safety confidence", prompt="Rate your confidence moving through the area.", activity_type="rating", position=2, required=True, release_offset_days=1, due_offset_days=3))
        created["activities"] += 2

    for reference, name, email in [
        ("PILOT-P01", "Sample Resident One", "pilot.participant.one@example.org"),
        ("PILOT-P02", "Sample Resident Two", "pilot.participant.two@example.org"),
    ]:
        participant_row = db.scalar(
            select(Participant).where(
                Participant.organisation_id == organisation_id,
                Participant.reference == reference,
            )
        )
        if not participant_row:
            participant_row = Participant(
                organisation_id=organisation_id,
                reference=reference,
                name=name,
                email=email,
                status=ParticipantStatus.prospective.value,
                consent_status=ConsentStatus.pending.value,
                communication_preference="email",
                tags="sample,pilot",
                created_by_id=user.id,
            )
            db.add(participant_row)
            db.flush()
            created["participants"] += 1

        enrolment = db.scalar(
            select(StudyEnrolment).where(
                StudyEnrolment.organisation_id == organisation_id,
                StudyEnrolment.study_id == study_row.id,
                StudyEnrolment.participant_id == participant_row.id,
            )
        )
        if not enrolment:
            db.add(
                StudyEnrolment(
                    organisation_id=organisation_id,
                    study_id=study_row.id,
                    participant_id=participant_row.id,
                    status="enrolled",
                )
            )
            created["enrolments"] += 1

    audit(
        db,
        organisation_id,
        user.id,
        "pilot.sample_data_generated",
        "organisation",
        organisation_id,
        f"projects={created['projects']} studies={created['studies']} participants={created['participants']} activities={created['activities']} enrolments={created['enrolments']}",
    )
    db.commit()
    return created

def startup():
    configure_logging()
    validate_runtime_settings(settings)
    validate_startup_environment()
    storage.ensure_ready()
    Base.metadata.create_all(engine)
    # Safe additive migration for databases created by v0.2.x.
    if settings.database_url.startswith("sqlite"):
        with engine.begin() as c:
            cols={r[1] for r in c.execute(text("PRAGMA table_info(studies)"))}
            if "demographics_schema_json" not in cols: c.execute(text("ALTER TABLE studies ADD COLUMN demographics_schema_json TEXT DEFAULT '[]'"))
            user_cols={r[1] for r in c.execute(text("PRAGMA table_info(users)"))}
            if "external_provider" not in user_cols: c.execute(text("ALTER TABLE users ADD COLUMN external_provider VARCHAR(40)"))
            if "external_subject" not in user_cols: c.execute(text("ALTER TABLE users ADD COLUMN external_subject VARCHAR(255)"))
            if "last_login_at" not in user_cols: c.execute(text("ALTER TABLE users ADD COLUMN last_login_at DATETIME"))
            evidence_cols={r[1] for r in c.execute(text("PRAGMA table_info(evidence_files)"))}
            if "sha256_hex" not in evidence_cols: c.execute(text("ALTER TABLE evidence_files ADD COLUMN sha256_hex VARCHAR(64) DEFAULT ''"))
            if "scan_status" not in evidence_cols: c.execute(text("ALTER TABLE evidence_files ADD COLUMN scan_status VARCHAR(30) DEFAULT 'pending'"))
            if "scan_detail" not in evidence_cols: c.execute(text("ALTER TABLE evidence_files ADD COLUMN scan_detail TEXT DEFAULT ''"))
            if "storage_provider" not in evidence_cols: c.execute(text("ALTER TABLE evidence_files ADD COLUMN storage_provider VARCHAR(30) DEFAULT 'local'"))
            if "blob_uri" not in evidence_cols: c.execute(text("ALTER TABLE evidence_files ADD COLUMN blob_uri TEXT DEFAULT ''"))
            if "scan_completed_at" not in evidence_cols: c.execute(text("ALTER TABLE evidence_files ADD COLUMN scan_completed_at DATETIME"))
    with SessionLocal() as db:
        if settings.seed_demo_data and not db.scalar(select(func.count(User.id))):
            org=Organisation(name="Politis Demo Council",slug="politis-demo"); db.add(org); db.flush()
            u=User(organisation_id=org.id,name="Platform Owner",email="admin@politis.local",password_hash=hash_password("PolitisDemo!"),role="owner"); db.add(u); db.flush()
            add_organisation_membership(db, u, org.id, "owner")
            p=Project(organisation_id=org.id,title="Town Centre Experience",code="TCX-001",description="Demonstration civic intelligence project.",status="live",created_by_id=u.id); db.add(p); db.flush()
            s=Study(organisation_id=org.id,project_id=p.id,title="Seven-day town centre diary",code="TCX-D01",description="A demonstration longitudinal diary study.",methodology="diary",status="recruiting",created_by_id=u.id); db.add(s); db.flush()
            db.add(Activity(organisation_id=org.id,study_id=s.id,title="First impressions",prompt="Tell us about your latest visit to the town centre.",activity_type="long_text",position=1))
            audit(db,org.id,u.id,"platform.seeded","organisation",org.id,"Initial demonstration tenant created"); db.commit()


@app.middleware("http")
async def static_cache_middleware(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/") and response.status_code == 200:
        response.headers.setdefault("Cache-Control", "public, max-age=86400")
    return response

@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": VERSION,
    }


@app.get("/health/ready")
def readiness():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        logger.error(
            "readiness_failed dependency=database error=%s",
            exc.__class__.__name__,
        )
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable"},
        )
    return {"status": "ready", "version": VERSION}


@app.get("/login",response_class=HTMLResponse)
def login_page(request:Request): return render(request,"login.html")
@app.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_ok: None = Depends(csrf_protect),
    db: Session = Depends(get_db),
):
    if not settings.local_login_enabled:
        return render(
            request,
            "login.html",
            error="Password sign-in is disabled. Use Microsoft sign-in.",
        )

    normalised_email = email.lower().strip()
    user = unique_active_user_for_email(db, normalised_email)
    _enforce_rate_limit(
        request,
        db,
        scope="login",
        ip_limit=settings.rate_limit_login_ip,
        account_key=normalised_email,
        account_limit=settings.rate_limit_login_account,
        organisation_id=user.organisation_id if user else None,
        actor_user_id=user.id if user else None,
    )

    generic_error = "Email or password is incorrect."

    if not user or not user.password_hash:
        return render(request, "login.html", error=generic_error)

    current_time = now()

    if user.locked_until:
        locked_until = user.locked_until

        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)

        if locked_until > current_time:
            return render(request, "login.html", error=generic_error)

        user.locked_until = None
        user.failed_login_count = 0

    if not verify_password(password, user.password_hash):
        user.failed_login_count += 1

        if user.failed_login_count >= settings.login_max_failed_attempts:
            user.locked_until = current_time + timedelta(
                seconds=settings.login_lockout_seconds
            )
            bump_session_version(user)
            audit(
                db,
                user.organisation_id,
                user.id,
                "auth.account_locked",
                "user",
                user.id,
                "Account temporarily locked after repeated failed sign-in attempts",
            )
        else:
            audit(
                db,
                user.organisation_id,
                user.id,
                "auth.login_failed",
                "user",
                user.id,
                "Incorrect password",
            )

        db.commit()
        return render(request, "login.html", error=generic_error)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = current_time

    audit(
        db,
        user.organisation_id,
        user.id,
        "auth.login",
        "user",
        user.id,
    )

    db.commit()

    response = RedirectResponse("/", 303)
    response.set_cookie(
        "session",
        encode_session(
            user.id,
            user.session_version,
            user.organisation_id,
        ),
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
        max_age=settings.session_max_age_seconds,
    )
    return response

@app.get("/auth/entra/login")
async def entra_login(request: Request):
    if not entra_configured():
        raise HTTPException(503, "Microsoft sign-in is not configured.")
    redirect_uri = f"{settings.base_url.rstrip('/')}/auth/entra/callback"
    return await oauth.entra.authorize_redirect(request, redirect_uri)

@app.get("/auth/entra/callback")
async def entra_callback(request: Request, db: Session = Depends(get_db)):
    if not entra_configured():
        raise HTTPException(503, "Microsoft sign-in is not configured.")
    try:
        token = await oauth.entra.authorize_access_token(request)
    except Exception:
        return render(request, "login.html", error="Microsoft sign-in could not be completed.")
    claims = token.get("userinfo") or {}
    identity = entra_identity_from_claims(claims)
    if not identity:
        return render(request, "login.html", error="Microsoft account details could not be verified.")
    subject, email, name = identity
    allowed = {x.strip().lower() for x in settings.entra_allowed_domains.split(",") if x.strip()}
    domain = email.rsplit("@", 1)[-1] if "@" in email else ""
    if allowed and domain not in allowed:
        return render(request, "login.html", error="This Microsoft account is not permitted for this service.")
    entra_matches = list(
        db.scalars(
            select(User)
            .where(
                User.external_provider == "entra",
                User.external_subject == subject,
                User.is_active == True,
            )
            .limit(2)
        ).all()
    )
    if len(entra_matches) > 1:
        return render(request, "login.html", error="Microsoft account details could not be verified.")
    user = entra_matches[0] if entra_matches else None
    if not user:
        email_matches = active_users_for_email(db, email)
        if len(email_matches) > 1:
            return render(request, "login.html", error="Your Microsoft account has not been invited to this workspace.")
        user = email_matches[0] if email_matches else None
        if user:
            user.external_provider = "entra"
            user.external_subject = subject
        elif settings.entra_auto_provision and settings.entra_default_organisation_slug:
            org = db.scalar(select(Organisation).where(Organisation.slug == settings.entra_default_organisation_slug))
            if not org:
                return render(request, "login.html", error="The configured organisation could not be found.")
            role = settings.entra_default_role if settings.entra_default_role in {"owner","admin","researcher","observer"} else "researcher"
            user = User(organisation_id=org.id, name=name[:120], email=email, password_hash=None, role=role, is_active=True, external_provider="entra", external_subject=subject)
            db.add(user); db.flush()
            add_organisation_membership(db, user, org.id, role)
        else:
            return render(request, "login.html", error="Your Microsoft account has not been invited to this workspace.")
    user.name = name[:120] or user.name
    user.last_login_at = now()
    audit(db, user.organisation_id, user.id, "auth.entra_login", "user", user.id)
    db.commit()
    response = RedirectResponse("/", 303)
    response.set_cookie("session", encode_session(user.id, user.session_version, user.organisation_id), httponly=True, samesite="lax", secure=settings.cookie_secure, max_age=43200)
    return response

@app.post("/logout")
def logout(request: Request, csrf_ok: None = Depends(csrf_protect), db: Session = Depends(get_db)):
    invalidate_session_cookie_user(request, db)
    r=RedirectResponse("/login",303); r.delete_cookie("session"); return r


@app.post("/organisations/switch")
def switch_organisation(
    organisation_id: int = Form(...),
    u=Depends(current_user),
    csrf_ok: None = Depends(csrf_protect),
    db: Session = Depends(get_db),
):
    membership = db.scalar(
        select(OrganisationMembership).where(
            OrganisationMembership.user_id == u.id,
            OrganisationMembership.organisation_id == organisation_id,
            OrganisationMembership.is_active == True,
        )
    )
    if not membership:
        raise HTTPException(403, "Organisation membership is unavailable.")
    response = RedirectResponse("/", 303)
    response.set_cookie(
        "session",
        encode_session(u.id, u.session_version, organisation_id),
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
        max_age=settings.session_max_age_seconds,
    )
    return response

@app.get("/forgot-password",response_class=HTMLResponse)
def forgot_page(request:Request): return render(request,"forgot_password.html")
@app.post("/forgot-password",response_class=HTMLResponse)
def forgot(request:Request,email:str=Form(...),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    normalised_email = email.lower().strip()
    u=unique_active_user_for_email(db,normalised_email)
    _enforce_rate_limit(
        request,
        db,
        scope="forgot_password",
        ip_limit=settings.rate_limit_forgot_password_ip,
        account_key=normalised_email,
        account_limit=settings.rate_limit_forgot_password_account,
        organisation_id=u.organisation_id if u else None,
        actor_user_id=u.id if u else None,
    )
    if u:
        raw=new_token(); db.add(PasswordReset(user_id=u.id,token_hash=token_hash(raw),expires_at=now()+timedelta(hours=1)))
        queue_email(db,u.organisation_id,u.email,"Citizen Centric by Politis: Reset your password",f"Reset your Citizen Centric password: {settings.base_url}/reset-password?token={raw}"); audit(db,u.organisation_id,u.id,"auth.password_reset_requested","user",u.id); db.commit()
    return render(request,"forgot_password.html",sent=True)
@app.get("/reset-password",response_class=HTMLResponse)
def reset_page(request:Request,token:str="",db:Session=Depends(get_db)):
    if token:
        if token_already_redeemed(db, PUBLIC_SCOPE_PASSWORD_RESET, token):
            return render(request,"reset_password.html",valid=False)
        row=db.scalar(select(PasswordReset).where(PasswordReset.token_hash==token_hash(token)))
        valid=bool(row and not row.used_at and unexpired(row.expires_at))
        if not valid:
            return render(request,"reset_password.html",valid=False)
        raw_session = create_public_auth_session(
            db,
            scope=PUBLIC_SCOPE_PASSWORD_RESET,
            ttl_seconds=15 * 60,
            password_reset_id=row.id,
        )
        record_token_redemption(db, PUBLIC_SCOPE_PASSWORD_RESET, token)
        db.commit()
        response = RedirectResponse("/reset-password", 303)
        set_public_auth_cookie(response, raw_session, 15 * 60)
        return response

    session_row = get_public_auth_session(request, db, PUBLIC_SCOPE_PASSWORD_RESET)
    if not session_row:
        return render(request,"reset_password.html",valid=False)
    row = db.get(PasswordReset, session_row.password_reset_id)
    valid=bool(row and not row.used_at and unexpired(row.expires_at))
    return render(request,"reset_password.html",valid=valid)
@app.post("/reset-password")
def reset_password(request: Request, token:str=Form(""),password:str=Form(...),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    session_row = get_public_auth_session(request, db, PUBLIC_SCOPE_PASSWORD_RESET)
    row = db.get(PasswordReset, session_row.password_reset_id) if session_row else None
    user = db.get(User, row.user_id) if row else None
    token_key = token_hash(token) if token else f"session:{session_row.id}" if session_row else "missing"
    _enforce_rate_limit(
        request,
        db,
        scope="password_reset",
        ip_limit=settings.rate_limit_password_reset_ip,
        account_key=token_key,
        account_limit=settings.rate_limit_password_reset_token,
        organisation_id=user.organisation_id if user else None,
        actor_user_id=user.id if user else None,
    )
    if not session_row:
        raise HTTPException(400,"Reset link is invalid or expired.")
    if not row or row.used_at or not unexpired(row.expires_at): raise HTTPException(400,"Reset link is invalid or expired.")
    if len(password)<10: raise HTTPException(400,"Password must contain at least 10 characters.")
    user.password_hash=hash_password(password); row.used_at=now(); user.failed_login_count = 0; user.locked_until = None; bump_session_version(user); session_row.revoked_at = now(); audit(db,user.organisation_id,user.id,"auth.password_reset","user",user.id); db.commit(); response = RedirectResponse("/login",303); clear_public_auth_cookie(response); return response

@app.get("/",response_class=HTMLResponse)
def dashboard(request:Request,u=Depends(current_user),db:Session=Depends(get_db)):
    o=u.organisation_id
    organisation_wide = u.role in {"owner", "admin", "observer"}
    accessible_studies = (
        select(Study.id).where(Study.organisation_id == o)
        if organisation_wide
        else study_scope_for_user(u)
    )
    accessible_participants = select(StudyEnrolment.participant_id).where(
        StudyEnrolment.organisation_id == o,
        StudyEnrolment.study_id.in_(accessible_studies),
    )
    accessible_projects = select(Study.project_id).where(
        Study.organisation_id == o,
        Study.id.in_(accessible_studies),
    )
    project_filter = (
        Project.organisation_id == o
        if organisation_wide
        else (
            (Project.organisation_id == o)
            & or_(
                Project.created_by_id == u.id,
                Project.id.in_(accessible_projects),
            )
        )
    )
    metrics_row = db.execute(
        select(
            select(func.count(Project.id))
            .where(project_filter)
            .scalar_subquery()
            .label("projects"),
            select(func.count(Study.id))
            .where(
                Study.organisation_id == o,
                Study.id.in_(accessible_studies),
            )
            .scalar_subquery()
            .label("studies"),
            select(func.count(Participant.id))
            .where(
                Participant.organisation_id == o,
                Participant.id.in_(accessible_participants),
            )
            .scalar_subquery()
            .label("participants"),
            select(func.count(Participant.id))
            .where(
                Participant.organisation_id == o,
                Participant.id.in_(accessible_participants),
                Participant.status == "active",
            )
            .scalar_subquery()
            .label("active"),
            select(func.count(ParticipantInvitation.id))
            .where(
                ParticipantInvitation.organisation_id == o,
                ParticipantInvitation.study_id.in_(accessible_studies),
                ParticipantInvitation.accepted_at.is_(None),
                ParticipantInvitation.revoked_at.is_(None),
            )
            .scalar_subquery()
            .label("invitations"),
            select(func.count(ActivityResponse.id))
            .where(
                ActivityResponse.organisation_id == o,
                ActivityResponse.study_id.in_(accessible_studies),
                ActivityResponse.status == "submitted",
            )
            .scalar_subquery()
            .label("submissions"),
        )
    ).one()
    metrics={
        "projects": int(metrics_row.projects or 0),
        "studies": int(metrics_row.studies or 0),
        "participants": int(metrics_row.participants or 0),
        "active": int(metrics_row.active or 0),
        "invitations": int(metrics_row.invitations or 0),
        "submissions": int(metrics_row.submissions or 0),
    }
    studies=db.scalars(
        select(Study)
        .where(
            Study.organisation_id == o,
            Study.id.in_(accessible_studies),
        )
        .order_by(Study.updated_at.desc())
        .limit(6)
    ).all()
    project_ids = {s.project_id for s in studies}
    pmap={p.id:p for p in db.scalars(select(Project).where(Project.organisation_id==o, Project.id.in_(project_ids))).all()} if project_ids else {}
    recent_events_stmt = select(AuditEvent).where(
        AuditEvent.organisation_id == o
    )
    if not organisation_wide:
        recent_events_stmt = recent_events_stmt.where(
            AuditEvent.actor_user_id == u.id
        )
    recent_events = db.scalars(
        recent_events_stmt.order_by(AuditEvent.created_at.desc()).limit(5)
    ).all()
    onboarding={
        "has_project": metrics["projects"] > 0,
        "has_study": metrics["studies"] > 0,
        "has_participant": metrics["participants"] > 0,
        "has_submission": metrics["submissions"] > 0,
        "can_seed": u.role in {"owner", "admin"},
    }
    return render(request,"dashboard.html",user=u,metrics=metrics,studies=studies,project_map=pmap,onboarding=onboarding,recent_events=recent_events)


@app.post("/pilot/sample-data")
def generate_pilot_sample_data(
    request: Request,
    u=Depends(roles("owner", "admin")),
    csrf_ok: None = Depends(csrf_protect),
    db: Session = Depends(get_db),
):
    created = create_pilot_sample_data(db, u)
    if any(created.values()):
        set_flash(request, "notice", "Sample pilot data has been added to your workspace.")
    else:
        set_flash(request, "notice", "Sample pilot data is already available for this organisation.")
    return RedirectResponse("/", 303)


@app.get("/onboarding/first-project", response_class=HTMLResponse)
def first_project_wizard_page(request: Request, u=Depends(roles("owner", "admin", "researcher"))):
    return render(
        request,
        "first_project_wizard.html",
        user=u,
        project_statuses=[x.value for x in ProjectStatus],
        study_statuses=[x.value for x in StudyStatus],
        activity_types=sorted(ACTIVITY_TYPES),
    )


@app.post("/onboarding/first-project")
def first_project_wizard_submit(
    request: Request,
    project_title: str = Form(...),
    project_code: str = Form(...),
    project_description: str = Form(""),
    project_status: str = Form("draft"),
    study_title: str = Form(...),
    study_code: str = Form(...),
    study_description: str = Form(""),
    study_methodology: str = Form("diary"),
    study_status: str = Form("recruiting"),
    add_starter_activity: bool = Form(True),
    csrf_ok: None = Depends(csrf_protect),
    u=Depends(roles("owner", "admin", "researcher")),
    db: Session = Depends(get_db),
):
    enum_value(project_status, ProjectStatus, "project status")
    enum_value(study_status, StudyStatus, "study status")

    if study_methodology not in STUDY_METHODOLOGIES:
        raise HTTPException(400, "Please select a valid study methodology.")

    cleaned_project_title = project_title.strip()
    cleaned_study_title = study_title.strip()
    if len(cleaned_project_title) < 3:
        raise HTTPException(400, "Project title must be at least 3 characters long.")
    if len(cleaned_study_title) < 3:
        raise HTTPException(400, "Study title must be at least 3 characters long.")

    project_row = Project(
        organisation_id=u.organisation_id,
        title=cleaned_project_title,
        code=project_code.strip().upper(),
        description=project_description.strip(),
        status=project_status,
        created_by_id=u.id,
    )
    db.add(project_row)
    try:
        db.flush()
    except Exception:
        db.rollback()
        raise HTTPException(400, "Project code already exists. Use a unique code such as BORO-001.")

    study_row = Study(
        organisation_id=u.organisation_id,
        project_id=project_row.id,
        title=cleaned_study_title,
        code=study_code.strip().upper(),
        description=study_description.strip(),
        methodology=study_methodology,
        status=study_status,
        created_by_id=u.id,
    )
    db.add(study_row)
    try:
        db.flush()
    except Exception:
        db.rollback()
        raise HTTPException(400, "Study code already exists. Use a unique code such as BORO-ST01.")

    if add_starter_activity:
        db.add(
            Activity(
                organisation_id=u.organisation_id,
                study_id=study_row.id,
                title="Welcome activity",
                prompt="Share your first thoughts about this area and what should improve.",
                activity_type="long_text",
                position=1,
                required=True,
                release_offset_days=0,
            )
        )

    audit(db, u.organisation_id, u.id, "pilot.first_project_wizard_completed", "study", study_row.id, study_row.title)
    db.commit()
    set_flash(request, "notice", "Your first project has been created. You can now enrol participants and send invitations.")
    return RedirectResponse(f"/studies/{study_row.id}", 303)

@app.get("/projects",response_class=HTMLResponse)
def projects(request:Request,u=Depends(current_user),db:Session=Depends(get_db)):
    stmt = select(Project).where(
        Project.organisation_id == u.organisation_id
    )
    if u.role not in {"owner", "admin", "observer"}:
        stmt = stmt.where(Project.id.in_(project_scope_for_user(u)))
    rows = db.scalars(stmt.order_by(Project.updated_at.desc())).all()
    project_ids = [row.id for row in rows]
    counts = dict(
        db.execute(
            select(Study.project_id, func.count(Study.id))
            .where(
                Study.organisation_id == u.organisation_id,
                Study.project_id.in_(project_ids),
            )
            .group_by(Study.project_id)
        ).all()
    ) if project_ids else {}
    return render(request,"projects.html",user=u,projects=rows,counts=counts,statuses=[x.value for x in ProjectStatus])
@app.post("/projects")
def create_project(title:str=Form(...),code:str=Form(...),description:str=Form(""),status_value:str=Form("draft"),u=Depends(roles("owner","admin","researcher")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    enum_value(status_value,ProjectStatus,"project status"); cleaned_title=nonblank(title,"Project title",3); cleaned_code=nonblank(code,"Project code").upper(); row=Project(organisation_id=u.organisation_id,title=cleaned_title,code=cleaned_code,description=description.strip(),status=status_value,created_by_id=u.id); db.add(row)
    try: db.flush(); audit(db,u.organisation_id,u.id,"project.created","project",row.id,row.title); db.commit()
    except Exception: db.rollback(); raise HTTPException(400,"Project code must be unique.")
    return RedirectResponse(f"/projects/{row.id}",303)
@app.get("/projects/{project_id}",response_class=HTMLResponse)
def project_detail(project_id:int,request:Request,u=Depends(current_user),db:Session=Depends(get_db)):
    p=project(db,project_id,u.organisation_id)
    permission=require_project_permission(db,u,p)
    studies_stmt=select(Study).where(Study.project_id==p.id,Study.organisation_id==u.organisation_id)
    if u.role not in {"owner","admin","observer"}:
        studies_stmt=studies_stmt.where(Study.id.in_(study_scope_for_user(u)))
    studies=db.scalars(studies_stmt.order_by(Study.updated_at.desc())).all()
    return render(request,"project_detail.html",user=u,project=p,studies=studies,statuses=[x.value for x in StudyStatus],can_edit=permission=="manage")
@app.post("/projects/{project_id}/edit")
def edit_project(project_id:int,title:str=Form(...),description:str=Form(""),status_value:str=Form(...),u=Depends(roles("owner","admin","researcher")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    p=project(db,project_id,u.organisation_id); require_project_permission(db,u,p,edit=True); enum_value(status_value,ProjectStatus,"project status"); p.title=title.strip(); p.description=description.strip(); p.status=status_value; audit(db,u.organisation_id,u.id,"project.updated","project",p.id,p.title); db.commit(); return RedirectResponse(f"/projects/{p.id}",303)
@app.post("/projects/{project_id}/status")
def update_project_status(project_id:int,status_value:str=Form(...),u=Depends(roles("owner","admin","researcher")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    p=project(db,project_id,u.organisation_id)
    return edit_project(project_id,p.title,p.description,status_value,u,csrf_ok,db)

@app.get("/studies",response_class=HTMLResponse)
def studies_page(request:Request,u=Depends(current_user),db:Session=Depends(get_db)):
    stmt=select(Study).where(Study.organisation_id==u.organisation_id)
    if u.role not in {"owner","admin","observer"}:
        permitted_ids=select(StudyAccess.study_id).where(StudyAccess.organisation_id==u.organisation_id,StudyAccess.user_id==u.id)
        stmt=stmt.where(or_(Study.created_by_id==u.id,Study.id.in_(permitted_ids)))
    rows=db.scalars(stmt.order_by(Study.updated_at.desc())).all()
    study_ids = [s.id for s in rows]
    project_ids = {s.project_id for s in rows}
    projects={p.id:p for p in db.scalars(select(Project).where(Project.organisation_id==u.organisation_id, Project.id.in_(project_ids))).all()} if project_ids else {}
    counts=dict(db.execute(select(StudyEnrolment.study_id,func.count()).where(StudyEnrolment.organisation_id==u.organisation_id, StudyEnrolment.study_id.in_(study_ids)).group_by(StudyEnrolment.study_id)).all()) if study_ids else {}
    return render(request,"studies.html",user=u,studies=rows,projects=projects,enrolment_counts=counts)
@app.post("/projects/{project_id}/studies")
def create_study(project_id:int,title:str=Form(...),code:str=Form(...),description:str=Form(""),methodology:str=Form("diary"),status_value:str=Form("draft"),u=Depends(roles("owner","admin","researcher")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    p=project(db,project_id,u.organisation_id); require_project_permission(db,u,p,edit=True); enum_value(status_value,StudyStatus,"study status")
    if methodology not in STUDY_METHODOLOGIES: raise HTTPException(400,"Invalid methodology.")
    cleaned_title=nonblank(title,"Study title",3); cleaned_code=nonblank(code,"Study code").upper(); s=Study(organisation_id=u.organisation_id,project_id=p.id,title=cleaned_title,code=cleaned_code,description=description.strip(),methodology=methodology,status=status_value,created_by_id=u.id); db.add(s)
    try: db.flush(); audit(db,u.organisation_id,u.id,"study.created","study",s.id,s.title); db.commit()
    except Exception: db.rollback(); raise HTTPException(400,"Study code must be unique.")
    return RedirectResponse(f"/studies/{s.id}",303)
@app.get("/studies/{study_id}",response_class=HTMLResponse)
def study_detail(study_id:int,request:Request,u=Depends(current_user),db:Session=Depends(get_db)):
    s=study(db,study_id,u.organisation_id); permission=require_study_permission(db,u,s); p=project(db,s.project_id,u.organisation_id); acts=db.scalars(select(Activity).where(Activity.study_id==s.id,Activity.organisation_id==u.organisation_id).order_by(Activity.position)).all(); ens=db.scalars(select(StudyEnrolment).where(StudyEnrolment.study_id==s.id,StudyEnrolment.organisation_id==u.organisation_id)).all(); invs=db.scalars(select(ParticipantInvitation).where(ParticipantInvitation.study_id==s.id,ParticipantInvitation.organisation_id==u.organisation_id).order_by(ParticipantInvitation.created_at.desc())).all(); latest={}
    for i in invs: latest.setdefault(i.participant_id,i)
    enrolled_ids = {e.participant_id for e in ens}
    if permission in {"edit", "manage"}:
        ps={x.id:x for x in db.scalars(select(Participant).where(Participant.organisation_id==u.organisation_id)).all()}
        available=[x for x in ps.values() if x.id not in enrolled_ids]
    else:
        ps={x.id:x for x in db.scalars(select(Participant).where(Participant.organisation_id==u.organisation_id, Participant.id.in_(enrolled_ids))).all()} if enrolled_ids else {}
        available=[]
    response_counts=dict(db.execute(select(ActivityResponse.activity_id,func.count()).where(ActivityResponse.study_id==s.id,ActivityResponse.status=="submitted").group_by(ActivityResponse.activity_id)).all())
    if u.role in {"owner", "admin"}:
        access_rows=db.scalars(select(StudyAccess).where(StudyAccess.study_id==s.id,StudyAccess.organisation_id==u.organisation_id)).all(); access_map={a.user_id:a for a in access_rows}; team=db.scalars(select(User).join(OrganisationMembership, OrganisationMembership.user_id==User.id).where(OrganisationMembership.organisation_id==u.organisation_id,OrganisationMembership.is_active==True,User.is_active==True).order_by(User.name)).all()
    else:
        access_map = {}
        team = []
    return render(request,"study_detail.html",user=u,study=s,project=p,activities=acts,enrolments=ens,participants=ps,available=available,latest_invites=latest,response_counts=response_counts,study_permission=permission,team=team,access_map=access_map,can_edit=permission in {"edit","manage"},activity_types=sorted(ACTIVITY_TYPES))
@app.post("/studies/{study_id}/edit")
def edit_study(study_id:int,title:str=Form(...),description:str=Form(""),methodology:str=Form(...),status_value:str=Form(...),demographics_schema:str=Form(""),u=Depends(roles("owner","admin","researcher")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    s=study(db,study_id,u.organisation_id); require_study_permission(db,u,s,edit=True); enum_value(status_value,StudyStatus,"study status")
    if methodology not in STUDY_METHODOLOGIES: raise HTTPException(400,"Invalid methodology.")
    s.title=nonblank(title,"Study title",3); s.description=description.strip(); s.methodology=methodology; s.status=status_value; s.demographics_schema_json=json.dumps([x.strip() for x in demographics_schema.splitlines() if x.strip()]); audit(db,u.organisation_id,u.id,"study.updated","study",s.id,s.title); db.commit(); return RedirectResponse(f"/studies/{s.id}",303)
@app.post("/studies/{study_id}/status")
def study_status(study_id:int,status_value:str=Form(...),u=Depends(roles("owner","admin","researcher")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    s=study(db,study_id,u.organisation_id); require_study_permission(db,u,s,edit=True); enum_value(status_value,StudyStatus,"study status"); s.status=status_value; db.commit(); return RedirectResponse(f"/studies/{s.id}",303)
@app.post("/studies/{study_id}/activities")
def create_activity(study_id:int,title:str=Form(...),prompt:str=Form(""),activity_type:str=Form("long_text"),options:str=Form(""),required:bool=Form(False),release_offset_days:int=Form(0),due_offset_days:str=Form(""),u=Depends(roles("owner","admin","researcher")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    s=study(db,study_id,u.organisation_id); require_study_permission(db,u,s,edit=True)
    if activity_type not in ACTIVITY_TYPES or release_offset_days<0: raise HTTPException(400,"Invalid activity configuration.")
    try: due=int(due_offset_days) if due_offset_days.strip() else None
    except ValueError: raise HTTPException(400,"Due day must be a whole number.")
    if due is not None and due<release_offset_days: raise HTTPException(400,"Due day cannot be earlier than release day.")
    opts=[x.strip() for x in options.splitlines() if x.strip()]
    if activity_type in {"single_choice","multiple_choice","ranking"} and len(opts)<2: raise HTTPException(400,"Choice and ranking activities require at least two options.")
    pos=(db.scalar(select(func.max(Activity.position)).where(Activity.study_id==s.id)) or 0)+1; a=Activity(organisation_id=u.organisation_id,study_id=s.id,title=nonblank(title,"Activity title"),prompt=prompt.strip(),activity_type=activity_type,options_json=json.dumps(opts),position=pos,required=required,release_offset_days=release_offset_days,due_offset_days=due); db.add(a); db.flush(); audit(db,u.organisation_id,u.id,"activity.created","activity",a.id,a.title); db.commit(); return RedirectResponse(f"/studies/{s.id}",303)
@app.post("/activities/{activity_id}/edit")
def edit_activity(activity_id:int,title:str=Form(...),prompt:str=Form(""),activity_type:str=Form(...),options:str=Form(""),required:bool=Form(False),release_offset_days:int=Form(0),due_offset_days:str=Form(""),u=Depends(roles("owner","admin","researcher")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    a=db.scalar(select(Activity).where(Activity.id==activity_id,Activity.organisation_id==u.organisation_id));
    if not a: raise HTTPException(404)
    require_study_permission(db,u,study(db,a.study_id,u.organisation_id),edit=True)
    if activity_type not in ACTIVITY_TYPES or release_offset_days<0: raise HTTPException(400,"Invalid activity configuration.")
    try: due=int(due_offset_days) if due_offset_days.strip() else None
    except ValueError: raise HTTPException(400,"Due day must be a whole number.")
    opts=[x.strip() for x in options.splitlines() if x.strip()]
    if due is not None and due<release_offset_days: raise HTTPException(400,"Invalid dates.")
    if activity_type in {"single_choice","multiple_choice","ranking"} and len(opts)<2: raise HTTPException(400,"At least two options required.")
    a.title=nonblank(title,"Activity title"); a.prompt=prompt.strip(); a.activity_type=activity_type; a.options_json=json.dumps(opts); a.required=required; a.release_offset_days=release_offset_days; a.due_offset_days=due; audit(db,u.organisation_id,u.id,"activity.updated","activity",a.id,a.title); db.commit(); return RedirectResponse(f"/studies/{a.study_id}",303)
@app.post("/activities/{activity_id}/delete")
def delete_activity(activity_id:int,u=Depends(roles("owner","admin","researcher")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    a=db.scalar(select(Activity).where(Activity.id==activity_id,Activity.organisation_id==u.organisation_id));
    if not a: raise HTTPException(404)
    require_study_permission(db,u,study(db,a.study_id,u.organisation_id),edit=True)
    sid=a.study_id; db.delete(a); db.commit(); return RedirectResponse(f"/studies/{sid}",303)

@app.get("/participants",response_class=HTMLResponse)
def participants_page(request:Request,q:str="",status_filter:str="",page:int=1,u=Depends(current_user),db:Session=Depends(get_db)):
    stmt=select(Participant).where(Participant.organisation_id==u.organisation_id)
    if u.role not in {"owner","admin","observer"}:
        participant_ids = select(StudyEnrolment.participant_id).where(
            StudyEnrolment.organisation_id == u.organisation_id,
            StudyEnrolment.study_id.in_(study_scope_for_user(u)),
        )
        stmt = stmt.where(or_(Participant.created_by_id == u.id, Participant.id.in_(participant_ids)))
    if q.strip():
        t=f"%{q.strip()}%"; stmt=stmt.where(or_(Participant.name.ilike(t),Participant.reference.ilike(t),Participant.email.ilike(t),Participant.tags.ilike(t)))
    if status_filter: enum_value(status_filter,ParticipantStatus,"participant status"); stmt=stmt.where(Participant.status==status_filter)
    rows,total,pages=paginate(stmt.order_by(Participant.updated_at.desc()),db,page)
    return render(request,"participants.html",user=u,participants=rows,q=q,status_filter=status_filter,statuses=[x.value for x in ParticipantStatus],consent_statuses=[x.value for x in ConsentStatus],page=page,pages=pages,total=total)
@app.post("/participants")
def create_participant(reference:str=Form(...),name:str=Form(...),email:str=Form(""),phone:str=Form(""),status_value:str=Form("prospective"),consent_status:str=Form("pending"),communication_preference:str=Form("email"),tags:str=Form(""),notes:str=Form(""),u=Depends(roles("owner","admin","researcher")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    enum_value(status_value,ParticipantStatus,"participant status"); enum_value(consent_status,ConsentStatus,"consent status")
    if communication_preference not in COMMUNICATION_PREFERENCES: raise HTTPException(400,"Invalid communication preference.")
    cleaned_reference=nonblank(reference,"Participant reference").upper(); cleaned_name=nonblank(name,"Participant name",3); cleaned_email=validated_email(email)
    row=Participant(organisation_id=u.organisation_id,reference=cleaned_reference,name=cleaned_name,email=cleaned_email,phone=phone.strip() or None,status=status_value,consent_status=consent_status,communication_preference=communication_preference,tags=tags.strip(),notes=notes.strip(),created_by_id=u.id); db.add(row)
    try: db.flush(); audit(db,u.organisation_id,u.id,"participant.created","participant",row.id,row.reference); db.commit()
    except Exception: db.rollback(); raise HTTPException(400,"Participant reference must be unique.")
    return RedirectResponse(f"/participants/{row.id}",303)
@app.post("/participants/import")
def import_participants(file:UploadFile=File(...),u=Depends(roles("owner","admin","researcher")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    raw=file.file.read(MAX_CSV_IMPORT_BYTES + 1)
    if len(raw)>MAX_CSV_IMPORT_BYTES: raise HTTPException(413,"CSV import must be 2 MB or smaller.")
    try: data=raw.decode("utf-8-sig")
    except UnicodeDecodeError: raise HTTPException(400,"CSV import must use UTF-8 encoding.")
    reader=csv.DictReader(io.StringIO(data))
    if reader.fieldnames:
        reader.fieldnames=[field.strip().lower() if field else field for field in reader.fieldnames]
    if not reader.fieldnames or not {"reference","name"}.issubset(set(reader.fieldnames)):
        raise HTTPException(400,"CSV import requires reference and name columns.")
    created=0; seen_refs=set()
    try:
        for row_number,r in enumerate(reader,start=2):
            if row_number>MAX_CSV_IMPORT_ROWS+1: raise HTTPException(413,f"CSV import cannot exceed {MAX_CSV_IMPORT_ROWS} data rows.")
            ref=nonblank(r.get("reference") or "",f"Participant reference on row {row_number}").upper()
            name=nonblank(r.get("name") or "",f"Participant name on row {row_number}",3)
            cleaned_email=validated_email(r.get("email") or "")
            if ref in seen_refs or db.scalar(select(Participant.id).where(Participant.organisation_id==u.organisation_id,Participant.reference==ref)): continue
            seen_refs.add(ref)
            db.add(Participant(organisation_id=u.organisation_id,reference=ref,name=name,email=cleaned_email,phone=(r.get("phone") or "").strip() or None,status="prospective",consent_status="pending",communication_preference="email",tags=(r.get("tags") or "").strip(),created_by_id=u.id)); created+=1
    except csv.Error as exc:
        raise HTTPException(400,f"CSV import is malformed: {exc}") from exc
    audit(db,u.organisation_id,u.id,"participant.bulk_imported","participant","bulk",str(created)); db.commit(); return RedirectResponse("/participants",303)
@app.get("/participants/{participant_id}",response_class=HTMLResponse)
def participant_detail(participant_id:int,request:Request,u=Depends(current_user),db:Session=Depends(get_db)):
    p=participant(db,participant_id,u.organisation_id)
    if u.role in {"owner","admin","observer"}:
        ens=db.scalars(select(StudyEnrolment).where(StudyEnrolment.participant_id==p.id,StudyEnrolment.organisation_id==u.organisation_id)).all()
        invs=db.scalars(select(ParticipantInvitation).where(ParticipantInvitation.participant_id==p.id,ParticipantInvitation.organisation_id==u.organisation_id).order_by(ParticipantInvitation.created_at.desc())).all()
        responses=db.scalars(select(ActivityResponse).where(ActivityResponse.participant_id==p.id,ActivityResponse.organisation_id==u.organisation_id).order_by(ActivityResponse.updated_at.desc())).all()
        evidence_files=db.scalars(select(EvidenceFile).where(EvidenceFile.participant_id==p.id,EvidenceFile.organisation_id==u.organisation_id).order_by(EvidenceFile.created_at.desc())).all()
        messages=db.scalars(select(ParticipantMessage).where(ParticipantMessage.participant_id==p.id,ParticipantMessage.organisation_id==u.organisation_id).order_by(ParticipantMessage.created_at)).all()
        study_ids = {e.study_id for e in ens} | {i.study_id for i in invs} | {r.study_id for r in responses} | {e.study_id for e in evidence_files} | {m.study_id for m in messages}
        studies={s.id:s for s in db.scalars(select(Study).where(Study.organisation_id==u.organisation_id, Study.id.in_(study_ids))).all()} if study_ids else {}
    else:
        allowed_ids = set(db.scalars(study_scope_for_user(u)).all())
        ens=db.scalars(select(StudyEnrolment).where(StudyEnrolment.participant_id==p.id,StudyEnrolment.organisation_id==u.organisation_id,StudyEnrolment.study_id.in_(allowed_ids))).all()
        if p.created_by_id != u.id and not ens:
            raise HTTPException(403, "You do not have access to this participant.")
        studies={s.id:s for s in db.scalars(select(Study).where(Study.organisation_id==u.organisation_id,Study.id.in_(allowed_ids))).all()}
        invs=db.scalars(select(ParticipantInvitation).where(ParticipantInvitation.participant_id==p.id,ParticipantInvitation.organisation_id==u.organisation_id,ParticipantInvitation.study_id.in_(allowed_ids)).order_by(ParticipantInvitation.created_at.desc())).all()
        responses=db.scalars(select(ActivityResponse).where(ActivityResponse.participant_id==p.id,ActivityResponse.organisation_id==u.organisation_id,ActivityResponse.study_id.in_(allowed_ids)).order_by(ActivityResponse.updated_at.desc())).all()
        evidence_files=db.scalars(select(EvidenceFile).where(EvidenceFile.participant_id==p.id,EvidenceFile.organisation_id==u.organisation_id,EvidenceFile.study_id.in_(allowed_ids)).order_by(EvidenceFile.created_at.desc())).all()
        messages=db.scalars(select(ParticipantMessage).where(ParticipantMessage.participant_id==p.id,ParticipantMessage.organisation_id==u.organisation_id,ParticipantMessage.study_id.in_(allowed_ids)).order_by(ParticipantMessage.created_at)).all()
    privacy_counts = participant_related_counts(db, p.id, u.organisation_id) if u.role in {"owner", "admin"} else None
    privacy_workflow_token = request.session.get(privacy_workflow_key(p.id)) if u.role in {"owner", "admin"} else None
    return render(request,"participant_detail.html",user=u,participant=p,enrolments=ens,studies=studies,invitations=invs,responses=responses,evidence_files=evidence_files,messages=messages,statuses=[x.value for x in ParticipantStatus],consent_statuses=[x.value for x in ConsentStatus],is_privacy_admin=u.role in {"owner", "admin"},privacy_counts=privacy_counts,privacy_workflow_token=privacy_workflow_token)


@app.get("/participants/{participant_id}/export")
def export_participant_data(participant_id:int,u=Depends(roles("owner","admin")),db:Session=Depends(get_db)):
    p=participant(db,participant_id,u.organisation_id)
    payload = participant_export_payload(db, p)
    audit(db,u.organisation_id,u.id,"privacy.participant_exported","participant",p.id,p.reference)
    db.commit()
    filename = f"participant-{p.id}-export.json"
    return JSONResponse(
        payload,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/participants/{participant_id}/privacy/delete-request")
def participant_delete_request(participant_id:int,request:Request,u=Depends(roles("owner","admin")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    p=participant(db,participant_id,u.organisation_id)
    request.session[privacy_workflow_key(p.id)] = new_token()
    return RedirectResponse(f"/participants/{p.id}#privacy",303)


@app.post("/participants/{participant_id}/privacy/delete-execute")
def participant_delete_execute(participant_id:int,request:Request,workflow_token:str=Form(""),mode:str=Form("auto"),u=Depends(roles("owner","admin")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    p=participant(db,participant_id,u.organisation_id)
    expected = request.session.get(privacy_workflow_key(p.id))
    if not expected or not workflow_token or not secrets.compare_digest(expected, workflow_token):
        raise HTTPException(400, "Privacy deletion confirmation is missing or expired.")
    request.session.pop(privacy_workflow_key(p.id), None)
    if mode not in {"auto", "delete", "anonymise"}:
        raise HTTPException(400, "Invalid privacy action.")
    counts = participant_related_counts(db, p.id, u.organisation_id)
    has_related = participant_has_related_data(counts)

    if mode == "delete" and has_related:
        raise HTTPException(400, "Deletion is not available for participants with related records. Use anonymisation.")

    applied = mode
    if mode == "auto":
        applied = "anonymise" if has_related else "delete"

    if applied == "delete":
        reference = p.reference
        pid = p.id
        db.delete(p)
        audit(db,u.organisation_id,u.id,"privacy.participant_deleted","participant",pid,json.dumps({"reference": reference, "counts": counts}))
        db.commit()
        return RedirectResponse("/participants",303)

    anonymise_participant_record(p)
    audit(db,u.organisation_id,u.id,"privacy.participant_anonymised","participant",p.id,json.dumps({"counts": counts}))
    db.commit()
    return RedirectResponse(f"/participants/{p.id}#privacy",303)


@app.post("/privacy/retention/apply")
def apply_privacy_retention(request:Request,u=Depends(roles("owner","admin")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    statuses = [x.strip() for x in settings.privacy_retention_statuses.split(",") if x.strip()]
    if not statuses:
        raise HTTPException(400, "No retention statuses configured.")
    days = max(0, int(settings.privacy_retention_days))
    cutoff = now() - timedelta(days=days)
    mode = settings.privacy_retention_action.strip().lower()
    if mode not in {"delete", "anonymise"}:
        raise HTTPException(400, "PRIVACY_RETENTION_ACTION must be delete or anonymise.")

    rows = db.scalars(
        select(Participant).where(
            Participant.organisation_id == u.organisation_id,
            Participant.status.in_(statuses),
            Participant.created_at <= cutoff,
        )
    ).all()

    processed = 0
    deleted = 0
    anonymised = 0
    for p in rows:
        counts = participant_related_counts(db, p.id, u.organisation_id)
        has_related = participant_has_related_data(counts)
        action = mode
        if action == "delete" and has_related:
            action = "anonymise"
        processed += 1
        if action == "delete":
            pid = p.id
            reference = p.reference
            db.delete(p)
            deleted += 1
            audit(db,u.organisation_id,u.id,"privacy.participant_deleted","participant",pid,json.dumps({"reason": "retention", "reference": reference, "counts": counts}))
        else:
            anonymise_participant_record(p)
            anonymised += 1
            audit(db,u.organisation_id,u.id,"privacy.participant_anonymised","participant",p.id,json.dumps({"reason": "retention", "counts": counts}))

    audit(
        db,
        u.organisation_id,
        u.id,
        "privacy.retention_applied",
        "organisation",
        u.organisation_id,
        json.dumps({"processed": processed, "deleted": deleted, "anonymised": anonymised, "days": days, "statuses": statuses, "configured_mode": mode}),
    )
    db.commit()
    return RedirectResponse("/participants",303)
@app.post("/participants/{participant_id}/update")
def update_participant(participant_id:int,name:str=Form(None),email:str=Form(None),phone:str=Form(None),status_value:str=Form(...),consent_status:str=Form(...),communication_preference:str=Form(...),tags:str=Form(""),notes:str=Form(""),demographics_json:str=Form("{}"),u=Depends(roles("owner","admin","researcher")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    p=participant(db,participant_id,u.organisation_id); enum_value(status_value,ParticipantStatus,"participant status"); enum_value(consent_status,ConsentStatus,"consent status")
    if communication_preference not in COMMUNICATION_PREFERENCES: raise HTTPException(400,"Invalid communication preference.")
    if u.role == "researcher":
        visible = db.scalar(
            select(StudyEnrolment.id).where(
                StudyEnrolment.organisation_id == u.organisation_id,
                StudyEnrolment.participant_id == p.id,
                StudyEnrolment.study_id.in_(study_scope_for_user(u)),
            )
        )
        if p.created_by_id != u.id and not visible:
            raise HTTPException(403, "You do not have access to this participant.")
    if name is not None: p.name=nonblank(name,"Participant name",3); p.email=validated_email(email or ""); p.phone=(phone or "").strip() or None
    try: json.loads(demographics_json or "{}")
    except json.JSONDecodeError: raise HTTPException(400,"Demographics must be valid JSON.")
    p.status=status_value; p.consent_status=consent_status; p.communication_preference=communication_preference; p.tags=tags.strip(); p.notes=notes.strip(); p.demographics_json=demographics_json or "{}"; audit(db,u.organisation_id,u.id,"participant.updated","participant",p.id,p.reference); db.commit(); return RedirectResponse(f"/participants/{p.id}",303)
@app.post("/studies/{study_id}/enrol")
def enrol(study_id:int,participant_id:int=Form(...),u=Depends(roles("owner","admin","researcher")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    s=study(db,study_id,u.organisation_id); require_study_permission(db,u,s,edit=True); p=participant(db,participant_id,u.organisation_id)
    if not db.scalar(select(StudyEnrolment).where(StudyEnrolment.study_id==s.id,StudyEnrolment.participant_id==p.id)): db.add(StudyEnrolment(organisation_id=u.organisation_id,study_id=s.id,participant_id=p.id)); audit(db,u.organisation_id,u.id,"participant.enrolled","participant",p.id,s.title); db.commit()
    return RedirectResponse(f"/studies/{s.id}",303)

def send_participant_invite(db,u,s,p):
    _, raw = create_participant_invitation(
        db,
        organisation_id=u.organisation_id,
        participant_id=p.id,
        study_id=s.id,
        invited_by_id=u.id,
        expires_at=now() + timedelta(days=30),
    )
    queue_email(db,u.organisation_id,p.email,f"Invitation: {s.title}",f"Join the study: {settings.base_url}/join-study?token={raw}"); p.status="invited"; audit(db,u.organisation_id,u.id,"participant.invited","participant",p.id,s.title); db.commit()
@app.post("/studies/{study_id}/invite/{participant_id}")
def invite_participant(study_id:int,participant_id:int,u=Depends(roles("owner","admin","researcher")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    s=study(db,study_id,u.organisation_id); require_study_permission(db,u,s,edit=True); p=participant(db,participant_id,u.organisation_id)
    if not p.email: raise HTTPException(400,"Participant requires an email address.")
    active = find_live_unaccepted_invitation(db, s.id, p.id, now())
    if active: raise HTTPException(400,"A live invitation already exists. Revoke it before resending.")
    send_participant_invite(db,u,s,p); return RedirectResponse(f"/studies/{s.id}",303)
@app.post("/participant-invitations/{invitation_id}/revoke")
def revoke_participant_invite(invitation_id:int,u=Depends(roles("owner","admin","researcher")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    inv = resolve_org_scoped_invitation(db, u.organisation_id, invitation_id)
    if not inv: raise HTTPException(404)
    require_study_permission(db,u,study(db,inv.study_id,u.organisation_id),edit=True)
    mark_invitation_revoked(inv, now()); db.commit(); return RedirectResponse(f"/studies/{inv.study_id}",303)
@app.post("/participant-invitations/{invitation_id}/resend")
def resend_participant_invite(invitation_id:int,u=Depends(roles("owner","admin","researcher")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    inv = resolve_org_scoped_invitation(db, u.organisation_id, invitation_id)
    if not inv: raise HTTPException(404)
    require_study_permission(db,u,study(db,inv.study_id,u.organisation_id),edit=True)
    mark_invitation_revoked(inv, now()); send_participant_invite(db,u,study(db,inv.study_id,u.organisation_id),participant(db,inv.participant_id,u.organisation_id)); return RedirectResponse(f"/studies/{inv.study_id}",303)

@app.get("/join-study",response_class=HTMLResponse)
def join_study(request:Request,token:str="",db:Session=Depends(get_db)):
    if token:
        inv = resolve_invitation_by_token(db, token)
        valid=bool(inv and not inv.revoked_at and unexpired(inv.expires_at))
        if not valid:
            return render(request,"join_study.html",invitation=None,study=None,participant=None,valid=False)
        if not inv.opened_at:
            inv.opened_at=now()
        raw_session = create_public_auth_session(
            db,
            scope=PUBLIC_SCOPE_PARTICIPANT_PORTAL,
            ttl_seconds=12 * 60 * 60,
            participant_invitation_id=inv.id,
        )
        db.commit()
        destination = "/participant-portal" if inv.accepted_at else "/join-study"
        response = RedirectResponse(destination, 303)
        set_public_auth_cookie(response, raw_session, 12 * 60 * 60)
        return response

    session_row = get_public_auth_session(request, db, PUBLIC_SCOPE_PARTICIPANT_PORTAL)
    if not session_row:
        return render(request,"join_study.html",invitation=None,study=None,participant=None,valid=False)
    inv = db.get(ParticipantInvitation, session_row.participant_invitation_id)
    valid=bool(inv and not inv.revoked_at and unexpired(inv.expires_at))
    s=db.get(Study,inv.study_id) if valid else None
    p=db.get(Participant,inv.participant_id) if valid else None
    if valid and inv.accepted_at:
        return RedirectResponse("/participant-portal",303)
    return render(request,"join_study.html",invitation=inv,study=s,participant=p,valid=valid)
@app.post("/join-study")
def accept_study(request:Request,token:str=Form(""),consent:bool=Form(False),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    session_row = get_public_auth_session(request, db, PUBLIC_SCOPE_PARTICIPANT_PORTAL)
    inv = resolve_participant_invitation(db, session_row)
    account_key = f"invitation:{inv.id}" if inv else (token_hash(token) if token else "missing")
    _enforce_rate_limit(
        request,
        db,
        scope="participant_invitation_accept",
        ip_limit=settings.rate_limit_invitation_accept_ip,
        account_key=account_key,
        account_limit=settings.rate_limit_invitation_accept_token,
    )
    if not inv or inv.revoked_at or not unexpired(inv.expires_at):
        raise HTTPException(400,"This participant link is invalid or expired.")
    if not consent: raise HTTPException(400,"Consent is required.")
    p=db.get(Participant,inv.participant_id); grant_participant_consent(inv, p, now()); audit(db,inv.organisation_id,None,"participant.invitation_accepted","participant",p.id); db.commit(); return RedirectResponse("/participant-portal",303)
@app.get("/participant-portal",response_class=HTMLResponse)
def participant_portal(request:Request,token:str="",db:Session=Depends(get_db)):
    if token:
        return RedirectResponse(f"/join-study?token={token}",303)
    session_row = get_public_auth_session(request, db, PUBLIC_SCOPE_PARTICIPANT_PORTAL)
    if not session_row:
        return RedirectResponse("/join-study",303)
    inv = resolve_participant_invitation(db, session_row)
    if not inv or inv.revoked_at or not unexpired(inv.expires_at):
        return RedirectResponse("/join-study",303)
    if not inv.accepted_at: return RedirectResponse("/join-study",303)
    s=db.get(Study,inv.study_id); p=db.get(Participant,inv.participant_id); acts=db.scalars(select(Activity).where(Activity.study_id==s.id).order_by(Activity.position)).all(); activity_windows={a.id:activity_window(s,a) for a in acts}; responses={r.activity_id:r for r in db.scalars(select(ActivityResponse).where(ActivityResponse.study_id==s.id,ActivityResponse.participant_id==p.id)).all()}; response_values={}
    for activity_id,response in responses.items():
        try: response_values[activity_id]=json.loads(response.value_json or "{}")
        except json.JSONDecodeError: response_values[activity_id]={}
    msgs = list_participant_visible_messages(db, study_id=s.id, participant_id=p.id); return render(request,"participant_portal.html",study=s,participant=p,activities=acts,activity_windows=activity_windows,responses=responses,response_values=response_values,messages=msgs)
@app.post("/participant-portal/activity/{activity_id}")
async def submit_activity(request: Request, activity_id:int,token:str=Form(""),action:str=Form("submit"),answer:str=Form(""),choices:str=Form(""),upload:UploadFile|None=File(None),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    session_row = get_public_auth_session(request, db, PUBLIC_SCOPE_PARTICIPANT_PORTAL)
    inv = resolve_participant_invitation(db, session_row)
    account_key = f"invitation:{inv.id}" if inv else (token_hash(token) if token else "missing")
    _enforce_rate_limit(
        request,
        db,
        scope="participant_portal_write",
        ip_limit=settings.rate_limit_portal_write_ip,
        account_key=account_key,
        account_limit=settings.rate_limit_portal_write_token,
    )
    if not inv or inv.revoked_at or not unexpired(inv.expires_at) or not inv.accepted_at:
        raise HTTPException(400,"This participant link is invalid or expired.")
    a=db.scalar(select(Activity).where(Activity.id==activity_id,Activity.study_id==inv.study_id));
    if not a: raise HTTPException(404)
    s=db.get(Study,inv.study_id)
    window=activity_window(s,a)
    if window["status"] == "upcoming":
        raise HTTPException(409,"This activity is not available yet.")
    if window["status"] == "closed":
        raise HTTPException(409,"The due date for this activity has passed.")
    r = resolve_or_create_activity_response(
        db,
        organisation_id=inv.organisation_id,
        study_id=inv.study_id,
        activity_id=a.id,
        participant_id=inv.participant_id,
    )
    value, choice_list = serialise_response_payload(answer, choices)
    stored_key = None
    if upload and upload.filename:
        original=Path(upload.filename).name
        extension=Path(original).suffix.lower()
        allowed_extensions={x.strip().lower() for x in settings.allowed_upload_extensions.split(",") if x.strip()}
        if extension not in allowed_extensions:
            raise HTTPException(400,"This file type is not permitted.")
        try:
            stored=storage.save_stream(upload.file,original,settings.max_upload_mb*1024*1024)
        except ValueError as exc:
            raise HTTPException(413,str(exc))
        stored_key = stored.key
        try:
            if stored.provider == "local":
                path=storage.path(stored.key)
                scan_status,scan_detail=scan_file(path)
                if scan_status=="infected":
                    delete_stored_object_safely(stored.key, "infected")
                    stored_key = None
                    db.rollback()
                    audit(db,inv.organisation_id,None,"evidence.rejected","activity",a.id,scan_detail)
                    db.commit()
                    raise HTTPException(400,"The uploaded file failed malware screening.")
            else:
                scan_status,scan_detail="pending","Awaiting Microsoft Defender for Storage on-upload scan."
            ev = build_evidence_file(
                organisation_id=inv.organisation_id,
                study_id=inv.study_id,
                activity_id=a.id,
                participant_id=inv.participant_id,
                response_id=r.id,
                original_name=original,
                stored_name=stored.key,
                content_type=upload.content_type or "application/octet-stream",
                size_bytes=stored.size,
                sha256_hex=stored.sha256_hex,
                scan_status=scan_status,
                scan_detail=scan_detail,
                storage_provider=stored.provider,
                blob_uri=stored.uri,
            ); db.add(ev); db.flush(); value["evidence_id"]=ev.id
        except Exception:
            if stored_key:
                delete_stored_object_safely(stored_key, "upload_processing_failed")
                stored_key = None
            db.rollback()
            raise
    try:
        if a.required and action=="submit" and not answer.strip() and not choice_list and not upload: raise HTTPException(400,"A response is required.")
        apply_response_action(r, value, action, now()); audit(db,inv.organisation_id,None,f"activity.{r.status}","activity_response",r.id,str(a.id)); db.commit()
    except Exception:
        db.rollback()
        if stored_key:
            delete_stored_object_safely(stored_key, "database_write_failed")
        raise
    return RedirectResponse("/participant-portal",303)
@app.post("/participant-portal/message")
def participant_message(request: Request, token:str=Form(""),body:str=Form(...),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    session_row = get_public_auth_session(request, db, PUBLIC_SCOPE_PARTICIPANT_PORTAL)
    inv = resolve_participant_invitation(db, session_row)
    account_key = f"invitation:{inv.id}" if inv else (token_hash(token) if token else "missing")
    _enforce_rate_limit(
        request,
        db,
        scope="participant_portal_write",
        ip_limit=settings.rate_limit_portal_write_ip,
        account_key=account_key,
        account_limit=settings.rate_limit_portal_write_token,
    )
    if not inv or inv.revoked_at or not unexpired(inv.expires_at) or not inv.accepted_at:
        raise HTTPException(400,"This participant link is invalid or expired.")
    if not body.strip(): raise HTTPException(400,"Message cannot be empty.")
    db.add(create_participant_message(inv, body=body)); db.commit(); return RedirectResponse("/participant-portal#messages",303)


@app.post("/api/v1/participant/session/exchange", response_model=SessionExchangeResponse)
def participant_api_session_exchange(
    payload: SessionExchangeRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    account_key = token_hash(payload.invitation_token) if payload.invitation_token else "missing"
    _enforce_rate_limit(
        request,
        db,
        scope="participant_api_session_exchange",
        ip_limit=settings.rate_limit_invitation_accept_ip,
        account_key=account_key,
        account_limit=settings.rate_limit_invitation_accept_token,
    )

    invitation = resolve_invitation_by_token(db, payload.invitation_token)
    if not invitation or invitation.revoked_at or not unexpired(invitation.expires_at):
        raise HTTPException(400, "This participant link is invalid or expired.")
    participant_row = db.get(Participant, invitation.participant_id)
    if not participant_row:
        raise HTTPException(400, "This participant link is invalid or expired.")

    existing_sessions = list(
        db.scalars(
            select(PublicAuthSession).where(
                PublicAuthSession.scope == PARTICIPANT_API_SCOPE,
                PublicAuthSession.participant_invitation_id == invitation.id,
                PublicAuthSession.revoked_at.is_(None),
            )
        )
    )
    for row in existing_sessions:
        if unexpired(row.expires_at):
            raise _participant_api_exchange_conflict()
        row.revoked_at = now()

    try:
        raw_token, session_row = create_participant_api_session(
            db,
            participant_invitation_id=invitation.id,
            ttl_seconds=settings.session_max_age_seconds,
        )
    except IntegrityError:
        db.rollback()
        raise _participant_api_exchange_conflict()
    next_action = "portal" if invitation.accepted_at else "consent_required"
    invitation_status = "accepted" if invitation.accepted_at else "valid"
    audit(
        db,
        invitation.organisation_id,
        None,
        "participant.api_session_exchanged",
        "participant_invitation",
        invitation.id,
        next_action,
    )
    db.commit()
    _cache_control_no_store(response)
    return SessionExchangeResponse(
        session=BearerSession(
            access_token=raw_token,
            token_type="Bearer",
            expires_at=session_row.expires_at,
            revocable=True,
        ),
        participant=ParticipantSummary(
            participant_id=participant_row.id,
            display_name=participant_row.name,
            consent_status=participant_row.consent_status,
        ),
        invitation=InvitationContext(
            study_id=invitation.study_id,
            invitation_status=invitation_status,
            expires_at=invitation.expires_at,
            accepted_at=invitation.accepted_at,
        ),
        next_action=next_action,
    )


@app.get("/api/v1/participant/session", response_model=ParticipantSessionResponse)
def participant_api_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    session_row, invitation, participant_row = _resolve_participant_api_context(request, db)
    _cache_control_no_store(response)
    return ParticipantSessionResponse(
        session=SessionInfo(
            expires_at=session_row.expires_at,
            revocable=True,
        ),
        participant=ParticipantSummary(
            participant_id=participant_row.id,
            display_name=participant_row.name,
            consent_status=participant_row.consent_status,
        ),
        study_scope=[invitation.study_id],
    )


@app.get("/api/v1/participant/studies", response_model=StudyListResponse)
def participant_api_studies(
    request: Request,
    response: Response,
    cursor: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    _session_row, invitation, participant_row = _resolve_participant_api_context(request, db)
    if not invitation.accepted_at:
        raise HTTPException(403, "Participant consent has not been accepted.")

    _enforce_rate_limit(
        request,
        db,
        scope="participant_portal_read",
        ip_limit=settings.rate_limit_portal_write_ip,
        account_key=f"invitation:{invitation.id}",
        account_limit=settings.rate_limit_portal_write_token,
    )

    study_row = db.scalar(
        select(Study).where(
            Study.id == invitation.study_id,
            Study.organisation_id == invitation.organisation_id,
        )
    )
    if not study_row:
        raise _participant_api_unauthorised()

    enrolled = db.scalar(
        select(StudyEnrolment.id).where(
            StudyEnrolment.organisation_id == invitation.organisation_id,
            StudyEnrolment.study_id == invitation.study_id,
            StudyEnrolment.participant_id == participant_row.id,
        )
    ) is not None

    _cache_control_no_store(response)
    return StudyListResponse(
        data=[
            StudySummary(
                study_id=study_row.id,
                title=study_row.title,
                description=study_row.description,
                status=study_row.status,
                methodology=study_row.methodology,
                enrolled=enrolled,
            )
        ],
        pagination=Pagination(
            cursor=cursor,
            next_cursor=None,
            limit=limit,
            has_more=False,
        ),
    )


@app.delete("/api/v1/participant/session", response_model=LogoutResponse)
def participant_api_session_logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    session_row, invitation, _participant_row = _resolve_participant_api_context(request, db)
    session_row.revoked_at = now()
    audit(
        db,
        invitation.organisation_id,
        None,
        "participant.api_session_revoked",
        "public_auth_session",
        session_row.id,
        PARTICIPANT_API_SCOPE,
    )
    db.commit()
    _cache_control_no_store(response)
    return LogoutResponse(revoked=True, revoked_at=session_row.revoked_at)


@app.post("/participants/{participant_id}/message")
def researcher_message(participant_id:int,study_id:int=Form(...),body:str=Form(...),internal_note:bool=Form(False),u=Depends(roles("owner","admin","researcher")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    p=participant(db,participant_id,u.organisation_id); s=study(db,study_id,u.organisation_id); require_study_permission(db,u,s,edit=True)
    enrolment = db.scalar(select(StudyEnrolment.id).where(StudyEnrolment.organisation_id==u.organisation_id,StudyEnrolment.study_id==s.id,StudyEnrolment.participant_id==p.id))
    if not enrolment:
        raise HTTPException(400,"Participant is not enrolled in this study.")
    if not body.strip(): raise HTTPException(400,"Message cannot be empty.")
    db.add(create_researcher_message(organisation_id=u.organisation_id,study_id=s.id,participant_id=p.id,sender_user_id=u.id,body=body,internal_note=internal_note)); audit(db,u.organisation_id,u.id,"message.created","participant",p.id,"internal" if internal_note else s.title); db.commit(); return RedirectResponse(f"/participants/{p.id}#messages",303)
@app.get("/evidence/{evidence_id}")
def evidence(evidence_id:int,u=Depends(current_user),db:Session=Depends(get_db)):
    e = resolve_org_scoped_evidence(db, u.organisation_id, evidence_id)
    if not e: raise HTTPException(404)
    require_study_permission(db,u,study(db,e.study_id,u.organisation_id))
    if e.storage_provider == "azure_blob":
        latest_status, latest_detail = storage.scan_result(e.stored_name)
        if latest_status != "pending" or e.scan_status == "pending":
            e.scan_status, e.scan_detail = latest_status, latest_detail
            if latest_status in {"clean", "infected", "scan_failed"}: e.scan_completed_at = now()
            db.commit()
        ensure_clean_scan_for_download(e.scan_status)
        return RedirectResponse(storage.download_url(e.stored_name,e.original_name,e.content_type,settings.azure_sas_minutes),303)
    ensure_clean_scan_for_download(e.scan_status)
    path=storage.path(e.stored_name)
    if not path.exists(): raise HTTPException(404,"Stored evidence is unavailable.")
    return FileResponse(path,media_type=e.content_type,filename=e.original_name)

@app.post("/webhooks/defender-storage")
async def defender_storage_webhook(request: Request, db: Session = Depends(get_db)):
    """Receive Event Grid validation and Defender for Storage scan-result events."""
    configured = (settings.azure_defender_webhook_secret or "").strip()
    supplied = request.headers.get("x-pcip-webhook-secret") or request.query_params.get("secret")
    if hosted_environment() and not configured:
        log_webhook_rejection(request, "missing_server_secret")
        raise HTTPException(503, "Webhook authentication is not configured.")
    if (hosted_environment() or configured) and not supplied:
        log_webhook_rejection(request, "unsigned")
        raise HTTPException(401, "Missing webhook signature.")
    if configured and not secrets.compare_digest(configured, supplied or ""):
        log_webhook_rejection(request, "invalid_signature")
        raise HTTPException(401, "Invalid webhook secret.")
    payload = await request.json()
    events = payload if isinstance(payload, list) else [payload]
    for event in events:
        event_type = str(event.get("eventType") or event.get("type") or "")
        data = event.get("data") or {}
        if event_type == "Microsoft.EventGrid.SubscriptionValidationEvent":
            return JSONResponse({"validationResponse": data.get("validationCode")})
        blob_uri = str(data.get("blobUri") or data.get("blobURL") or data.get("url") or "")
        raw_result = str(data.get("scanResultType") or data.get("scanResult") or data.get("malwareScanResult") or "")
        if not blob_uri or not raw_result:
            continue
        row = db.scalar(select(EvidenceFile).where(EvidenceFile.blob_uri == blob_uri))
        if not row:
            # Some Event Grid payloads encode the URI; the persisted URI remains the safest lookup.
            continue
        result = raw_result.strip().lower()
        if result == "no threats found": row.scan_status = "clean"
        elif result == "malicious": row.scan_status = "infected"
        elif result in {"error", "not scanned"}: row.scan_status = "scan_failed"
        else: row.scan_status = "pending"
        detail = data.get("scanResultDetails")
        row.scan_detail = json.dumps(detail) if isinstance(detail, (dict, list)) else str(detail or raw_result)
        row.scan_completed_at = now()
        audit(db,row.organisation_id,None,"evidence.defender_scan","evidence_file",row.id,row.scan_status)
    db.commit()
    return {"accepted": True}

@app.post("/studies/{study_id}/access")
def set_study_access(study_id:int,user_id:int=Form(...),permission:str=Form(...),u=Depends(roles("owner","admin")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    s=study(db,study_id,u.organisation_id)
    target=db.scalar(select(User).join(OrganisationMembership, OrganisationMembership.user_id==User.id).where(User.id==user_id,OrganisationMembership.organisation_id==u.organisation_id,OrganisationMembership.is_active==True,User.is_active==True))
    if not target: raise HTTPException(404,"Researcher not found.")
    if permission not in {"none","view","edit"}: raise HTTPException(400,"Invalid study permission.")
    row=db.scalar(select(StudyAccess).where(StudyAccess.study_id==s.id,StudyAccess.user_id==target.id))
    if permission=="none":
        if row: db.delete(row)
    elif row:
        row.permission=permission
    else:
        db.add(StudyAccess(organisation_id=u.organisation_id,study_id=s.id,user_id=target.id,permission=permission,created_by_id=u.id))
    audit(db,u.organisation_id,u.id,"study.access_updated","study",s.id,f"{target.email}:{permission}")
    db.commit()
    return RedirectResponse(f"/studies/{s.id}#team-access",303)

@app.get("/researchers",response_class=HTMLResponse)
def researchers(request:Request,u=Depends(roles("owner","admin")),db:Session=Depends(get_db)):
    membership_rows=db.execute(select(User,OrganisationMembership).join(OrganisationMembership,OrganisationMembership.user_id==User.id).where(OrganisationMembership.organisation_id==u.organisation_id).order_by(User.name)).all(); users=[CurrentUser(identity,membership) for identity,membership in membership_rows]; invs=db.scalars(select(Invitation).where(Invitation.organisation_id==u.organisation_id).order_by(Invitation.created_at.desc())).all(); return render(request,"researchers.html",user=u,users=users,invitations=invs,roles=[x.value for x in Role])
@app.post("/researchers/invite")
def invite_researcher(name:str=Form(...),email:str=Form(...),role:str=Form("researcher"),u=Depends(roles("owner","admin")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    enum_value(role,Role,"role"); email=email.lower().strip()
    existing_user=db.scalar(select(User).where(func.lower(User.email)==email))
    if existing_user and db.scalar(select(OrganisationMembership.id).where(OrganisationMembership.user_id==existing_user.id,OrganisationMembership.organisation_id==u.organisation_id)): raise HTTPException(400,"This person already belongs to the organisation.")
    live=db.scalar(select(Invitation.id).where(Invitation.organisation_id==u.organisation_id,Invitation.email==email,Invitation.accepted_at.is_(None),Invitation.revoked_at.is_(None),Invitation.expires_at>now()))
    if live: raise HTTPException(400,"A live invitation already exists.")
    raw=new_token(); inv=Invitation(organisation_id=u.organisation_id,email=email,name=name.strip(),role=role,token_hash=token_hash(raw),expires_at=now()+timedelta(hours=48),invited_by_id=u.id); db.add(inv); db.flush(); queue_email(db,u.organisation_id,email,"Citizen Centric by Politis: Activate your account",f"Activate your Citizen Centric account: {settings.base_url}/accept-invitation?token={raw}"); db.commit(); return RedirectResponse("/researchers",303)


@app.post("/researchers/{user_id}/disable")
def disable_researcher_account(user_id:int,u=Depends(roles("owner","admin")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    row = db.execute(select(User,OrganisationMembership).join(OrganisationMembership,OrganisationMembership.user_id==User.id).where(User.id==user_id,OrganisationMembership.organisation_id==u.organisation_id)).first()
    if not row:
        raise HTTPException(404, "User not found.")
    target, membership = row
    if target.id == u.id:
        raise HTTPException(400, "You cannot disable your own account.")
    if membership.is_active:
        membership.is_active = False
        bump_session_version(target)
        audit(db,u.organisation_id,u.id,"auth.account_disabled","user",target.id,target.email)
    db.commit()
    return RedirectResponse("/researchers",303)


@app.post("/researchers/{user_id}/reset-password")
def admin_reset_researcher_password(user_id:int,u=Depends(roles("owner","admin")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    target = db.scalar(select(User).join(OrganisationMembership,OrganisationMembership.user_id==User.id).where(User.id==user_id,OrganisationMembership.organisation_id==u.organisation_id,OrganisationMembership.is_active==True))
    if not target:
        raise HTTPException(404, "User not found.")
    if not target.is_active:
        raise HTTPException(400, "Disabled accounts cannot receive reset links.")
    raw = new_token()
    db.add(PasswordReset(user_id=target.id, token_hash=token_hash(raw), expires_at=now()+timedelta(hours=1)))
    target.failed_login_count = 0
    target.locked_until = None
    bump_session_version(target)
    queue_email(
        db,
        u.organisation_id,
        target.email,
        "Citizen Centric by Politis: Reset your password",
        f"Reset your Citizen Centric password: {settings.base_url}/reset-password?token={raw}",
    )
    audit(db,u.organisation_id,u.id,"auth.admin_password_reset","user",target.id,target.email)
    db.commit()
    return RedirectResponse("/researchers",303)
@app.get("/accept-invitation",response_class=HTMLResponse)
def accept_page(request:Request,token:str="",db:Session=Depends(get_db)):
    if token:
        if token_already_redeemed(db, PUBLIC_SCOPE_RESEARCHER_INVITE, token):
            return render(request,"accept.html",invitation=None,valid=False)
        inv=db.scalar(select(Invitation).where(Invitation.token_hash==token_hash(token)))
        valid=bool(inv and not inv.accepted_at and not inv.revoked_at and unexpired(inv.expires_at))
        if not valid:
            return render(request,"accept.html",invitation=None,valid=False)
        raw_session = create_public_auth_session(
            db,
            scope=PUBLIC_SCOPE_RESEARCHER_INVITE,
            ttl_seconds=60 * 60,
            invitation_id=inv.id,
        )
        record_token_redemption(db, PUBLIC_SCOPE_RESEARCHER_INVITE, token)
        db.commit()
        response = RedirectResponse("/accept-invitation", 303)
        set_public_auth_cookie(response, raw_session, 60 * 60)
        return response

    session_row = get_public_auth_session(request, db, PUBLIC_SCOPE_RESEARCHER_INVITE)
    if not session_row:
        return render(request,"accept.html",invitation=None,valid=False)
    inv = db.get(Invitation, session_row.invitation_id)
    valid = bool(inv and not inv.accepted_at and not inv.revoked_at and unexpired(inv.expires_at))
    existing_identity = bool(
        valid
        and db.scalar(
            select(User.id).where(
                func.lower(User.email) == inv.email.lower()
            )
        )
    )
    return render(
        request,
        "accept.html",
        invitation=inv,
        valid=valid,
        existing_identity=existing_identity,
    )
@app.post("/accept-invitation")
def accept_invitation(request: Request, token:str=Form(""),password:str=Form(...),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    session_row = get_public_auth_session(request, db, PUBLIC_SCOPE_RESEARCHER_INVITE)
    inv_for_limit = db.get(Invitation, session_row.invitation_id) if session_row else None
    account_key = f"invitation:{inv_for_limit.id}" if inv_for_limit else (token_hash(token) if token else "missing")
    _enforce_rate_limit(
        request,
        db,
        scope="researcher_invitation_accept",
        ip_limit=settings.rate_limit_invitation_accept_ip,
        account_key=account_key,
        account_limit=settings.rate_limit_invitation_accept_token,
        organisation_id=inv_for_limit.organisation_id if inv_for_limit else None,
    )
    if not session_row:
        raise HTTPException(400,"Invitation invalid or expired.")
    inv = db.get(Invitation, session_row.invitation_id)
    if not inv or inv.accepted_at or inv.revoked_at or not unexpired(inv.expires_at): raise HTTPException(400,"Invitation invalid or expired.")
    if len(password)<10: raise HTTPException(400,"Password must contain at least 10 characters.")
    u=db.scalar(select(User).where(func.lower(User.email)==inv.email.lower()))
    if u:
        if not u.is_active or not u.password_hash or not verify_password(password,u.password_hash):
            raise HTTPException(400,"Use the password for your existing account.")
        if db.scalar(select(OrganisationMembership.id).where(OrganisationMembership.user_id==u.id,OrganisationMembership.organisation_id==inv.organisation_id)):
            raise HTTPException(400,"This account already belongs to the organisation.")
    else:
        u=User(organisation_id=inv.organisation_id,name=inv.name,email=inv.email,password_hash=hash_password(password),role=inv.role); db.add(u); db.flush()
    add_organisation_membership(db,u,inv.organisation_id,inv.role)
    inv.accepted_at=now(); session_row.revoked_at = now(); db.commit(); r=RedirectResponse("/",303); r.set_cookie("session",encode_session(u.id, u.session_version, inv.organisation_id),httponly=True,samesite="strict",secure=settings.cookie_secure,max_age=43200); clear_public_auth_cookie(r); return r
@app.post("/invitations/{invitation_id}/revoke")
def revoke_researcher_invite(invitation_id:int,u=Depends(roles("owner","admin")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    inv=db.scalar(select(Invitation).where(Invitation.id==invitation_id,Invitation.organisation_id==u.organisation_id));
    if not inv: raise HTTPException(404)
    inv.revoked_at=now(); db.commit(); return RedirectResponse("/researchers",303)

@app.get("/audit",response_class=HTMLResponse)
def audit_page(request:Request,page:int=1,u=Depends(roles("owner","admin")),db:Session=Depends(get_db)):
    rows,total,pages=paginate(select(AuditEvent).where(AuditEvent.organisation_id==u.organisation_id).order_by(AuditEvent.created_at.desc()),db,page,50); return render(request,"audit.html",user=u,events=rows,page=page,pages=pages,total=total)
@app.get("/outbox",response_class=HTMLResponse)
def outbox(request:Request,page:int=1,u=Depends(roles("owner","admin")),db:Session=Depends(get_db)):
    rows,total,pages=paginate(select(OutboxEmail).where(OutboxEmail.organisation_id==u.organisation_id).order_by(OutboxEmail.created_at.desc()),db,page,50); return render(request,"outbox.html",user=u,rows=rows,smtp_enabled=bool(settings.smtp_host),page=page,pages=pages,total=total)
