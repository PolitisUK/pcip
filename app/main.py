from datetime import datetime, timedelta, timezone
from pathlib import Path
from contextlib import asynccontextmanager
import asyncio
import os
import re
import logging
import time
import csv, io, json, secrets
from collections import OrderedDict, deque
from threading import Lock
from urllib.parse import urlencode
from .csrf import get_csrf_token, csrf_protect
from fastapi import FastAPI, Request, Form, Depends, HTTPException, UploadFile, File, Response, Query, Header, Path as ApiPath
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select, func, or_, and_, case, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .config import settings, validate_runtime_settings
from .db import Base, engine, get_db, SessionLocal
from .models import (
    Activity,
    ActivityResponse,
    AuditEvent,
    DemoImportStatus,
    ConsentStatus,
    EvidenceConfidenceAssessment,
    EvidenceFile,
    Invitation,
    Organisation,
    OrganisationMembership,
    OutboxEmail,
    Participant,
    ParticipantAppAccessCode,
    ParticipantInvitation,
    ParticipantMessage,
    ParticipantPrivacyRequest,
    ParticipantStatus,
    PasswordReset,
    Project,
    ProjectStatus,
    ResearchAnalysisSuggestion,
    ResearchTheme,
    PublicAuthSession,
    PublicTokenExchange,
    Role,
    Study,
    StudyAccess,
    StudyEnrolment,
    StudyGovernance,
    StudyMethodologyConfiguration,
    StudyStatus,
    User,
)
from .security import hash_password, verify_password, new_token, token_hash, encode_session, decode_session
from .services import audit, purge_expired_outbox, queue_email
from .research_intelligence import (
    create_confidence_assessment,
    review_confidence_assessment,
    review_suggestion,
)
from .evidence_explorer import evidence_items, filter_evidence
from .research_api import (
    EvidenceExplorerResponse,
    EvidenceItemResponse,
    QuoteFinderResponse,
    ThemeListResponse,
    ThemeResponse,
)
from .theme_explorer import create_theme, parse_suggestion_ids
from .research_workspace import response_body, response_codes, response_context, code_counts
from .storage import storage
from .privacy_lifecycle import process_deletion_request, revoke_participant_access
from .scanner import scan_file
from .entra import oauth, configured as entra_configured
from .observability import configure_observability
from .legal_content import (
    CONTACT_EMAIL,
    LegalDocument,
    LegalSection,
    CUSTOMER_LEGAL_DOCUMENTS,
    customer_legal_document,
    participant_policy_documents,
    public_legal_document,
)
from .study_governance import (
    ASSESSMENT_STATES,
    FEATURES,
    SPECIAL_CATEGORY_STATES,
    study_document_references,
    study_launch_readiness,
)
from .study_consent import (
    bind_invitation_to_current_bundle,
    create_or_reuse_current_bundle,
    current_bundle_documents,
    require_bound_documents,
)
from .methodology import (
    MethodologyGateViolation,
    controlled_methodology_for_canonical,
    library_records,
    methodology_library,
    source_metadata,
    validate_configuration,
)
from .demo_data.rivermere import (
    CHAPEL_PROJECT_CODE,
    CONTENT_VERSION as RIVERMERE_CONTENT_VERSION,
    EVERYDAY_PROJECT_CODE,
    RIVERMERE_SLUG,
    rivermere_verification_completed_at,
)
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
    ActivityAvailability,
    ActivityDetailResponse,
    ActivityDetailResponseItem,
    EvidenceMetadata,
    EvidenceStatusResponse,
    EvidenceUploadResponse,
    DraftResponseRequest,
    DraftResponseResult,
    EntryLocation,
    ActivityListResponse,
    ActivityResponseSummary,
    ActivityResponseValue,
    ActivitySummary,
    AvailableStudyListResponse,
    BearerSession,
    CreateMessageRequest,
    CreateMessageResponse,
    DeletionRequest,
    InvitationContext,
    LegalDocumentReference,
    LogoutResponse,
    MessageListResponse,
    Pagination,
    ParticipantMessageSummary,
    ParticipantProfile,
    ParticipantSessionResponse,
    ParticipantSummary,
    PrivacyRequestAcknowledgement,
    PortalResponseItem,
    PortalSummaryResponse,
    ConsentAcceptanceRequest,
    ConsentAcceptanceResponse,
    SessionExchangeRequest,
    SessionExchangeResponse,
    SessionSwitchRequest,
    SessionInfo,
    SubmissionHistoryItem,
    SubmissionEvidenceItem,
    SubmissionHistoryResponse,
    SubmitResponseRequest,
    SubmittedResponseResult,
    StudyListResponse,
    StudyLegalDocumentsResponse,
    StudySummary,
    UpdateParticipantProfileRequest,
    WithdrawalRequest,
)

VERSION = "0.6.0"
# Set by the image build from Dockerfile's VCS_REF argument. This is deliberately
# non-sensitive: release verification uses it to distinguish the serving image
# from an older container that may still answer requests during replacement.
APPLICATION_REVISION = os.environ.get("APP_REVISION", "unknown")
# App Service setting changes can be applied while an older container still
# serves traffic. Capture the release-attempt generation during process import,
# rather than reading it for each request, so readiness proves this process was
# started after that generation was configured.
STARTUP_GENERATION = os.environ.get("RELEASE_STARTUP_GENERATION", "unknown")
BASE = Path(__file__).resolve().parent
configure_observability(settings)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    startup()
    retention_task = asyncio.create_task(_outbox_retention_worker())
    try:
        yield
    finally:
        retention_task.cancel()
        try:
            await retention_task
        except asyncio.CancelledError:
            pass


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


async def _outbox_retention_worker():
    """Apply the short mail-retention policy while the application is live."""
    while True:
        await asyncio.sleep(60 * 60)
        try:
            with SessionLocal() as db:
                purge_expired_outbox(db)
                db.commit()
        except Exception:
            logger.exception("outbox_retention_cleanup_failed")



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


class SensitiveAccessLogFilter(logging.Filter):
    """Remove bearer-style query values before request paths reach access logs."""

    _query_secret = re.compile(
        r"(?i)([?&](?:token|invitation_token|access_token)=)[^&\s]*"
    )

    @classmethod
    def redact(cls, value: object) -> object:
        rendered = str(value)
        redacted = cls._query_secret.sub(r"\1[REDACTED]", rendered)
        return redacted if redacted != rendered else value

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(self.redact(value) for value in record.args)
        elif isinstance(record.args, dict):
            record.args = {
                key: self.redact(value) for key, value in record.args.items()
            }
        record.msg = self.redact(record.msg)
        return True


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
    for logger_name in ("uvicorn.access", "httpx", "httpcore"):
        request_logger = logging.getLogger(logger_name)
        if not any(isinstance(item, SensitiveAccessLogFilter) for item in request_logger.filters):
            request_logger.addFilter(SensitiveAccessLogFilter())


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
        "not_scanned": "failed",
        "not_configured": "failed",
        "error": "failed",
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
UPLOAD_CONTENT_TYPES = {
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".webp": {"image/webp"},
    ".mp3": {"audio/mpeg", "audio/mp3"},
    ".wav": {"audio/wav", "audio/x-wav"},
    ".m4a": {"audio/mp4", "audio/x-m4a"},
    ".mp4": {"video/mp4"},
    ".mov": {"video/quicktime"},
    ".pdf": {"application/pdf"},
    ".doc": {"application/msword"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".txt": {"text/plain"},
    ".csv": {"text/csv", "application/csv", "text/plain"},
}


def validate_evidence_upload_metadata(filename: str, content_type: str | None, activity_type: str | None = None):
    extension = Path(filename).suffix.lower()
    allowed_extensions = {x.strip().lower() for x in settings.allowed_upload_extensions.split(",") if x.strip()}
    if extension not in allowed_extensions:
        raise HTTPException(415, "This file type is not permitted.")
    declared_type = (content_type or "application/octet-stream").split(";", 1)[0].strip().lower()
    expected_types = UPLOAD_CONTENT_TYPES.get(extension)
    if expected_types and declared_type not in expected_types and declared_type != "application/octet-stream":
        raise HTTPException(415, "The file extension and content type do not match.")
    required_prefix = {"photo": "image/", "audio": "audio/", "video": "video/"}.get(activity_type or "")
    if required_prefix and not declared_type.startswith(required_prefix):
        raise HTTPException(415, f"This activity requires a {activity_type} file.")


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

def optional_current_user(request: Request, db: Session = Depends(get_db)):
    identity = decode_session(request.cookies.get("session", ""))

    if not identity:
        return None

    u = db.get(User, identity.user_id)

    if not u or not u.is_active:
        return None

    if u.session_version != identity.session_version:
        return None

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
    return None


def current_user(request: Request, db: Session = Depends(get_db)):
    u = optional_current_user(request, db)
    if u:
        return u
    raise HTTPException(303, headers={"Location": "/login"})

def roles(*allowed):
    def dep(u=Depends(current_user)):
        if u.role not in allowed: raise HTTPException(403, "Insufficient permission")
        return u
    return dep


def platform_admin(u=Depends(current_user)):
    """Restrict global operations to explicitly provisioned Politis staff.

    Organisation roles are intentionally insufficient: returning a generic
    not-found response also avoids confirming that a platform view exists to
    customer accounts.
    """
    if not u.is_platform_admin:
        raise HTTPException(404, "Not found.")
    return u


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
            "response_body": response_body,
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


def governance_for_study(db: Session, study_row: Study) -> StudyGovernance | None:
    return db.scalar(
        select(StudyGovernance).where(
            StudyGovernance.organisation_id == study_row.organisation_id,
            StudyGovernance.study_id == study_row.id,
        )
    )


def methodology_configuration_for_study(db: Session, study_row: Study) -> StudyMethodologyConfiguration | None:
    return db.scalar(
        select(StudyMethodologyConfiguration).where(
            StudyMethodologyConfiguration.organisation_id == study_row.organisation_id,
            StudyMethodologyConfiguration.study_id == study_row.id,
        )
    )


def document_reference(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""
    if (
        cleaned.startswith("/")
        or cleaned.lower().startswith("file:")
        or re.match(r"^[A-Za-z]:[\\/]", cleaned)
        or ".." in cleaned
        or any(ord(char) < 32 for char in cleaned)
    ):
        raise HTTPException(400, f"{label} must be a public reference, not an internal path.")
    return cleaned


def capture_consent_document_evidence(invitation: ParticipantInvitation, governance: StudyGovernance | None) -> None:
    """Snapshot controller-approved references once; historical consent is immutable."""
    if invitation.accepted_at or invitation.consent_bundle_id or governance is None:
        return
    for item in study_document_references(governance):
        prefix = item.document_type
        setattr(invitation, f"{prefix}_reference", item.reference)
        setattr(invitation, f"{prefix}_version", item.version)
        setattr(invitation, f"{prefix}_effective_date", item.effective_date)


def require_study_launch_ready(db: Session, study_row: Study) -> None:
    readiness = study_launch_readiness(governance_for_study(db, study_row))
    outstanding = list(readiness.missing) + list(readiness.review_required)
    methodology_configuration = methodology_configuration_for_study(db, study_row)
    if methodology_configuration is None or not methodology_configuration.researcher_confirmed_at:
        outstanding.append("researcher-confirmed methodology and analysis configuration")
    if not outstanding:
        return
    raise HTTPException(
        400,
        "Study launch readiness is not complete: " + ", ".join(outstanding) + ".",
    )

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


def project_studies_for_user(db: Session, user: User, project_row: Project) -> list[Study]:
    """Return studies visible through the same rules used by project navigation."""
    stmt = select(Study).where(
        Study.organisation_id == user.organisation_id,
        Study.project_id == project_row.id,
    )
    if user.role not in {"owner", "admin", "observer"}:
        stmt = stmt.where(Study.id.in_(study_scope_for_user(user)))
    return db.scalars(stmt.order_by(Study.created_at.asc())).all()


def project_workspace_scope(db: Session, user: User, project_id: int) -> tuple[Project, list[Study]]:
    project_row = project(db, project_id, user.organisation_id)
    require_project_permission(db, user, project_row)
    return project_row, project_studies_for_user(db, user, project_row)


def protocol_builder_options() -> dict[str, list[dict[str, str]]]:
    """The ordinary researcher UI: five non-competing protocol dimensions."""
    def option(identifier: str, label: str, description: str, supports: str) -> dict[str, str]:
        return {
            "id": identifier,
            "label": label,
            "description": description,
            "supports": supports,
        }

    return {
        "research_philosophies": [
            option("interpretivist_constructivist", "Interpretivist / constructivist", "Knowledge is understood as socially situated and constructed through people's interpretations, interactions and lived experience.", "contextual and meaning-centred inquiry, reflexive interpretation and multiple situated accounts."),
            option("positivist_postpositivist", "Positivist / post-positivist", "Knowledge is developed through systematic observation, measurement and the testing or refinement of explanations.", "structured observation, comparison and inference; post-positivist work also recognises uncertainty, measurement limits and researcher fallibility."),
            option("pragmatist", "Pragmatist", "Methodological choices are guided by the research question, practical consequences and the usefulness of the resulting knowledge.", "purposeful combinations of qualitative and quantitative methods where they help address the question."),
            option("critical_transformative", "Critical / transformative", "Inquiry examines how power, inequality and exclusion shape experience, while attending to possibilities for change.", "collaborative and justice-oriented inquiry, positional reflexivity and attention to whose knowledge is centred."),
            option("realist_critical_realist", "Realist / critical realist", "What is observed is considered in relation to the underlying mechanisms and contexts that may generate it.", "explanation across contexts, careful use of theory and analysis of how causal processes may differ."),
            option("other", "Other", "Use this where an established named philosophical position is important to the protocol but is not listed above.", "a clear written rationale and appropriate alignment between the stated perspective, design and analysis."),
            option("not_specified", "Not specified / not sure", "Use this when the study does not adopt an explicit philosophical position or it is not yet settled.", "transparent protocol development without implying that a paradigm has been selected."),
        ],
        "research_designs": [
            option("ethnography", "Ethnography", "A sustained study of practices, relationships and meaning within a social or organisational setting.", "contextual observation, field engagement and interpretation of everyday practice."),
            option("case_study", "Case study", "An in-depth examination of a bounded case, programme, place, organisation or event in its context.", "multiple sources of evidence, contextual explanation and careful case boundaries."),
            option("grounded_theory", "Grounded theory", "An iterative design that develops an explanatory account through systematic engagement with data.", "theoretical sampling, constant comparison and progressively focused conceptual development."),
            option("phenomenological", "Phenomenological / experiential research", "An inquiry into how people experience and make sense of a particular phenomenon.", "rich accounts of lived experience, careful interpretation and attention to the researcher's standpoint."),
            option("narrative_inquiry", "Narrative inquiry", "An exploration of how people construct and communicate experience through stories over time and across contexts.", "attention to chronology, plot, voice and the social setting of storytelling."),
            option("participatory_action", "Participatory / action research", "A collaborative approach in which participants and researchers investigate concerns while seeking practical change.", "shared decision-making, iterative action and reflection, and explicit attention to power."),
            option("mixed_methods", "Mixed-methods study", "A planned integration of qualitative and quantitative evidence within one coherent study.", "intentional sequencing, complementarity and transparent integration rather than parallel data collection alone."),
            option("evaluation", "Evaluation", "A systematic assessment of the design, implementation, outcomes or value of a programme, service or intervention.", "clear evaluative questions, relevant criteria and context-sensitive interpretation of findings."),
            option("survey_quantitative", "Survey / quantitative study", "A structured study of variables, patterns or associations across a defined population or sample.", "operationalised measures, sampling rationale and appropriate descriptive or inferential analysis."),
            option("other", "Other", "Use this for a recognised design that is material to the protocol but not represented above.", "a concise explanation of its logic, boundaries and relationship to the planned evidence and analysis."),
            option("not_specified", "Not specified / not sure", "Use this while the design remains genuinely undecided rather than selecting an inaccurate label.", "a clear record that further methodological clarification is still required."),
        ],
        "evidence_methods": [
            option("interviews", "Interviews", "Purposeful conversations that elicit participants' accounts, experiences or interpretations.", "topic guides, informed follow-up and an interview-recording and transcription plan where relevant."),
            option("focus_groups", "Focus groups", "Facilitated group discussion that examines shared, contested or socially negotiated views.", "careful group composition, facilitation and analysis of interaction as well as stated opinion."),
            option("observation", "Observation", "Systematic attention to practices, events, settings or interactions as they occur.", "fieldnotes, an observer role and a clear account of access, reactivity and context."),
            option("diaries", "Participant diaries / repeated entries", "Repeated participant-created records of experience, activity or reflection over time.", "longitudinal insight, a realistic submission rhythm and support for changing circumstances."),
            option("questionnaires", "Questionnaires / surveys", "Structured questions designed to collect comparable responses across participants or occasions.", "clear constructs, accessible wording, sampling decisions and planned handling of missing data."),
            option("photos", "Photos / visual material", "Participant-created or researcher-collected visual material considered as evidence in its social context.", "consent and safeguarding for identifiable people or places, contextual captions and visual interpretation."),
            option("audio", "Audio / voice notes", "Recorded spoken accounts, soundscapes or other audio material submitted or collected for the study.", "informed recording choices, transcription or listening plans and management of identifiable voices."),
            option("documents", "Documents / archival material", "Existing written, administrative or historical materials analysed as situated records.", "provenance, authorship, purpose and the conditions under which documents were produced and retained."),
            option("files", "Participant-submitted files", "Files supplied by participants as part of their account or evidence for the study.", "clear file guidance, proportionate security controls and review of personal or third-party information."),
            option("secondary_data", "Existing / secondary data", "Data originally collected for another purpose and reused under an appropriate governance basis.", "provenance review, fitness for purpose, access controls and documented limitations."),
            option("other", "Other", "Use this where a material evidence source is not represented above.", "a specific collection plan, relevant consent or permissions and a clear analytical role."),
        ],
        "analysis_approaches": [
            option("reflexive_thematic", "Reflexive thematic analysis", "An interpretive approach to developing patterns of shared meaning through active researcher engagement with the material.", "reflexive memoing, iterative theme development and transparent researcher judgement rather than coding-reliability claims."),
            option("codebook_thematic", "Codebook / coding-reliability thematic analysis", "A structured thematic approach using a defined coding framework that may be applied across analysts or cases.", "codebook development, documented coding procedures and reliability assessment only where methodologically justified."),
            option("content_analysis", "Qualitative content analysis", "A systematic interpretation of manifest and, where appropriate, latent content within a defined corpus.", "transparent categorisation, attention to context and a clear account of how categories were developed."),
            option("framework_analysis", "Framework analysis", "A matrix-based approach that organises data by cases and themes while preserving links to the original accounts.", "applied policy or service research, comparison across cases and an auditable analytic framework."),
            option("grounded_theory_analysis", "Grounded-theory analysis", "Iterative comparison and conceptual development aimed at producing an explanatory account grounded in the data.", "constant comparison, memoing and theoretically informed refinement of emerging categories."),
            option("ipa", "Interpretative phenomenological analysis (IPA)", "An idiographic, interpretative exploration of how people make sense of significant lived experience.", "small, purposive samples, detailed case analysis and a double-hermeneutic account of interpretation."),
            option("narrative_analysis", "Narrative analysis", "Analysis of stories as accounts shaped by sequence, voice, audience and social context.", "attention to temporality, plot, turning points and how stories are told as well as what they contain."),
            option("discourse_analysis", "Discourse analysis", "Analysis of language and meaning-making in relation to the practices and contexts in which discourse is used.", "close attention to wording, interactional context and the effects of particular ways of framing an issue."),
            option("critical_discourse_analysis", "Critical discourse analysis", "A critical examination of how language, representation and institutional practice can reproduce or challenge power.", "explicit theoretical positioning, analysis of power relations and reflexive interpretation of texts or talk."),
            option("conversation_analysis", "Conversation analysis", "Detailed analysis of the organisation of naturally occurring interaction, including sequence, timing and turn-taking.", "high-quality recordings or transcripts and close examination of interaction rather than retrospective accounts alone."),
            option("descriptive_statistics", "Descriptive statistical analysis", "Numerical summarisation of distributions, frequencies, central tendency or variation in the observed data.", "clear variable definitions, appropriate denominators and transparent presentation of uncertainty or missingness."),
            option("inferential_statistics", "Inferential statistical analysis", "Statistical estimation or testing used to assess patterns beyond the observed sample under stated assumptions.", "a sampling and analysis plan, assumption checks and cautious interpretation of uncertainty."),
            option("mixed_methods_integration", "Mixed-methods integration", "Deliberate bringing together of qualitative and quantitative findings to develop a combined interpretation.", "planned points of integration, explicit handling of convergence or divergence and coherent meta-inferences."),
            option("other", "Other", "Use this for a recognised analytic approach not listed above.", "a concise account of its analytic logic, required materials and relationship to the study design."),
            option("not_yet_decided", "Not yet decided", "Use this when analysis is genuinely still being developed, not as a substitute for a completed analysis plan.", "a documented decision point before analysis or AI-supported research functions are enabled."),
        ],
        "theoretical_orientations": [
            option("feminist", "Feminist", "A framework that examines gendered power relations, knowledge and lived experience.", "attention to standpoint, care, representation and the distribution of power in research relationships."),
            option("intersectional", "Intersectional", "A framework for examining how intersecting social positions and systems of power shape experience and opportunity.", "analysis that avoids treating categories as isolated and attends to structural as well as lived inequalities."),
            option("critical_race", "Critical race", "A framework that examines how racism and racialisation are embedded in social, institutional and legal arrangements.", "historically informed analysis, attention to structural racism and careful treatment of racialised knowledge and experience."),
            option("indigenous", "Indigenous", "Approaches grounded in Indigenous knowledge, sovereignty, relationships and community authority.", "appropriate governance, community-led decision-making and respect for relevant data sovereignty principles."),
            option("decolonising", "Decolonising", "An approach that questions colonial assumptions in knowledge production and seeks more accountable research relationships.", "reflexive scrutiny of power, meaningful participation and avoidance of extractive research practices."),
            option("postcolonial", "Postcolonial", "A framework that examines the continuing cultural, political and epistemic effects of colonial histories.", "attention to representation, historical context and uneven global or institutional power relations."),
            option("poststructural", "Poststructural", "A perspective that examines how meanings, identities and categories are produced and contested through discourse and practice.", "analysis of instability, difference, categorisation and the power effects of taken-for-granted terms."),
            option("postqualitative", "Postqualitative", "An experimental orientation that rethinks conventional qualitative assumptions about representation, method and the human subject.", "careful theoretical grounding, methodological openness and explicit consideration of what counts as data or analysis."),
            option("new_materialist", "New materialist", "A perspective that attends to how human and non-human material relations participate in events and meaning-making.", "analysis of materiality, affect, environment and distributed agency alongside human accounts."),
            option("photovoice", "Photovoice", "A participatory visual approach in which people use photographs to document and discuss their experiences or concerns.", "participant control over images, facilitated reflection and robust safeguarding for identifiable people and places."),
            option("other", "Other", "Use this for a material theoretical or specialist framework not listed above.", "a clear account of its relevance and how it will shape interpretation without mechanically determining method."),
        ],
    }


def _protocol_values(values: list[str], section: str) -> list[str]:
    allowed = {item["id"] for item in protocol_builder_options()[section]}
    selected = sorted(set(values))
    if not set(selected).issubset(allowed):
        raise HTTPException(400, "Invalid protocol-builder selection.")
    return selected


def _protocol_value(value: str, section: str) -> str:
    allowed = {item["id"] for item in protocol_builder_options()[section]}
    if value not in allowed:
        raise HTTPException(400, "Invalid protocol-builder selection.")
    return value


def controlled_methodology_for_design(design: str, analysis: list[str]) -> str:
    """Derive a controlled AI guard only from an unambiguous current choice.

    The researcher-facing design and analysis dimensions deliberately do not
    expose controlled-library identifiers.  This table is the audited bridge
    between them; its values must match the published knowledge-base records.
    Multiple analysis approaches are not silently collapsed into one method.
    """
    return controlled_methodology_for_canonical(design, analysis)


def has_canonical_methodology_values(configuration: StudyMethodologyConfiguration) -> bool:
    """Whether a configuration has already been saved through the canonical UI."""
    return any((
        configuration.research_philosophy not in {"", "not_specified"},
        configuration.research_design not in {"", "not_specified"},
        bool(configuration.secondary_design),
        configuration.evidence_methods_json not in {"", "[]"},
        configuration.analysis_approaches_json not in {"", "[]"},
        configuration.theoretical_orientations_json not in {"", "[]"},
    ))


def preserve_legacy_methodology_metadata(configuration: StudyMethodologyConfiguration) -> None:
    """Snapshot pre-0021 controlled fields before replacing current grounding.

    Those fields may contain labels from an older importer that are not current
    controlled-library identifiers.  Keeping a lossless source record prevents
    historical provenance from becoming a hidden, revalidated form input.
    """
    if has_canonical_methodology_values(configuration):
        return
    historical = {
        "primary_methodology_id": configuration.primary_methodology_id,
        "methodology_variant": configuration.methodology_variant,
        "secondary_methodologies_json": configuration.secondary_methodologies_json,
        "legacy_methodology_json": configuration.legacy_methodology_json,
    }
    if not any(value not in {"", "[]"} for value in historical.values()):
        return
    configuration.legacy_methodology_json = json.dumps(
        {"pre_0021_controlled_methodology": historical},
        sort_keys=True,
    )


def study_consent_display(enrolment: StudyEnrolment, participant_row: Participant, invitation: ParticipantInvitation | None) -> dict[str, object]:
    """Return a current, study-scoped consent state without erasing history."""
    accepted_at = invitation.accepted_at if invitation else None
    historical_acceptance = accepted_at.strftime("%d %b %Y") if accepted_at else ""
    withdrawn = (
        enrolment.status == "withdrawn"
        or participant_row.status == ParticipantStatus.withdrawn.value
        or participant_row.consent_status == ConsentStatus.withdrawn.value
    )
    if withdrawn:
        return {"label": "Withdrawn", "invitation_label": "Withdrawn", "style": "withdrawn", "historical_acceptance": historical_acceptance}
    if invitation is None:
        return {"label": "Awaiting study consent", "invitation_label": "Not sent", "style": "pending", "historical_acceptance": ""}
    if invitation.revoked_at:
        return {"label": "Revoked", "invitation_label": "Revoked", "style": "withdrawn", "historical_acceptance": historical_acceptance}
    if not unexpired(invitation.expires_at):
        return {"label": "Expired", "invitation_label": "Expired", "style": "pending", "historical_acceptance": historical_acceptance}
    if accepted_at:
        return {"label": "Consented for this study", "invitation_label": "Accepted", "style": "active", "historical_acceptance": ""}
    return {"label": "Awaiting study consent", "invitation_label": "Pending", "style": "pending", "historical_acceptance": ""}


def study_design_summaries(db: Session, organisation_id: int, study_ids: list[int]) -> dict[int, str]:
    """Present canonical design data without exposing the legacy Study.methodology field."""
    if not study_ids:
        return {}
    labels = {
        section: {item["id"]: item["label"] for item in values}
        for section, values in protocol_builder_options().items()
    }
    rows = db.scalars(select(StudyMethodologyConfiguration).where(
        StudyMethodologyConfiguration.organisation_id == organisation_id,
        StudyMethodologyConfiguration.study_id.in_(study_ids),
    )).all()
    result = {}
    for row in rows:
        design = labels["research_designs"].get(row.research_design or "", "")
        evidence = [labels["evidence_methods"].get(value, value) for value in json.loads(row.evidence_methods_json or "[]")]
        analysis = [labels["analysis_approaches"].get(value, value) for value in json.loads(row.analysis_approaches_json or "[]")]
        parts = ([f"Design: {design}"] if design and design != "Not specified / not sure" else [])
        if evidence:
            parts.append("Evidence: " + ", ".join(evidence))
        if analysis:
            parts.append("Analysis: " + ", ".join(analysis))
        result[row.study_id] = " · ".join(parts) or "Legacy methodology metadata"
    return result


def _workspace_entry_statement(user: User, study_ids: list[int]):
    return (
        select(ActivityResponse, Participant, Activity)
        .join(Participant, Participant.id == ActivityResponse.participant_id)
        .join(Activity, Activity.id == ActivityResponse.activity_id)
        .where(
            ActivityResponse.organisation_id == user.organisation_id,
            ActivityResponse.study_id.in_(study_ids),
            ActivityResponse.status == "submitted",
        )
    )


def project_workspace_entries(
    db: Session,
    user: User,
    studies: list[Study],
    *,
    participant_id: int | None = None,
    prompt_id: int | None = None,
    code: str = "",
    q: str = "",
    date_from: str = "",
    date_to: str = "",
    evidence: str = "all",
    newest_first: bool = True,
    page: int = 1,
    per_page: int = 30,
) -> tuple[list[dict], int, int]:
    """Page source entries while prefetching only their related research context."""
    study_ids = [row.id for row in studies]
    if not study_ids:
        return [], 0, 0
    stmt = _workspace_entry_statement(user, study_ids)
    if participant_id:
        stmt = stmt.where(ActivityResponse.participant_id == participant_id)
    if prompt_id:
        stmt = stmt.where(ActivityResponse.activity_id == prompt_id)
    if q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(or_(ActivityResponse.value_json.ilike(term), Activity.prompt.ilike(term), Activity.title.ilike(term)))
    if code.strip():
        # Codes are intentionally stored in flexible response payloads today.
        # SQL narrowing avoids materialising an entire project before parsing.
        stmt = stmt.where(ActivityResponse.value_json.ilike(f"%{code.strip()}%"))
    for raw, comparison in ((date_from, ">="), (date_to, "<=")):
        if raw:
            try:
                parsed = datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
            except ValueError:
                raise HTTPException(422, "Dates must use YYYY-MM-DD.")
            if comparison == ">=":
                stmt = stmt.where(ActivityResponse.submitted_at >= parsed)
            else:
                stmt = stmt.where(ActivityResponse.submitted_at < parsed + timedelta(days=1))
    evidence_exists = select(EvidenceFile.id).where(
        EvidenceFile.organisation_id == user.organisation_id,
        EvidenceFile.response_id == ActivityResponse.id,
    ).exists()
    if evidence == "yes":
        stmt = stmt.where(evidence_exists)
    elif evidence == "no":
        stmt = stmt.where(~evidence_exists)
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    ordering = ActivityResponse.submitted_at.desc() if newest_first else ActivityResponse.submitted_at.asc()
    rows = db.execute(stmt.order_by(ordering, ActivityResponse.id.desc()).offset((page - 1) * per_page).limit(per_page)).all()
    response_ids = [response.id for response, _, _ in rows]
    evidence_by_response: dict[int, list[EvidenceFile]] = {}
    if response_ids:
        for item in db.scalars(select(EvidenceFile).where(EvidenceFile.organisation_id == user.organisation_id, EvidenceFile.response_id.in_(response_ids)).order_by(EvidenceFile.created_at)).all():
            evidence_by_response.setdefault(item.response_id, []).append(item)
    items = []
    wanted_code = code.strip().casefold()
    for response, participant_row, activity in rows:
        codes = response_codes(response.value_json)
        if wanted_code and not any(wanted_code in item.casefold() for item in codes):
            # The SQL prefilter is intentionally broad; preserve exact code filtering.
            continue
        body = response_body(response.value_json)
        items.append({
            "response": response, "participant": participant_row, "activity": activity,
            "body": body, "codes": codes, "context": response_context(response.value_json),
            "evidence": evidence_by_response.get(response.id, []),
        })
    return items, total, max(1, (total + per_page - 1) // per_page)


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


def apply_participant_withdrawal(
    db: Session,
    invitation: ParticipantInvitation,
    participant_row: Participant,
    scope: str,
):
    study_id = invitation.study_id if scope == "study" else None
    revoke_participant_access(
        db,
        organisation_id=invitation.organisation_id,
        participant_id=participant_row.id,
        study_id=study_id,
    )
    enrolments = list(
        db.scalars(
            select(StudyEnrolment).where(
                StudyEnrolment.organisation_id == invitation.organisation_id,
                StudyEnrolment.participant_id == participant_row.id,
                *([StudyEnrolment.study_id == study_id] if study_id is not None else []),
            )
        )
    )
    if scope == "all":
        participant_row.consent_status = ConsentStatus.withdrawn.value
        participant_row.status = ParticipantStatus.withdrawn.value
    return enrolments


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


def _participant_switchable_studies(
    db: Session,
    invitation: ParticipantInvitation,
    participant_row: Participant,
) -> list[tuple[ParticipantInvitation, Study]]:
    """Return only study invitations that are independently safe to enter.

    A participant API token remains bound to one invitation.  This helper is
    intentionally stricter than a participant lookup: every selectable study
    needs its own accepted, unrevoked invitation and an active enrolment.
    """
    if not invitation.accepted_at:
        raise HTTPException(403, "Participant consent has not been accepted.")
    if participant_row.consent_status != ConsentStatus.granted.value:
        raise HTTPException(403, "Participant consent is no longer active.")

    rows = db.execute(
        select(ParticipantInvitation, Study)
        .join(
            Study,
            and_(
                Study.id == ParticipantInvitation.study_id,
                Study.organisation_id == ParticipantInvitation.organisation_id,
            ),
        )
        .join(
            StudyEnrolment,
            and_(
                StudyEnrolment.organisation_id == ParticipantInvitation.organisation_id,
                StudyEnrolment.study_id == ParticipantInvitation.study_id,
                StudyEnrolment.participant_id == ParticipantInvitation.participant_id,
                StudyEnrolment.status != "withdrawn",
            ),
        )
        .where(
            ParticipantInvitation.organisation_id == invitation.organisation_id,
            ParticipantInvitation.participant_id == participant_row.id,
            ParticipantInvitation.accepted_at.is_not(None),
            ParticipantInvitation.revoked_at.is_(None),
        )
        .order_by(Study.title.asc(), ParticipantInvitation.created_at.desc())
    ).all()
    active = [(candidate, study_row) for candidate, study_row in rows if unexpired(candidate.expires_at)]

    # There should be one live accepted invitation per study.  Do not choose
    # arbitrarily if historical invitation state has become inconsistent.
    by_study_id: dict[int, tuple[ParticipantInvitation, Study]] = {}
    for candidate, study_row in active:
        if study_row.id in by_study_id:
            raise HTTPException(409, "Participant study access configuration is invalid.")
        by_study_id[study_row.id] = (candidate, study_row)
    return list(by_study_id.values())


def _participant_session_exchange_response(
    raw_token: str,
    session_row: PublicAuthSession,
    invitation: ParticipantInvitation,
    participant_row: Participant,
) -> SessionExchangeResponse:
    return SessionExchangeResponse(
        session=BearerSession(
            access_token=raw_token,
            token_type="Bearer",
            expires_at=session_row.expires_at,
            revocable=True,
        ),
        participant=ParticipantSummary(
            display_name=participant_row.name,
            consent_status=participant_row.consent_status,
        ),
        invitation=InvitationContext(
            study_id=invitation.study_id,
            invitation_status="accepted" if invitation.accepted_at else "valid",
            expires_at=invitation.expires_at,
            accepted_at=invitation.accepted_at,
            requires_study_documents=invitation.consent_bundle_id is not None,
        ),
        next_action="portal" if invitation.accepted_at else "consent_required",
    )


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
        purge_expired_outbox(db)
        db.commit()
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
    return {
        "status": "ready",
        "version": VERSION,
        "revision": APPLICATION_REVISION,
        "startup_generation": STARTUP_GENERATION,
    }


def _rivermere_completion_payload(db: Session) -> dict[str, object]:
    completed_at = rivermere_verification_completed_at(db)
    status = db.get(DemoImportStatus, "rivermere")
    return {
        "dataset": "rivermere",
        "content_version": RIVERMERE_CONTENT_VERSION,
        "verified": completed_at is not None,
        "verified_at": completed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if completed_at else None,
        "import_status": status.status if status else "not_started",
        "current_phase": status.phase if status else "not_started",
        "error_category": status.error_category if status else None,
        "started_at": status.started_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if status and status.started_at else None,
        "committed_at": status.committed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if status and status.committed_at else None,
    }


@app.get("/api/v1/rivermere/verification")
def rivermere_verification_signal(db: Session = Depends(get_db)):
    """Non-sensitive durable signal for the protected release workflow."""
    return _rivermere_completion_payload(db)


@app.get("/api/v1/platform/rivermere/verification")
def platform_rivermere_verification_signal(
    u=Depends(platform_admin),
    db: Session = Depends(get_db),
):
    """Platform-admin read-only status without disclosing any account identifier."""
    payload = _rivermere_completion_payload(db)
    organisation = db.scalar(select(Organisation).where(Organisation.slug == RIVERMERE_SLUG))
    membership = db.scalar(select(OrganisationMembership).where(
        OrganisationMembership.user_id == u.id,
        OrganisationMembership.organisation_id == organisation.id,
    )) if organisation else None
    payload["current_platform_admin_owner_access"] = bool(
        membership and membership.is_active and membership.role == "owner"
    )
    payload["project_counts"] = {
        code: int(db.scalar(select(func.count(Project.id)).where(
            Project.organisation_id == organisation.id, Project.code == code,
        )) or 0) if organisation else 0
        for code in (EVERYDAY_PROJECT_CODE, CHAPEL_PROJECT_CODE)
    }
    return payload


@app.get("/privacy", response_class=HTMLResponse)
@app.get("/terms", response_class=HTMLResponse)
@app.get("/cookies", response_class=HTMLResponse)
@app.get("/accessibility", response_class=HTMLResponse)
@app.get("/acceptable-use", response_class=HTMLResponse)
@app.get("/data-rights", response_class=HTMLResponse)
@app.get("/consent", response_class=HTMLResponse)
def public_legal_page(request: Request):
    legal_slug = request.url.path.lstrip("/")
    document = public_legal_document(legal_slug)
    if document is None:
        raise HTTPException(404)
    if not document.is_published:
        response = render(
            request,
            "legal_unavailable.html",
            document=document,
            contact_email=CONTACT_EMAIL,
        )
        response.status_code = 503
        return response
    return render(
        request,
        "legal_document.html",
        document=document,
        legal_version=document.version,
        legal_effective_date=document.effective_date,
    )


@app.get("/legal", response_class=HTMLResponse)
def public_legal_centre(request: Request):
    return render(
        request,
        "legal_centre.html",
        documents=participant_policy_documents(),
    )


@app.get("/legal-information", response_class=HTMLResponse)
def legacy_legal_information(request: Request):
    return RedirectResponse("/legal", 308)


@app.get("/contact", response_class=HTMLResponse)
@app.get("/support", response_class=HTMLResponse)
def public_support_page(request: Request):
    document = LegalDocument(
        document_id="support",
        title="Citizen Centric support",
        summary="How to get support for the Citizen Centric platform or a study.",
        audience="public and participant",
        publication_status="published",
        source_file="app/legal_sources/canonical/legal_information_v1.md",
        sections=(
            LegalSection(
                "Support contact",
                (
                    "For Citizen Centric support, contact info@politisconsulting.co.uk.",
                    "For a question about a specific study, use the contact details supplied by the research organisation.",
                ),
            ),
        ),
    )
    return render(
        request,
        "legal_document.html",
        document=document,
        legal_version=document.version,
        legal_effective_date=document.effective_date,
    )


@app.get("/agreements", response_class=HTMLResponse)
def customer_agreements(request: Request, u=Depends(roles("owner", "admin"))):
    """Customer-only legal schedules; participant credentials cannot reach it."""
    return render(
        request,
        "customer_agreements.html",
        user=u,
        documents=tuple(CUSTOMER_LEGAL_DOCUMENTS.values()),
    )


@app.get("/agreements/{legal_slug}", response_class=HTMLResponse)
def customer_agreement(
    request: Request,
    legal_slug: str,
    u=Depends(roles("owner", "admin")),
):
    document = customer_legal_document(legal_slug)
    if document is None:
        raise HTTPException(404)
    return render(
        request,
        "customer_legal_document.html",
        user=u,
        document=document,
        legal_version=document.version,
        legal_effective_date=document.effective_date,
    )


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
def dashboard(request:Request,u=Depends(optional_current_user),db:Session=Depends(get_db)):
    if not u:
        return render(request, "public_home.html")
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
    return render(request,"dashboard.html",user=u,metrics=metrics,studies=studies,project_map=pmap,onboarding=onboarding,recent_events=recent_events,study_design_summaries=study_design_summaries(db, o, [row.id for row in studies]))


@app.get("/admin", response_class=HTMLResponse)
def platform_admin_dashboard(
    request: Request,
    u=Depends(platform_admin),
    db: Session = Depends(get_db),
):
    """Small, deliberately separate operational overview for Politis staff."""
    organisation_rows = db.execute(
        select(
            Organisation,
            func.count(func.distinct(Study.id)).label("study_count"),
            func.count(func.distinct(Participant.id)).label("participant_count"),
        )
        .outerjoin(Study, Study.organisation_id == Organisation.id)
        .outerjoin(
            Participant,
            Participant.organisation_id == Organisation.id,
        )
        .group_by(Organisation.id)
        .order_by(Organisation.name)
    ).all()
    audit(
        db,
        u.organisation_id,
        u.id,
        "platform_admin.dashboard_viewed",
        "platform",
        "admin",
    )
    db.commit()
    return render(
        request,
        "platform_admin.html",
        user=u,
        organisations=organisation_rows,
        ai_governance={
            "provider": "Azure-approved server-side services only",
            "deployment": settings.azure_openai_deployment if settings.azure_openai_endpoint else "No active model deployment configured",
            "region": settings.ai_processing_region,
            "grounding": f"Enabled · methodology library {settings.methodology_library_version}",
            "retrieval": settings.ai_retrieval_provider,
            "participant_training": settings.participant_training_allowed,
            "shared_training": settings.shared_model_training_allowed,
            "cross_customer_learning": settings.cross_customer_learning_allowed,
        },
    )


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
    return render(request,"project_detail.html",user=u,project=p,studies=studies,statuses=[x.value for x in StudyStatus],can_edit=permission=="manage",study_design_summaries=study_design_summaries(db, u.organisation_id, [row.id for row in studies]))


def _workspace_context(project_row: Project, studies: list[Study]) -> dict:
    return {"project": project_row, "workspace_studies": studies}


def page_url(request: Request, page: int) -> str:
    params = dict(request.query_params)
    params["page"] = str(page)
    return f"{request.url.path}?{urlencode(params)}"


@app.get("/projects/{project_id}/workspace", response_class=HTMLResponse)
def project_workspace(project_id: int, request: Request, u=Depends(current_user), db: Session = Depends(get_db)):
    project_row, studies = project_workspace_scope(db, u, project_id)
    study_ids = [row.id for row in studies]
    counts = {"participants": 0, "entries": 0, "evidence": 0}
    date_range = (None, None)
    recent_entries: list[dict] = []
    themes = []
    if study_ids:
        counts["participants"] = int(db.scalar(select(func.count(func.distinct(StudyEnrolment.participant_id))).where(StudyEnrolment.organisation_id == u.organisation_id, StudyEnrolment.study_id.in_(study_ids))) or 0)
        counts["entries"] = int(db.scalar(select(func.count(ActivityResponse.id)).where(ActivityResponse.organisation_id == u.organisation_id, ActivityResponse.study_id.in_(study_ids), ActivityResponse.status == "submitted")) or 0)
        counts["evidence"] = int(db.scalar(select(func.count(EvidenceFile.id)).where(EvidenceFile.organisation_id == u.organisation_id, EvidenceFile.study_id.in_(study_ids))) or 0)
        date_range = db.execute(select(func.min(ActivityResponse.submitted_at), func.max(ActivityResponse.submitted_at)).where(ActivityResponse.organisation_id == u.organisation_id, ActivityResponse.study_id.in_(study_ids), ActivityResponse.status == "submitted")).one()
        recent_entries, _, _ = project_workspace_entries(db, u, studies, page=1, per_page=5)
        themes = db.scalars(select(ResearchTheme).where(ResearchTheme.organisation_id == u.organisation_id, ResearchTheme.study_id.in_(study_ids)).order_by(ResearchTheme.updated_at.desc()).limit(6)).all()
    return render(request, "research_workspace.html", user=u, **_workspace_context(project_row, studies), counts=counts, date_range=date_range, recent_entries=recent_entries, themes=themes)


@app.get("/projects/{project_id}/workspace/entries", response_class=HTMLResponse)
def project_workspace_entries_page(
    project_id: int, request: Request, participant_id: int | None = Query(None, ge=1), prompt_id: int | None = Query(None, ge=1),
    code: str = Query("", max_length=120), q: str = Query("", max_length=200), date_from: str = Query("", max_length=10), date_to: str = Query("", max_length=10),
    evidence: str = Query("all", pattern="^(all|yes|no)$"), order: str = Query("newest", pattern="^(newest|oldest)$"), page: int = Query(1, ge=1),
    u=Depends(current_user), db: Session = Depends(get_db),
):
    project_row, studies = project_workspace_scope(db, u, project_id)
    items, total, pages = project_workspace_entries(db, u, studies, participant_id=participant_id, prompt_id=prompt_id, code=code, q=q, date_from=date_from, date_to=date_to, evidence=evidence, newest_first=order == "newest", page=page)
    study_ids = [row.id for row in studies]
    participant_rows = db.scalars(select(Participant).join(StudyEnrolment, StudyEnrolment.participant_id == Participant.id).where(Participant.organisation_id == u.organisation_id, StudyEnrolment.organisation_id == u.organisation_id, StudyEnrolment.study_id.in_(study_ids)).distinct().order_by(Participant.reference)).all() if study_ids else []
    prompts = db.scalars(select(Activity).where(Activity.organisation_id == u.organisation_id, Activity.study_id.in_(study_ids)).order_by(Activity.position, Activity.title)).all() if study_ids else []
    response_rows = db.scalars(select(ActivityResponse).where(ActivityResponse.organisation_id == u.organisation_id, ActivityResponse.study_id.in_(study_ids), ActivityResponse.status == "submitted").limit(5000)).all() if study_ids else []
    codes = [name for name, _ in code_counts(response_rows).most_common()]
    return render(request, "research_entries.html", user=u, **_workspace_context(project_row, studies), items=items, total=total, pages=pages, page=page, previous_url=page_url(request, page - 1) if page > 1 else None, next_url=page_url(request, page + 1) if page < pages else None, participant_rows=participant_rows, prompts=prompts, codes=codes, filters={"participant_id": participant_id, "prompt_id": prompt_id, "code": code, "q": q, "date_from": date_from, "date_to": date_to, "evidence": evidence, "order": order})


@app.get("/projects/{project_id}/workspace/participants", response_class=HTMLResponse)
def project_workspace_participants(project_id: int, request: Request, q: str = Query("", max_length=120), u=Depends(current_user), db: Session = Depends(get_db)):
    project_row, studies = project_workspace_scope(db, u, project_id)
    study_ids = [row.id for row in studies]
    stmt = select(Participant).join(StudyEnrolment, StudyEnrolment.participant_id == Participant.id).where(Participant.organisation_id == u.organisation_id, StudyEnrolment.organisation_id == u.organisation_id, StudyEnrolment.study_id.in_(study_ids)).distinct() if study_ids else select(Participant).where(False)
    if q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(or_(Participant.name.ilike(term), Participant.reference.ilike(term), Participant.tags.ilike(term)))
    rows = db.scalars(stmt.order_by(Participant.reference)).all()
    response_counts = dict(db.execute(select(ActivityResponse.participant_id, func.count(ActivityResponse.id)).where(ActivityResponse.organisation_id == u.organisation_id, ActivityResponse.study_id.in_(study_ids), ActivityResponse.status == "submitted").group_by(ActivityResponse.participant_id)).all()) if study_ids else {}
    return render(request, "research_participants.html", user=u, **_workspace_context(project_row, studies), participants=rows, response_counts=response_counts, q=q)


@app.get("/projects/{project_id}/workspace/evidence", response_class=HTMLResponse)
def project_workspace_evidence(project_id: int, request: Request, participant_id: int | None = Query(None, ge=1), page: int = Query(1, ge=1), u=Depends(current_user), db: Session = Depends(get_db)):
    project_row, studies = project_workspace_scope(db, u, project_id)
    study_ids = [row.id for row in studies]
    stmt = select(EvidenceFile).where(EvidenceFile.organisation_id == u.organisation_id, EvidenceFile.study_id.in_(study_ids)) if study_ids else select(EvidenceFile).where(False)
    if participant_id:
        stmt = stmt.where(EvidenceFile.participant_id == participant_id)
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    evidence_rows = db.scalars(stmt.order_by(EvidenceFile.created_at.desc()).offset((page - 1) * 36).limit(36)).all()
    participant_ids = {item.participant_id for item in evidence_rows}
    activity_ids = {item.activity_id for item in evidence_rows}
    response_ids = {item.response_id for item in evidence_rows if item.response_id}
    participants = {row.id: row for row in db.scalars(select(Participant).where(Participant.organisation_id == u.organisation_id, Participant.id.in_(participant_ids))).all()} if participant_ids else {}
    activities = {row.id: row for row in db.scalars(select(Activity).where(Activity.organisation_id == u.organisation_id, Activity.id.in_(activity_ids))).all()} if activity_ids else {}
    responses = {row.id: row for row in db.scalars(select(ActivityResponse).where(ActivityResponse.organisation_id == u.organisation_id, ActivityResponse.id.in_(response_ids))).all()} if response_ids else {}
    participant_rows = db.scalars(select(Participant).join(StudyEnrolment, StudyEnrolment.participant_id == Participant.id).where(Participant.organisation_id == u.organisation_id, StudyEnrolment.organisation_id == u.organisation_id, StudyEnrolment.study_id.in_(study_ids)).distinct().order_by(Participant.reference)).all() if study_ids else []
    return render(request, "research_evidence.html", user=u, **_workspace_context(project_row, studies), evidence_rows=evidence_rows, participants=participants, activities=activities, responses=responses, participant_rows=participant_rows, participant_id=participant_id, page=page, pages=max(1, (total + 35) // 36), total=total)


@app.get("/projects/{project_id}/workspace/themes", response_class=HTMLResponse)
def project_workspace_themes(project_id: int, request: Request, u=Depends(current_user), db: Session = Depends(get_db)):
    project_row, studies = project_workspace_scope(db, u, project_id)
    study_ids = [row.id for row in studies]
    responses = db.scalars(select(ActivityResponse).where(ActivityResponse.organisation_id == u.organisation_id, ActivityResponse.study_id.in_(study_ids), ActivityResponse.status == "submitted").limit(5000)).all() if study_ids else []
    counts = code_counts(responses)
    participants_by_code: dict[str, set[int]] = {}
    for response in responses:
        for item in response_codes(response.value_json):
            participants_by_code.setdefault(item, set()).add(response.participant_id)
    return render(request, "research_themes.html", user=u, **_workspace_context(project_row, studies), codes=counts.most_common(), participants_by_code=participants_by_code, source_limit_reached=len(responses) == 5000)


@app.get("/projects/{project_id}/workspace/analysis", response_class=HTMLResponse)
def project_workspace_analysis(project_id: int, request: Request, u=Depends(current_user), db: Session = Depends(get_db)):
    project_row, studies = project_workspace_scope(db, u, project_id)
    study_ids = [row.id for row in studies]
    themes = db.scalars(select(ResearchTheme).where(ResearchTheme.organisation_id == u.organisation_id, ResearchTheme.study_id.in_(study_ids)).order_by(ResearchTheme.updated_at.desc())).all() if study_ids else []
    suggestions = db.scalars(select(ResearchAnalysisSuggestion).where(ResearchAnalysisSuggestion.organisation_id == u.organisation_id, ResearchAnalysisSuggestion.study_id.in_(study_ids)).order_by(ResearchAnalysisSuggestion.created_at.desc()).limit(30)).all() if study_ids and settings.research_intelligence_enabled else []
    return render(request, "research_analysis.html", user=u, **_workspace_context(project_row, studies), themes=themes, suggestions=suggestions, ai_available=False)
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
    return render(request,"studies.html",user=u,studies=rows,projects=projects,enrolment_counts=counts,study_design_summaries=study_design_summaries(db, u.organisation_id, study_ids))
@app.post("/projects/{project_id}/studies")
def create_study(project_id:int,title:str=Form(...),code:str=Form(...),description:str=Form(""),methodology:str=Form("diary"),status_value:str=Form("draft"),u=Depends(roles("owner","admin","researcher")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    p=project(db,project_id,u.organisation_id); require_project_permission(db,u,p,edit=True); enum_value(status_value,StudyStatus,"study status")
    if methodology not in STUDY_METHODOLOGIES: raise HTTPException(400,"Invalid methodology.")
    if status_value == "live":
        raise HTTPException(400, "Configure study governance before making a study live.")
    cleaned_title=nonblank(title,"Study title",3); cleaned_code=nonblank(code,"Study code").upper(); s=Study(organisation_id=u.organisation_id,project_id=p.id,title=cleaned_title,code=cleaned_code,description=description.strip(),methodology=methodology,status=status_value,created_by_id=u.id); db.add(s)
    try: db.flush(); audit(db,u.organisation_id,u.id,"study.created","study",s.id,s.title); db.commit()
    except Exception: db.rollback(); raise HTTPException(400,"Study code must be unique.")
    return RedirectResponse(f"/studies/{s.id}",303)
@app.get("/studies/{study_id:int}",response_class=HTMLResponse)
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
    suggestions=db.scalars(select(ResearchAnalysisSuggestion).where(ResearchAnalysisSuggestion.organisation_id==u.organisation_id,ResearchAnalysisSuggestion.study_id==s.id).order_by(ResearchAnalysisSuggestion.created_at.desc()).limit(20)).all() if settings.research_intelligence_enabled else []
    confidence_assessments=db.scalars(select(EvidenceConfidenceAssessment).where(EvidenceConfidenceAssessment.organisation_id==u.organisation_id,EvidenceConfidenceAssessment.study_id==s.id).order_by(EvidenceConfidenceAssessment.created_at.desc()).limit(20)).all() if settings.research_intelligence_enabled and settings.research_intelligence_evidence_confidence_enabled else []
    governance = governance_for_study(db, s)
    methodology_configuration = methodology_configuration_for_study(db, s)
    participant_consent_states = {
        enrolment.participant_id: study_consent_display(
            enrolment,
            ps[enrolment.participant_id],
            latest.get(enrolment.participant_id),
        )
        for enrolment in ens
        if enrolment.participant_id in ps
    }
    methodology_record = None
    if methodology_configuration and methodology_configuration.primary_methodology_id:
        methodology_record = next((item for item in library_records() if item["methodology_id"] == methodology_configuration.primary_methodology_id), None)
    return render(request,"study_detail.html",user=u,study=s,project=p,activities=acts,enrolments=ens,participants=ps,available=available,latest_invites=latest,participant_consent_states=participant_consent_states,response_counts=response_counts,study_permission=permission,team=team,access_map=access_map,can_edit=permission in {"edit","manage"},activity_types=sorted(ACTIVITY_TYPES),research_intelligence_enabled=settings.research_intelligence_enabled,suggestions=suggestions,evidence_confidence_enabled=settings.research_intelligence_enabled and settings.research_intelligence_evidence_confidence_enabled,confidence_assessments=confidence_assessments,governance=governance,governance_readiness=study_launch_readiness(governance),governance_documents={document.document_type: document for document in current_bundle_documents(db, governance)},governance_features=sorted(FEATURES),governance_assessment_states=sorted(ASSESSMENT_STATES),governance_special_category_states=sorted(SPECIAL_CATEGORY_STATES),methodology_configuration=methodology_configuration,protocol_builder_options=protocol_builder_options(),methodology_record=methodology_record,methodology_sources=source_metadata(tuple(methodology_record["provenance"]) if methodology_record else ()),methodology_library_version=methodology_library()["library_version"],methodology_disagreements=methodology_library()["disagreements"])

@app.post("/studies/{study_id}/governance")
def update_study_governance(
    study_id: int,
    controller_name: str = Form(""),
    controller_privacy_contact: str = Form(""),
    sponsor_name: str = Form(""),
    research_contact: str = Form(""),
    participant_population: str = Form(""),
    data_categories: str = Form(""),
    special_category_data: str = Form("not_assessed"),
    article_6_lawful_basis: str = Form(""),
    article_9_condition: str = Form(""),
    participation_consent_configured: bool = Form(False),
    participant_information_available: bool = Form(False),
    privacy_information_available: bool = Form(False),
    participant_information_reference: str = Form(""),
    participant_information_version: str = Form(""),
    participant_information_effective_date: str = Form(""),
    privacy_notice_reference: str = Form(""),
    privacy_notice_version: str = Form(""),
    privacy_notice_effective_date: str = Form(""),
    consent_text_reference: str = Form(""),
    consent_text_version: str = Form(""),
    consent_text_effective_date: str = Form(""),
    participant_information_body: str = Form(""),
    privacy_notice_body: str = Form(""),
    consent_text_body: str = Form(""),
    retention_description: str = Form(""),
    deletion_retention_exception: str = Form(""),
    withdrawal_process_defined: bool = Form(False),
    deletion_handling_defined: bool = Form(False),
    features_assessed: bool = Form(False),
    enabled_features_values: list[str] = Form([], alias="enabled_features"),
    ai_features_disclosed: bool = Form(False),
    international_transfer_assessment: str = Form("not_assessed"),
    ethics_status: str = Form("not_assessed"),
    dpia_status: str = Form("not_assessed"),
    security_considerations: str = Form(""),
    u=Depends(roles("owner", "admin", "researcher")),
    csrf_ok: None = Depends(csrf_protect),
    db: Session = Depends(get_db),
):
    s = study(db, study_id, u.organisation_id)
    require_study_permission(db, u, s, edit=True)
    if special_category_data not in SPECIAL_CATEGORY_STATES:
        raise HTTPException(400, "Invalid special-category data assessment.")
    assessments = (international_transfer_assessment, ethics_status, dpia_status)
    if any(value not in ASSESSMENT_STATES for value in assessments):
        raise HTTPException(400, "Invalid governance assessment status.")
    selected_features = {value for value in enabled_features_values if value in FEATURES}
    if set(enabled_features_values) != selected_features:
        raise HTTPException(400, "Invalid participant feature.")
    governance = governance_for_study(db, s)
    if governance is None:
        governance = StudyGovernance(organisation_id=s.organisation_id, study_id=s.id)
        db.add(governance)
    for name, value in {
        "controller_name": controller_name,
        "controller_privacy_contact": controller_privacy_contact,
        "sponsor_name": sponsor_name,
        "research_contact": research_contact,
        "participant_population": participant_population,
        "data_categories": data_categories,
        "article_6_lawful_basis": article_6_lawful_basis,
        "article_9_condition": article_9_condition,
        "retention_description": retention_description,
        "deletion_retention_exception": deletion_retention_exception,
        "security_considerations": security_considerations,
    }.items():
        setattr(governance, name, value.strip())
    for name, value in {
        "participant_information_reference": participant_information_reference,
        "participant_information_version": participant_information_version,
        "participant_information_effective_date": participant_information_effective_date,
        "privacy_notice_reference": privacy_notice_reference,
        "privacy_notice_version": privacy_notice_version,
        "privacy_notice_effective_date": privacy_notice_effective_date,
        "consent_text_reference": consent_text_reference,
        "consent_text_version": consent_text_version,
        "consent_text_effective_date": consent_text_effective_date,
    }.items():
        if name.endswith("_reference"):
            setattr(governance, name, document_reference(value, name.replace("_", " ")))
        else:
            setattr(governance, name, value.strip())
    governance.special_category_data = special_category_data
    governance.participation_consent_configured = participation_consent_configured
    governance.participant_information_available = participant_information_available
    governance.privacy_information_available = privacy_information_available
    governance.withdrawal_process_defined = withdrawal_process_defined
    governance.deletion_handling_defined = deletion_handling_defined
    governance.features_assessed = features_assessed
    governance.enabled_features_json = json.dumps(sorted(selected_features))
    governance.ai_features_disclosed = ai_features_disclosed
    governance.international_transfer_assessment = international_transfer_assessment
    governance.ethics_status = ethics_status
    governance.dpia_status = dpia_status
    existing_documents = {item.document_type: item for item in current_bundle_documents(db, governance)}
    supplied_bodies = (participant_information_body, privacy_notice_body, consent_text_body)
    has_document_metadata = all(
        getattr(governance, f"{document_type}_{field}").strip()
        for document_type in ("participant_information", "privacy_notice", "consent_text")
        for field in ("reference", "version", "effective_date")
    )
    if has_document_metadata and (any(value.strip() for value in supplied_bodies) or len(existing_documents) == 3):
        try:
            create_or_reuse_current_bundle(
                db,
                s,
                governance,
                {
                    "participant_information": participant_information_body or (existing_documents["participant_information"].body if "participant_information" in existing_documents else ""),
                    "privacy_notice": privacy_notice_body or (existing_documents["privacy_notice"].body if "privacy_notice" in existing_documents else ""),
                    "consent_text": consent_text_body or (existing_documents["consent_text"].body if "consent_text" in existing_documents else ""),
                },
            )
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
    elif not has_document_metadata:
        # An incomplete edit cannot leave a superseded bundle marked current.
        # Existing invitations keep their own immutable bundle references.
        governance.current_consent_bundle_id = None
    audit(db, u.organisation_id, u.id, "study.governance_updated", "study", s.id, s.title)
    db.commit()
    return RedirectResponse(f"/studies/{s.id}#governance", 303)


@app.post("/studies/{study_id}/methodology-configuration")
def update_methodology_configuration(
    study_id: int,
    research_philosophy: str = Form("not_specified"),
    research_design: str = Form("not_specified"),
    secondary_design: str = Form(""),
    evidence_method_values: list[str] = Form([], alias="evidence_methods"),
    analysis_approach_values: list[str] = Form([], alias="analysis_approaches"),
    theoretical_orientation_values: list[str] = Form([], alias="theoretical_orientations"),
    research_questions: str = Form(""),
    protocol_reference: str = Form(""),
    protocol_version: str = Form(""),
    sampling_approach: str = Form(""),
    data_collection_plan: str = Form(""),
    ai_enabled: bool = Form(False),
    allowed_ai_task_values: list[str] = Form([], alias="allowed_ai_tasks"),
    researcher_notes: str = Form(""),
    researcher_confirmation: bool = Form(False),
    u=Depends(roles("owner", "admin", "researcher")),
    csrf_ok: None = Depends(csrf_protect),
    db: Session = Depends(get_db),
):
    s = study(db, study_id, u.organisation_id)
    require_study_permission(db, u, s, edit=True)
    research_philosophy = _protocol_value(research_philosophy, "research_philosophies")
    research_design = _protocol_value(research_design, "research_designs")
    secondary_design = _protocol_value(secondary_design, "research_designs") if secondary_design else ""
    if secondary_design and secondary_design == research_design:
        raise HTTPException(400, "Choose a different secondary design or leave it blank.")
    evidence_methods = _protocol_values(evidence_method_values, "evidence_methods")
    analysis_approaches = _protocol_values(analysis_approach_values, "analysis_approaches")
    theoretical_orientations = _protocol_values(theoretical_orientation_values, "theoretical_orientations")
    configuration = methodology_configuration_for_study(db, s)
    # Current controlled grounding is derived exclusively from the canonical
    # form values.  Historical controlled values are preserved separately and
    # cannot keep AI permissions alive after a researcher changes the design.
    derived_methodology_id = controlled_methodology_for_design(research_design, analysis_approaches)
    if ai_enabled and not derived_methodology_id:
        raise HTTPException(400, "AI support needs a clear study design or analysis mapping. Choose a more specific design or analysis before enabling it.")
    try:
        issues = validate_configuration(
            primary_methodology_id=derived_methodology_id,
            methodology_variant="",
            secondary_methodologies=[],
            research_questions=research_questions.strip(),
            protocol_reference=document_reference(protocol_reference, "Protocol reference"),
            protocol_version=protocol_version.strip(),
            sampling_approach=sampling_approach.strip(),
            data_collection_plan=data_collection_plan.strip(),
            ai_enabled=ai_enabled,
            allowed_ai_tasks=allowed_ai_task_values,
            researcher_confirmation=researcher_confirmation,
        ) if derived_methodology_id else ([] if not ai_enabled and not allowed_ai_task_values else ["Choose a more specific design or analysis before enabling AI support."])
    except MethodologyGateViolation as exc:
        raise HTTPException(400, str(exc)) from exc
    if issues:
        raise HTTPException(400, " ".join(issues))
    record = next((item for item in library_records() if item["methodology_id"] == derived_methodology_id), None)
    allowed = set(record["allowed_ai_tasks"]) if record else set()
    requested = set(allowed_ai_task_values)
    if not requested.issubset(allowed):
        raise HTTPException(400, "METHODOLOGICAL REVIEW REQUIRED: unsupported AI task requested.")
    if configuration is None:
        configuration = StudyMethodologyConfiguration(organisation_id=s.organisation_id, study_id=s.id)
        db.add(configuration)
    else:
        preserve_legacy_methodology_metadata(configuration)
    configuration.primary_methodology_id = derived_methodology_id
    configuration.methodology_variant = ""
    configuration.secondary_methodologies_json = "[]"
    configuration.research_philosophy = research_philosophy
    configuration.research_design = research_design
    configuration.secondary_design = secondary_design
    configuration.evidence_methods_json = json.dumps(evidence_methods)
    configuration.analysis_approaches_json = json.dumps(analysis_approaches)
    configuration.theoretical_orientations_json = json.dumps(theoretical_orientations)
    # Existing pre-0021 controlled and approach values retain their original
    # semantics. They are not guessed into the new canonical dimensions.
    configuration.research_questions = research_questions.strip()
    configuration.protocol_reference = document_reference(protocol_reference, "Protocol reference")
    configuration.protocol_version = protocol_version.strip()
    configuration.sampling_approach = sampling_approach.strip()
    configuration.data_collection_plan = data_collection_plan.strip()
    configuration.ai_enabled = ai_enabled
    configuration.allowed_ai_tasks_json = json.dumps(sorted(requested))
    configuration.human_review_required = True
    configuration.library_version = methodology_library()["library_version"]
    configuration.researcher_notes = researcher_notes.strip()
    configuration.researcher_confirmed_by_id = u.id
    configuration.researcher_confirmed_at = datetime.now(timezone.utc)
    audit(db, u.organisation_id, u.id, "study.methodology_configuration_confirmed", "study", s.id, derived_methodology_id or "protocol-builder")
    db.commit()
    return RedirectResponse(f"/studies/{s.id}?section=design#design", 303)
@app.post("/studies/{study_id}/research-analysis/{suggestion_id}/review")
def review_research_analysis(study_id:int,suggestion_id:int,decision:str=Form(...),note:str=Form(""),u=Depends(current_user),csrf_ok:None=Depends(csrf_protect),db:Session=Depends(get_db)):
    if not settings.research_intelligence_enabled: raise HTTPException(404,"Research Intelligence is disabled")
    s=study(db,study_id,u.organisation_id); require_study_permission(db,u,s,edit=True)
    row=db.scalar(select(ResearchAnalysisSuggestion).where(ResearchAnalysisSuggestion.id==suggestion_id,ResearchAnalysisSuggestion.organisation_id==u.organisation_id,ResearchAnalysisSuggestion.study_id==s.id))
    if not row: raise HTTPException(404,"Suggestion not found")
    try: review_suggestion(u,row,decision,note)
    except (PermissionError,ValueError) as exc: raise HTTPException(400,str(exc))
    audit(db,u.organisation_id,u.id,f"research_analysis.{decision}","research_analysis_suggestion",row.id,row.source_response_id.__str__()); db.commit()
    return RedirectResponse(f"/studies/{s.id}",303)
@app.post("/studies/{study_id}/evidence-confidence")
def create_evidence_confidence(study_id:int,focus:str=Form(...),supporting_response_ids:str=Form(""),contradicting_response_ids:str=Form(""),u=Depends(current_user),csrf_ok:None=Depends(csrf_protect),db:Session=Depends(get_db)):
    if not (settings.research_intelligence_enabled and settings.research_intelligence_evidence_confidence_enabled): raise HTTPException(404,"Evidence Confidence is disabled")
    s=study(db,study_id,u.organisation_id); require_study_permission(db,u,s,edit=True)
    try:
        support_ids={int(value) for value in supporting_response_ids.split(',') if value.strip()}; contradiction_ids={int(value) for value in contradicting_response_ids.split(',') if value.strip()}
    except ValueError: raise HTTPException(400,"Source response IDs must be whole numbers")
    if support_ids & contradiction_ids: raise HTTPException(400,"A source cannot both support and contradict the same assessment")
    source_rows=db.scalars(select(ActivityResponse).where(ActivityResponse.organisation_id==u.organisation_id,ActivityResponse.study_id==s.id,ActivityResponse.id.in_(support_ids|contradiction_ids))).all() if support_ids|contradiction_ids else []
    if {row.id for row in source_rows} != support_ids|contradiction_ids: raise HTTPException(400,"One or more source responses are unavailable in this study")
    try: row=create_confidence_assessment(db,u,s,focus,[row for row in source_rows if row.id in support_ids],[row for row in source_rows if row.id in contradiction_ids])
    except (PermissionError,ValueError) as exc: raise HTTPException(400,str(exc))
    db.flush(); audit(db,u.organisation_id,u.id,"evidence_confidence.created","evidence_confidence_assessment",row.id,row.focus); db.commit(); return RedirectResponse(f"/studies/{s.id}#evidence-confidence",303)
@app.post("/studies/{study_id}/evidence-confidence/{assessment_id}/review")
def review_evidence_confidence(study_id:int,assessment_id:int,decision:str=Form(...),note:str=Form(""),u=Depends(current_user),csrf_ok:None=Depends(csrf_protect),db:Session=Depends(get_db)):
    if not (settings.research_intelligence_enabled and settings.research_intelligence_evidence_confidence_enabled): raise HTTPException(404,"Evidence Confidence is disabled")
    s=study(db,study_id,u.organisation_id); require_study_permission(db,u,s,edit=True)
    row=db.scalar(select(EvidenceConfidenceAssessment).where(EvidenceConfidenceAssessment.id==assessment_id,EvidenceConfidenceAssessment.organisation_id==u.organisation_id,EvidenceConfidenceAssessment.study_id==s.id))
    if not row: raise HTTPException(404,"Assessment not found")
    try: review_confidence_assessment(u,row,decision,note)
    except (PermissionError,ValueError) as exc: raise HTTPException(400,str(exc))
    audit(db,u.organisation_id,u.id,f"evidence_confidence.{decision}","evidence_confidence_assessment",row.id,row.focus); db.commit(); return RedirectResponse(f"/studies/{s.id}#evidence-confidence",303)


def _study_evidence_explorer_items(
    db: Session,
    user: User,
    study_row: Study,
    *,
    query: str = "",
    code: str = "",
    participant_id: int | None = None,
    analysis_status: str = "all",
):
    """Return only submitted, authorised source material for the requested study."""
    responses = db.scalars(
        select(ActivityResponse).where(
            ActivityResponse.organisation_id == user.organisation_id,
            ActivityResponse.study_id == study_row.id,
            ActivityResponse.status == "submitted",
        )
    ).all()
    activities = {
        row.id: row
        for row in db.scalars(
            select(Activity).where(
                Activity.organisation_id == user.organisation_id,
                Activity.study_id == study_row.id,
            )
        ).all()
    }
    participant_ids = {row.participant_id for row in responses}
    participants = {
        row.id: row
        for row in db.scalars(
            select(Participant).where(
                Participant.organisation_id == user.organisation_id,
                Participant.id.in_(participant_ids),
            )
        ).all()
    } if participant_ids else {}
    suggestions = db.scalars(
        select(ResearchAnalysisSuggestion).where(
            ResearchAnalysisSuggestion.organisation_id == user.organisation_id,
            ResearchAnalysisSuggestion.study_id == study_row.id,
        ).order_by(ResearchAnalysisSuggestion.created_at.desc())
    ).all()
    return filter_evidence(
        evidence_items(responses, activities=activities, participants=participants, suggestions=suggestions),
        query=query,
        code=code,
        participant_id=participant_id,
        analysis_status=analysis_status,
    )


def _evidence_api_item(item) -> EvidenceItemResponse:
    return EvidenceItemResponse(
        response_id=item.response_id,
        participant_id=item.participant_id,
        participant_reference=item.participant_reference,
        activity_id=item.activity_id,
        activity_title=item.activity_title,
        source_excerpt=item.source_excerpt,
        source_truncated=item.source_truncated,
        submitted_at=item.submitted_at,
        updated_at=item.updated_at,
        suggested_codes=item.suggested_codes,
        analysis_status=item.analysis_status,
    )


@app.get("/studies/{study_id}/evidence-explorer", response_class=HTMLResponse)
def study_evidence_explorer(
    study_id: int,
    request: Request,
    q: str = Query("", max_length=200),
    code: str = Query("", max_length=120),
    participant_id: int | None = Query(None, ge=1),
    analysis_status: str = Query("all", pattern="^(all|awaiting_researcher_review|accepted|rejected)$"),
    u=Depends(current_user),
    db: Session = Depends(get_db),
):
    if not settings.research_intelligence_enabled:
        raise HTTPException(404, "Research Intelligence is disabled")
    s = study(db, study_id, u.organisation_id)
    require_study_permission(db, u, s)
    items = _study_evidence_explorer_items(
        db, u, s, query=q, code=code, participant_id=participant_id, analysis_status=analysis_status,
    )
    return render(
        request,
        "evidence_explorer.html",
        user=u,
        study=s,
        items=items[:100],
        total=len(items),
        q=q,
        code=code,
        participant_id=participant_id,
        analysis_status=analysis_status,
    )


@app.get("/api/v1/research/studies/{study_id}/evidence", response_model=EvidenceExplorerResponse)
def research_evidence_explorer_api(
    study_id: int,
    q: str = Query("", max_length=200),
    code: str = Query("", max_length=120),
    participant_id: int | None = Query(None, ge=1),
    analysis_status: str = Query("all", pattern="^(all|awaiting_researcher_review|accepted|rejected)$"),
    limit: int = Query(50, ge=1, le=100),
    u=Depends(current_user),
    db: Session = Depends(get_db),
):
    if not settings.research_intelligence_enabled:
        raise HTTPException(404, "Research Intelligence is disabled")
    s = study(db, study_id, u.organisation_id)
    require_study_permission(db, u, s)
    items = _study_evidence_explorer_items(
        db, u, s, query=q, code=code, participant_id=participant_id, analysis_status=analysis_status,
    )
    return EvidenceExplorerResponse(study_id=s.id, data=[_evidence_api_item(item) for item in items[:limit]], total=len(items), returned=min(len(items), limit))


@app.get("/api/v1/research/studies/{study_id}/quotes", response_model=QuoteFinderResponse)
def research_quote_finder_api(
    study_id: int,
    q: str = Query("", max_length=200),
    code: str = Query("", max_length=120),
    participant_id: int | None = Query(None, ge=1),
    analysis_status: str = Query("all", pattern="^(all|awaiting_researcher_review|accepted|rejected)$"),
    limit: int = Query(50, ge=1, le=100),
    u=Depends(current_user),
    db: Session = Depends(get_db),
):
    """A quote finder that only returns verbatim source excerpts and provenance."""
    result = research_evidence_explorer_api(study_id, q, code, participant_id, analysis_status, limit, u, db)
    return QuoteFinderResponse(**result.model_dump())


def _theme_response(theme_row: ResearchTheme, suggestions_by_id: dict[int, ResearchAnalysisSuggestion]) -> ThemeResponse:
    try:
        suggestion_ids = [int(value) for value in json.loads(theme_row.source_suggestion_ids_json or "[]")]
    except (TypeError, ValueError, json.JSONDecodeError):
        suggestion_ids = []
    return ThemeResponse(
        theme_id=theme_row.id,
        name=theme_row.name,
        description=theme_row.description,
        status=theme_row.status,
        source_suggestion_ids=suggestion_ids,
        source_response_ids=[
            suggestions_by_id[item_id].source_response_id
            for item_id in suggestion_ids
            if item_id in suggestions_by_id
        ],
        created_at=theme_row.created_at,
    )


def _study_themes(db: Session, user: User, study_row: Study):
    themes = db.scalars(
        select(ResearchTheme).where(
            ResearchTheme.organisation_id == user.organisation_id,
            ResearchTheme.study_id == study_row.id,
        ).order_by(ResearchTheme.updated_at.desc())
    ).all()
    suggestion_ids = {
        suggestion_id
        for theme_row in themes
        for suggestion_id in json.loads(theme_row.source_suggestion_ids_json or "[]")
        if isinstance(suggestion_id, int)
    }
    suggestions = {
        row.id: row
        for row in db.scalars(
            select(ResearchAnalysisSuggestion).where(
                ResearchAnalysisSuggestion.organisation_id == user.organisation_id,
                ResearchAnalysisSuggestion.study_id == study_row.id,
                ResearchAnalysisSuggestion.id.in_(suggestion_ids),
                ResearchAnalysisSuggestion.status == "accepted",
            )
        ).all()
    } if suggestion_ids else {}
    return themes, suggestions


@app.get("/studies/{study_id}/theme-explorer", response_class=HTMLResponse)
def study_theme_explorer(study_id: int, request: Request, u=Depends(current_user), db: Session = Depends(get_db)):
    if not settings.research_intelligence_enabled:
        raise HTTPException(404, "Research Intelligence is disabled")
    s = study(db, study_id, u.organisation_id)
    permission = require_study_permission(db, u, s)
    themes, suggestions_by_id = _study_themes(db, u, s)
    accepted_suggestions = db.scalars(
        select(ResearchAnalysisSuggestion).where(
            ResearchAnalysisSuggestion.organisation_id == u.organisation_id,
            ResearchAnalysisSuggestion.study_id == s.id,
            ResearchAnalysisSuggestion.status == "accepted",
        ).order_by(ResearchAnalysisSuggestion.reviewed_at.desc())
    ).all()
    return render(
        request,
        "theme_explorer.html",
        user=u,
        study=s,
        themes=[_theme_response(item, suggestions_by_id) for item in themes],
        accepted_suggestions=accepted_suggestions,
        can_edit=permission in {"edit", "manage"},
    )


@app.post("/studies/{study_id}/themes")
def create_research_theme(
    study_id: int,
    name: str = Form(...),
    description: str = Form(""),
    source_suggestion_ids: str = Form(...),
    u=Depends(current_user),
    csrf_ok: None = Depends(csrf_protect),
    db: Session = Depends(get_db),
):
    if not settings.research_intelligence_enabled:
        raise HTTPException(404, "Research Intelligence is disabled")
    s = study(db, study_id, u.organisation_id)
    require_study_permission(db, u, s, edit=True)
    try:
        identifiers = parse_suggestion_ids(source_suggestion_ids)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    suggestions = db.scalars(
        select(ResearchAnalysisSuggestion).where(
            ResearchAnalysisSuggestion.organisation_id == u.organisation_id,
            ResearchAnalysisSuggestion.study_id == s.id,
            ResearchAnalysisSuggestion.id.in_(identifiers),
        )
    ).all()
    if {row.id for row in suggestions} != identifiers:
        raise HTTPException(400, "One or more source analyses are unavailable in this study")
    try:
        row = create_theme(db, u, s, name=name, description=description, suggestions=suggestions)
    except (PermissionError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    db.flush()
    audit(db, u.organisation_id, u.id, "research_theme.created", "research_theme", row.id, row.name)
    db.commit()
    return RedirectResponse(f"/studies/{s.id}/theme-explorer", 303)


@app.get("/api/v1/research/studies/{study_id}/themes", response_model=ThemeListResponse)
def research_themes_api(study_id: int, u=Depends(current_user), db: Session = Depends(get_db)):
    if not settings.research_intelligence_enabled:
        raise HTTPException(404, "Research Intelligence is disabled")
    s = study(db, study_id, u.organisation_id)
    require_study_permission(db, u, s)
    themes, suggestions_by_id = _study_themes(db, u, s)
    return ThemeListResponse(study_id=s.id, data=[_theme_response(item, suggestions_by_id) for item in themes])
@app.post("/studies/{study_id}/edit")
def edit_study(study_id:int,title:str=Form(...),description:str=Form(""),methodology:str=Form(...),status_value:str=Form(...),demographics_schema:str=Form(""),u=Depends(roles("owner","admin","researcher")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    s=study(db,study_id,u.organisation_id); require_study_permission(db,u,s,edit=True); enum_value(status_value,StudyStatus,"study status")
    if methodology not in STUDY_METHODOLOGIES: raise HTTPException(400,"Invalid methodology.")
    if status_value == "live": require_study_launch_ready(db, s)
    s.title=nonblank(title,"Study title",3); s.description=description.strip(); s.methodology=methodology; s.status=status_value; s.demographics_schema_json=json.dumps([x.strip() for x in demographics_schema.splitlines() if x.strip()]); audit(db,u.organisation_id,u.id,"study.updated","study",s.id,s.title); db.commit(); return RedirectResponse(f"/studies/{s.id}",303)
@app.post("/studies/{study_id}/status")
def study_status(study_id:int,status_value:str=Form(...),u=Depends(roles("owner","admin","researcher")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    s=study(db,study_id,u.organisation_id); require_study_permission(db,u,s,edit=True); enum_value(status_value,StudyStatus,"study status")
    if status_value == "live": require_study_launch_ready(db, s)
    s.status=status_value; db.commit(); return RedirectResponse(f"/studies/{s.id}",303)
@app.post("/studies/{study_id}/activities")
def create_activity(study_id:int,title:str=Form(...),prompt:str=Form(""),activity_type:str=Form("long_text"),options:str=Form(""),required:bool=Form(False),allow_multiple_entries:bool=Form(False),allow_participant_location:bool=Form(False),release_offset_days:int=Form(0),due_offset_days:str=Form(""),u=Depends(roles("owner","admin","researcher")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    s=study(db,study_id,u.organisation_id); require_study_permission(db,u,s,edit=True)
    if activity_type not in ACTIVITY_TYPES or release_offset_days<0: raise HTTPException(400,"Invalid activity configuration.")
    try: due=int(due_offset_days) if due_offset_days.strip() else None
    except ValueError: raise HTTPException(400,"Due day must be a whole number.")
    if due is not None and due<release_offset_days: raise HTTPException(400,"Due day cannot be earlier than release day.")
    opts=[x.strip() for x in options.splitlines() if x.strip()]
    if activity_type in {"single_choice","multiple_choice","ranking"} and len(opts)<2: raise HTTPException(400,"Choice and ranking activities require at least two options.")
    if activity_type in {"single_choice","multiple_choice","ranking"} and len(opts) != len(set(opts)): raise HTTPException(400,"Activity options must be unique.")
    pos=(db.scalar(select(func.max(Activity.position)).where(Activity.study_id==s.id)) or 0)+1; a=Activity(organisation_id=u.organisation_id,study_id=s.id,title=nonblank(title,"Activity title"),prompt=prompt.strip(),activity_type=activity_type,options_json=json.dumps(opts),position=pos,required=required,allow_multiple_entries=allow_multiple_entries,allow_participant_location=allow_participant_location,release_offset_days=release_offset_days,due_offset_days=due); db.add(a); db.flush(); audit(db,u.organisation_id,u.id,"activity.created","activity",a.id,a.title); db.commit(); return RedirectResponse(f"/studies/{s.id}",303)
@app.post("/activities/{activity_id}/edit")
def edit_activity(activity_id:int,title:str=Form(...),prompt:str=Form(""),activity_type:str=Form(...),options:str=Form(""),required:bool=Form(False),allow_multiple_entries:bool=Form(False),allow_participant_location:bool=Form(False),release_offset_days:int=Form(0),due_offset_days:str=Form(""),u=Depends(roles("owner","admin","researcher")),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    a=db.scalar(select(Activity).where(Activity.id==activity_id,Activity.organisation_id==u.organisation_id));
    if not a: raise HTTPException(404)
    require_study_permission(db,u,study(db,a.study_id,u.organisation_id),edit=True)
    if activity_type not in ACTIVITY_TYPES or release_offset_days<0: raise HTTPException(400,"Invalid activity configuration.")
    try: due=int(due_offset_days) if due_offset_days.strip() else None
    except ValueError: raise HTTPException(400,"Due day must be a whole number.")
    opts=[x.strip() for x in options.splitlines() if x.strip()]
    if due is not None and due<release_offset_days: raise HTTPException(400,"Invalid dates.")
    if activity_type in {"single_choice","multiple_choice","ranking"} and len(opts)<2: raise HTTPException(400,"At least two options required.")
    if activity_type in {"single_choice","multiple_choice","ranking"} and len(opts) != len(set(opts)): raise HTTPException(400,"Activity options must be unique.")
    a.title=nonblank(title,"Activity title"); a.prompt=prompt.strip(); a.activity_type=activity_type; a.options_json=json.dumps(opts); a.required=required; a.allow_multiple_entries=allow_multiple_entries; a.allow_participant_location=allow_participant_location; a.release_offset_days=release_offset_days; a.due_offset_days=due; audit(db,u.organisation_id,u.id,"activity.updated","activity",a.id,a.title); db.commit(); return RedirectResponse(f"/studies/{a.study_id}",303)
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
    unread_result = db.execute(
        update(ParticipantMessage)
        .where(
            ParticipantMessage.organisation_id == u.organisation_id,
            ParticipantMessage.participant_id == p.id,
            ParticipantMessage.study_id.in_(studies.keys()),
            ParticipantMessage.sender_type == "participant",
            ParticipantMessage.internal_note == False,
            ParticipantMessage.read_at.is_(None),
        )
        .values(read_at=now())
    )
    if unread_result.rowcount:
        audit(db,u.organisation_id,u.id,"message.participant_messages_read","participant",p.id,str(unread_result.rowcount)); db.commit()
        for message in messages:
            if message.sender_type == "participant" and not message.internal_note and message.read_at is None:
                message.read_at = now()
    privacy_counts = participant_related_counts(db, p.id, u.organisation_id) if u.role in {"owner", "admin"} else None
    privacy_workflow_token = request.session.get(privacy_workflow_key(p.id)) if u.role in {"owner", "admin"} else None
    activity_ids = {row.activity_id for row in responses}
    activities = {row.id: row for row in db.scalars(select(Activity).where(Activity.organisation_id == u.organisation_id, Activity.id.in_(activity_ids))).all()} if activity_ids else {}
    evidence_by_response: dict[int, list[EvidenceFile]] = {}
    for item in evidence_files:
        if item.response_id:
            evidence_by_response.setdefault(item.response_id, []).append(item)
    timeline = [
        {"response": row, "activity": activities.get(row.activity_id), "body": response_body(row.value_json), "codes": response_codes(row.value_json), "context": response_context(row.value_json), "evidence": evidence_by_response.get(row.id, [])}
        for row in sorted(responses, key=lambda item: (item.submitted_at or item.updated_at, item.id))
        if row.status == "submitted" and response_body(row.value_json)
    ]
    visible_participant_ids = set()
    if u.role in {"owner", "admin", "observer"}:
        visible_participant_ids = set(db.scalars(select(Participant.id).where(Participant.organisation_id == u.organisation_id)).all())
    else:
        visible_participant_ids = set(db.scalars(select(StudyEnrolment.participant_id).where(StudyEnrolment.organisation_id == u.organisation_id, StudyEnrolment.study_id.in_(list(studies)))).all())
        if p.created_by_id == u.id:
            visible_participant_ids.add(p.id)
    dossier_participants = db.scalars(select(Participant).where(Participant.organisation_id == u.organisation_id, Participant.id.in_(visible_participant_ids)).order_by(Participant.reference)).all() if visible_participant_ids else []
    dossier_ids = [row.id for row in dossier_participants]
    position = dossier_ids.index(p.id) if p.id in dossier_ids else -1
    previous_participant = dossier_participants[position - 1] if position > 0 else None
    next_participant = dossier_participants[position + 1] if position >= 0 and position + 1 < len(dossier_participants) else None
    return render(request,"participant_detail.html",user=u,participant=p,enrolments=ens,studies=studies,invitations=invs,responses=responses,evidence_files=evidence_files,messages=[m for m in messages if not m.internal_note],internal_notes=[m for m in messages if m.internal_note],statuses=[x.value for x in ParticipantStatus],consent_statuses=[x.value for x in ConsentStatus],is_privacy_admin=u.role in {"owner", "admin"},privacy_counts=privacy_counts,privacy_workflow_token=privacy_workflow_token,timeline=timeline,previous_participant=previous_participant,next_participant=next_participant)


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
    if settings.privacy_retention_days is None or settings.privacy_retention_days <= 0:
        raise HTTPException(400, "A controller-approved retention period must be configured before applying retention.")
    statuses = [x.strip() for x in settings.privacy_retention_statuses.split(",") if x.strip()]
    if not statuses:
        raise HTTPException(400, "No retention statuses configured.")
    days = int(settings.privacy_retention_days)
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
    invitation, raw = create_participant_invitation(
        db,
        organisation_id=u.organisation_id,
        participant_id=p.id,
        study_id=s.id,
        invited_by_id=u.id,
        expires_at=now() + timedelta(days=30),
    )
    try:
        bind_invitation_to_current_bundle(db, invitation, governance_for_study(db, s))
    except ValueError as error:
        db.rollback()
        raise HTTPException(400, str(error)) from error
    queue_email(
        db,
        u.organisation_id,
        p.email,
        f"Invitation: {s.title}",
        (
            "Review the study information and consent securely. After consenting, "
            "the website will show a one-time code for the Citizen Centric app.\n\n"
            f"Join the study: {settings.base_url}/join-study?token={raw}"
        ),
        participant_id=p.id,
        study_id=s.id,
    ); p.status="invited"; audit(db,u.organisation_id,u.id,"participant.invited","participant",p.id,s.title); db.commit()
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
            response = render(request,"join_study.html",invitation=None,study=None,participant=None,valid=False)
            _cache_control_no_store(response)
            return response
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
        _cache_control_no_store(response)
        return response

    session_row = get_public_auth_session(request, db, PUBLIC_SCOPE_PARTICIPANT_PORTAL)
    if not session_row:
        response = render(request,"join_study.html",invitation=None,study=None,participant=None,valid=False)
        _cache_control_no_store(response)
        return response
    inv = db.get(ParticipantInvitation, session_row.participant_invitation_id)
    valid=bool(inv and not inv.revoked_at and unexpired(inv.expires_at))
    s=db.get(Study,inv.study_id) if valid else None
    p=db.get(Participant,inv.participant_id) if valid else None
    if valid and inv.accepted_at:
        return RedirectResponse("/participant-portal",303)
    try:
        documents = require_bound_documents(db, inv, governance_for_study(db, s)) if valid else ()
    except ValueError as error:
        response = render(request,"join_study.html",invitation=None,study=None,participant=None,documents=(),valid=False,flash_error=str(error))
        _cache_control_no_store(response)
        return response
    response = render(request,"join_study.html",invitation=inv,study=s,participant=p,documents=documents,valid=valid)
    _cache_control_no_store(response)
    return response
@app.post("/join-study")
def accept_study(request:Request,token:str=Form(""),consent:bool=Form(False),reviewed_participant_information:bool=Form(False),reviewed_privacy_notice:bool=Form(False),reviewed_consent_text:bool=Form(False),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
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
    p = db.get(Participant, inv.participant_id)
    governance = governance_for_study(db, study(db, inv.study_id, inv.organisation_id))
    try:
        documents = require_bound_documents(db, inv, governance)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    if documents and not all((reviewed_participant_information, reviewed_privacy_notice, reviewed_consent_text)):
        raise HTTPException(400, "Read each study-specific document before consenting.")
    capture_consent_document_evidence(inv, governance)
    grant_participant_consent(inv, p, now())
    audit(db, inv.organisation_id, None, "participant.invitation_accepted", "participant", p.id)
    db.commit()
    set_flash(
        request,
        "success",
        "Consent complete. Request a one-time code below to continue in the participant app.",
    )
    return RedirectResponse("/participant-portal", 303)


def normalise_participant_app_access_code(value: str) -> str:
    compact = re.sub(r"[\s-]+", "", value or "").upper()
    return compact if re.fullmatch(r"CC[0-9A-F]{16}", compact) else ""


def create_participant_app_access_code(
    db: Session,
    invitation: ParticipantInvitation,
) -> str:
    compact = f"CC{secrets.token_hex(8).upper()}"
    display = "-".join((compact[:2], compact[2:6], compact[6:10], compact[10:14], compact[14:18]))
    db.add(
        ParticipantAppAccessCode(
            organisation_id=invitation.organisation_id,
            participant_invitation_id=invitation.id,
            code_hash=token_hash(compact),
            expires_at=now() + timedelta(minutes=30),
        )
    )
    return display


@app.post("/participant-portal/app-access-code", response_class=HTMLResponse)
def participant_portal_app_access_code(
    request: Request,
    csrf_ok: None = Depends(csrf_protect),
    db: Session = Depends(get_db),
):
    _session_row, invitation, _participant, study_row, _enrolment = require_participant_portal_context(request, db)
    app_code = create_participant_app_access_code(db, invitation)
    audit(
        db,
        invitation.organisation_id,
        None,
        "participant.app_access_code_created",
        "participant_invitation",
        invitation.id,
    )
    db.commit()
    response = render(request, "participant_app_access.html", study=study_row, app_code=app_code)
    _cache_control_no_store(response)
    return response


def participant_portal_context(request: Request, db: Session):
    session_row = get_public_auth_session(request, db, PUBLIC_SCOPE_PARTICIPANT_PORTAL)
    inv = resolve_participant_invitation(db, session_row)
    if not inv or inv.revoked_at or not unexpired(inv.expires_at) or not inv.accepted_at:
        return None
    participant_row = db.scalar(
        select(Participant).where(
            Participant.id == inv.participant_id,
            Participant.organisation_id == inv.organisation_id,
        )
    )
    study_row = db.scalar(
        select(Study).where(
            Study.id == inv.study_id,
            Study.organisation_id == inv.organisation_id,
        )
    )
    enrolment = db.scalar(
        select(StudyEnrolment).where(
            StudyEnrolment.organisation_id == inv.organisation_id,
            StudyEnrolment.study_id == inv.study_id,
            StudyEnrolment.participant_id == inv.participant_id,
        )
    )
    if (
        not participant_row
        or not study_row
        or not enrolment
        or enrolment.status == "withdrawn"
        or participant_row.consent_status != ConsentStatus.granted.value
    ):
        return None
    return session_row, inv, participant_row, study_row, enrolment


def require_participant_portal_context(request: Request, db: Session):
    context = participant_portal_context(request, db)
    if not context:
        raise HTTPException(401, "Your participant session is invalid, expired or no longer active.")
    return context


@app.get("/participant-portal",response_class=HTMLResponse)
def participant_portal(request:Request,token:str="",db:Session=Depends(get_db)):
    if token:
        return RedirectResponse(f"/join-study?token={token}",303)
    context = participant_portal_context(request, db)
    if not context:
        response = RedirectResponse("/join-study",303)
        clear_public_auth_cookie(response)
        return response
    _session_row, inv, p, s, _enrolment = context
    acts=db.scalars(select(Activity).where(Activity.organisation_id==inv.organisation_id,Activity.study_id==s.id).order_by(Activity.position)).all(); activity_windows={a.id:activity_window(s,a) for a in acts}; responses={r.activity_id:r for r in db.scalars(select(ActivityResponse).where(ActivityResponse.organisation_id==inv.organisation_id,ActivityResponse.study_id==s.id,ActivityResponse.participant_id==p.id)).all()}; response_values={}
    for activity_id,response in responses.items():
        try: response_values[activity_id]=json.loads(response.value_json or "{}")
        except json.JSONDecodeError: response_values[activity_id]={}
    evidence_ids = {
        value.get("evidence_id")
        for value in response_values.values()
        if isinstance(value.get("evidence_id"), int)
    }
    evidence_by_id = {}
    if evidence_ids:
        evidence_by_id = {
            row.id: row
            for row in db.scalars(
                select(EvidenceFile).where(
                    EvidenceFile.id.in_(evidence_ids),
                    EvidenceFile.organisation_id == inv.organisation_id,
                    EvidenceFile.study_id == s.id,
                    EvidenceFile.participant_id == p.id,
                )
            ).all()
        }
    msgs = list_participant_visible_messages(db, study_id=s.id, participant_id=p.id)
    participant_read_result = db.execute(
        update(ParticipantMessage)
        .where(
            ParticipantMessage.organisation_id == inv.organisation_id,
            ParticipantMessage.study_id == s.id,
            ParticipantMessage.participant_id == p.id,
            ParticipantMessage.sender_type == "researcher",
            ParticipantMessage.internal_note == False,
            ParticipantMessage.read_at.is_(None),
        )
        .values(read_at=now())
    )
    if participant_read_result.rowcount:
        audit(db,inv.organisation_id,None,"participant.messages_read","participant",p.id,str(s.id)); db.commit()
        for message in msgs:
            if message.sender_type == "researcher" and message.read_at is None:
                message.read_at = now()
    response = render(
        request,
        "participant_portal.html",
        study=s,
        participant=p,
        activities=acts,
        activity_windows=activity_windows,
        responses=responses,
        response_values=response_values,
        activity_options={a.id: _participant_activity_options(a) or [] for a in acts},
        evidence_by_id=evidence_by_id,
        messages=msgs,
        max_upload_mb=settings.max_upload_mb,
    )
    _cache_control_no_store(response)
    return response


@app.get(
    "/api/v1/participant/portal",
    response_model=PortalSummaryResponse,
    response_model_exclude_unset=True,
)
def participant_api_portal_summary(
    request: Request,
    response: Response,
    study_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
):
    _session_row, inv, participant_row = _resolve_participant_api_context(request, db)
    if not inv.accepted_at:
        raise HTTPException(403, "Participant consent has not been accepted.")
    if participant_row.consent_status != ConsentStatus.granted.value:
        raise HTTPException(403, "Participant consent is no longer active.")
    if study_id is not None and study_id != inv.study_id:
        raise HTTPException(403, "Requested study is outside participant scope.")

    _enforce_rate_limit(
        request,
        db,
        scope="participant_portal_read",
        ip_limit=settings.rate_limit_portal_write_ip,
        account_key=f"invitation:{inv.id}",
        account_limit=settings.rate_limit_portal_write_token,
    )

    study_row = db.scalar(
        select(Study).where(
            Study.id == inv.study_id,
            Study.organisation_id == inv.organisation_id,
        )
    )
    if not study_row:
        raise _participant_api_unauthorised()

    enrolled = db.scalar(
        select(StudyEnrolment.id).where(
            StudyEnrolment.organisation_id == inv.organisation_id,
            StudyEnrolment.study_id == inv.study_id,
            StudyEnrolment.participant_id == participant_row.id,
            StudyEnrolment.status != "withdrawn",
        )
    ) is not None
    if not enrolled:
        raise HTTPException(403, "Participant is not enrolled in this study.")

    activity_rows = db.scalars(
        select(Activity)
        .where(
            Activity.organisation_id == inv.organisation_id,
            Activity.study_id == study_row.id,
        )
        .order_by(Activity.position)
    ).all()
    response_rows = db.scalars(
        select(ActivityResponse).where(
            ActivityResponse.organisation_id == inv.organisation_id,
            ActivityResponse.study_id == study_row.id,
            ActivityResponse.participant_id == participant_row.id,
        )
    ).all()
    responses_by_activity = {row.activity_id: row for row in response_rows}

    activity_summaries: list[ActivitySummary] = []
    response_items: list[PortalResponseItem] = []
    for activity in activity_rows:
        availability = activity_window(study_row, activity)
        response_row = responses_by_activity.get(activity.id)
        response_summary = None
        if response_row:
            response_summary = ActivityResponseSummary(
                status=response_row.status,
                submitted_at=response_row.submitted_at,
                updated_at=response_row.updated_at,
            )

            raw_value = {}
            try:
                raw_value = json.loads(response_row.value_json or "{}")
            except json.JSONDecodeError:
                raw_value = {}

            response_items.append(
                PortalResponseItem(
                    activity_id=activity.id,
                    status=response_row.status,
                    value=ActivityResponseValue(
                        answer=raw_value.get("answer"),
                        choices=list(raw_value.get("choices") or []),
                        evidence_id=raw_value.get("evidence_id"),
                        location=_participant_response_location(response_row),
                    ),
                    submitted_at=response_row.submitted_at,
                    updated_at=response_row.updated_at,
                )
            )

        item = ActivitySummary(
            activity_id=activity.id,
            title=activity.title,
            prompt=activity.prompt,
            activity_type=activity.activity_type,
            required=activity.required,
            allow_multiple_entries=bool(activity.allow_multiple_entries),
            allow_participant_location=bool(activity.allow_participant_location),
            position=activity.position,
            availability=ActivityAvailability(
                status=availability["status"],
                release_at=availability["release_at"],
                due_at=availability["due_at"],
            ),
        )
        if response_summary:
            item.response = response_summary
        activity_summaries.append(item)

    messages = [
        ParticipantMessageSummary(
            message_id=row.id,
            sender_type=row.sender_type,
            body=row.body,
            created_at=row.created_at,
        )
        for row in list_participant_visible_messages(
            db,
            study_id=study_row.id,
            participant_id=participant_row.id,
        )
    ]

    _cache_control_no_store(response)
    return PortalSummaryResponse(
        study=StudySummary(
            study_id=study_row.id,
            title=study_row.title,
            description=study_row.description,
            status=study_row.status,
            methodology=study_row.methodology,
            enrolled=True,
        ),
        participant=ParticipantSummary(
            display_name=participant_row.name,
            consent_status=participant_row.consent_status,
        ),
        activities=activity_summaries,
        responses=response_items,
        messages=messages,
    )


@app.post("/participant-portal/activity/{activity_id}")
async def submit_activity(request: Request, activity_id:int,token:str=Form(""),action:str=Form("submit"),answer:str=Form(""),choices:list[str]=Form(default=[]),upload:UploadFile|None=File(None),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    context = participant_portal_context(request, db)
    inv = context[1] if context else None
    account_key = f"invitation:{inv.id}" if inv else (token_hash(token) if token else "missing")
    _enforce_rate_limit(
        request,
        db,
        scope="participant_portal_write",
        ip_limit=settings.rate_limit_portal_write_ip,
        account_key=account_key,
        account_limit=settings.rate_limit_portal_write_token,
    )
    if not context or not inv:
        raise HTTPException(400,"This participant link is invalid or expired.")
    a=db.scalar(select(Activity).where(Activity.id==activity_id,Activity.organisation_id==inv.organisation_id,Activity.study_id==inv.study_id));
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
    if r.status == "submitted":
        raise HTTPException(409, "This activity response has already been submitted.")
    value, choice_list = serialise_response_payload(answer, choices)
    value = _validate_activity_response_value(a, value, action)
    choice_list = list(value.get("choices") or [])
    stored_key = None
    if upload and upload.filename:
        original=Path(upload.filename).name
        validate_evidence_upload_metadata(original, upload.content_type, a.activity_type)
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
def participant_message(request: Request, token:str=Form(""),body:str=Form(..., max_length=10000),csrf_ok: None = Depends(csrf_protect),db:Session=Depends(get_db)):
    context = participant_portal_context(request, db)
    inv = context[1] if context else None
    account_key = f"invitation:{inv.id}" if inv else (token_hash(token) if token else "missing")
    _enforce_rate_limit(
        request,
        db,
        scope="participant_portal_write",
        ip_limit=settings.rate_limit_portal_write_ip,
        account_key=account_key,
        account_limit=settings.rate_limit_portal_write_token,
    )
    if not context or not inv:
        raise HTTPException(400,"This participant link is invalid or expired.")
    if not body.strip(): raise HTTPException(400,"Message cannot be empty.")
    db.add(create_participant_message(inv, body=body)); audit(db,inv.organisation_id,None,"participant.message_created","participant",inv.participant_id,str(inv.study_id)); db.commit(); set_flash(request,"success","Your message was sent securely."); return RedirectResponse("/participant-portal#messages",303)


@app.post("/participant-portal/sign-out")
def participant_portal_sign_out(request: Request, csrf_ok: None = Depends(csrf_protect), db: Session = Depends(get_db)):
    context = participant_portal_context(request, db)
    if context:
        session_row, inv, _participant_row, _study_row, _enrolment = context
        session_row.revoked_at = now()
        audit(db, inv.organisation_id, None, "participant.portal_session_revoked", "public_auth_session", session_row.id, PUBLIC_SCOPE_PARTICIPANT_PORTAL)
        db.commit()
    response = RedirectResponse("/join-study", 303)
    clear_public_auth_cookie(response)
    return response


@app.post("/participant-portal/privacy/deletion-request")
def participant_portal_deletion_request(
    request: Request,
    confirmed: bool = Form(False),
    csrf_ok: None = Depends(csrf_protect),
    db: Session = Depends(get_db),
):
    if not confirmed:
        raise HTTPException(400, "Please confirm that you want to withdraw and delete your active study data.")
    _session_row, inv, participant_row, study_row, _enrolment = require_participant_portal_context(request, db)
    apply_participant_withdrawal(db, inv, participant_row, "study")
    privacy_request = ParticipantPrivacyRequest(
        organisation_id=inv.organisation_id,
        participant_id=participant_row.id,
        study_id=study_row.id,
        request_type="deletion",
        scope="study",
        status="received",
    )
    db.add(privacy_request)
    db.flush()
    db.commit()
    completed = process_deletion_request(db, storage, privacy_request)
    set_flash(
        request,
        "success",
        "Your identifiable active study data has been deleted." if completed else "Your access has ended. Deletion is being safely retried and is not yet complete.",
    )
    response = RedirectResponse("/join-study", 303)
    clear_public_auth_cookie(response)
    return response


def participant_self_export_payload(
    db: Session,
    invitation: ParticipantInvitation,
    participant_row: Participant,
    study_row: Study,
    enrolment: StudyEnrolment,
):
    activities = list(
        db.scalars(
            select(Activity)
            .where(
                Activity.organisation_id == invitation.organisation_id,
                Activity.study_id == study_row.id,
            )
            .order_by(Activity.position.asc(), Activity.id.asc())
        )
    )
    activities_by_id = {row.id: row for row in activities}
    responses = list(
        db.scalars(
            select(ActivityResponse)
            .where(
                ActivityResponse.organisation_id == invitation.organisation_id,
                ActivityResponse.study_id == study_row.id,
                ActivityResponse.participant_id == participant_row.id,
            )
            .order_by(ActivityResponse.id.asc())
        )
    )
    evidence = list(
        db.scalars(
            select(EvidenceFile)
            .where(
                EvidenceFile.organisation_id == invitation.organisation_id,
                EvidenceFile.study_id == study_row.id,
                EvidenceFile.participant_id == participant_row.id,
            )
            .order_by(EvidenceFile.id.asc())
        )
    )
    messages = list_participant_visible_messages(
        db,
        study_id=study_row.id,
        participant_id=participant_row.id,
    )

    response_items = []
    for response_row in responses:
        value = {}
        try:
            value = json.loads(response_row.value_json or "{}")
        except json.JSONDecodeError:
            value = {}
        activity_row = activities_by_id.get(response_row.activity_id)
        response_items.append(
            {
                "activity": activity_row.title if activity_row else "Activity",
                "activity_type": activity_row.activity_type if activity_row else None,
                "status": response_row.status,
                "answer": value.get("answer") if isinstance(value.get("answer"), str) else None,
                "choices": [x for x in value.get("choices", []) if isinstance(x, str)]
                if isinstance(value.get("choices"), list)
                else [],
                "submitted_at": _iso(response_row.submitted_at),
                "updated_at": _iso(response_row.updated_at),
            }
        )

    return {
        "application_name": "Citizen Centric",
        "generated_at": _iso(now()),
        "scope": "current_study",
        "participant_profile": {
            "reference": participant_row.reference,
            "name": participant_row.name,
            "email": participant_row.email,
            "phone": participant_row.phone,
            "status": participant_row.status,
            "consent_status": participant_row.consent_status,
            "communication_preference": participant_row.communication_preference,
            "created_at": _iso(participant_row.created_at),
        },
        "study": {
            "title": study_row.title,
            "description": study_row.description,
            "status": study_row.status,
            "enrolment_status": enrolment.status,
            "enrolled_at": _iso(enrolment.enrolled_at),
        },
        "activity_responses": response_items,
        "evidence_files": [
            {
                "activity": activities_by_id[row.activity_id].title if row.activity_id in activities_by_id else "Activity",
                "filename": row.original_name,
                "content_type": row.content_type,
                "size_bytes": row.size_bytes,
                "scan_status": _participant_evidence_scan_status(row.scan_status),
                "created_at": _iso(row.created_at),
            }
            for row in evidence
        ],
        "messages": [
            {
                "sender": row.sender_type,
                "body": row.body,
                "created_at": _iso(row.created_at),
            }
            for row in messages
        ],
    }


@app.post("/participant-portal/privacy/data-export")
def participant_portal_data_export(
    request: Request,
    csrf_ok: None = Depends(csrf_protect),
    db: Session = Depends(get_db),
):
    _session_row, inv, participant_row, study_row, enrolment = require_participant_portal_context(request, db)
    payload = participant_self_export_payload(db, inv, participant_row, study_row, enrolment)
    audit(
        db,
        inv.organisation_id,
        None,
        "privacy.participant_self_exported",
        "participant",
        participant_row.id,
        str(study_row.id),
    )
    db.commit()
    response = Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="citizen-centric-my-data.json"'},
    )
    _cache_control_no_store(response)
    return response


@app.post("/participant-portal/privacy/withdrawal-request")
def participant_portal_withdrawal_request(
    request: Request,
    confirmed: bool = Form(False),
    csrf_ok: None = Depends(csrf_protect),
    db: Session = Depends(get_db),
):
    if not confirmed:
        raise HTTPException(400, "Please confirm that you want to withdraw from this study.")
    _session_row, inv, participant_row, study_row, _enrolment = require_participant_portal_context(request, db)
    apply_participant_withdrawal(db, inv, participant_row, "study")
    db.add(
        ParticipantPrivacyRequest(
            organisation_id=inv.organisation_id,
            participant_id=participant_row.id,
            study_id=study_row.id,
            request_type="withdrawal",
            scope="study",
            status="completed",
            categories_json=json.dumps(["study_access", "participant_sessions", "invitations", "future_collection"]),
            completed_at=now(),
        )
    )
    db.commit()
    set_flash(request, "success", "You have withdrawn from this study. You can no longer submit material for it.")
    response = RedirectResponse("/join-study", 303)
    clear_public_auth_cookie(response)
    return response


def resolve_participant_portal_evidence(request: Request, db: Session, evidence_id: int):
    _session_row, inv, participant_row, _study_row, _enrolment = require_participant_portal_context(request, db)
    evidence_row = db.scalar(
        select(EvidenceFile).where(
            EvidenceFile.id == evidence_id,
            EvidenceFile.organisation_id == inv.organisation_id,
            EvidenceFile.study_id == inv.study_id,
            EvidenceFile.participant_id == participant_row.id,
        )
    )
    if not evidence_row:
        raise HTTPException(404, "Evidence file was not found.")
    return evidence_row


def refresh_evidence_scan_status(db: Session, evidence_row: EvidenceFile):
    if evidence_row.storage_provider != "azure_blob":
        return
    latest_status, latest_detail = storage.scan_result(evidence_row.stored_name)
    if latest_status != "pending" or evidence_row.scan_status == "pending":
        evidence_row.scan_status = latest_status
        evidence_row.scan_detail = latest_detail
        if latest_status in {"clean", "infected", "scan_failed"}:
            evidence_row.scan_completed_at = now()
        db.commit()


@app.get("/participant-portal/evidence/{evidence_id}/status")
def participant_portal_evidence_status(request: Request, evidence_id: int, db: Session = Depends(get_db)):
    evidence_row = resolve_participant_portal_evidence(request, db, evidence_id)
    refresh_evidence_scan_status(db, evidence_row)
    response = JSONResponse(
        {
            "evidence_id": evidence_row.id,
            "status": _participant_evidence_scan_status(evidence_row.scan_status),
            "downloadable": is_evidence_downloadable(evidence_row.scan_status),
        }
    )
    _cache_control_no_store(response)
    return response


@app.get("/participant-portal/evidence/{evidence_id}")
def participant_portal_evidence_download(request: Request, evidence_id: int, db: Session = Depends(get_db)):
    evidence_row = resolve_participant_portal_evidence(request, db, evidence_id)
    refresh_evidence_scan_status(db, evidence_row)
    ensure_clean_scan_for_download(evidence_row.scan_status)
    if evidence_row.storage_provider == "azure_blob":
        response = RedirectResponse(
            storage.download_url(evidence_row.stored_name, evidence_row.original_name, evidence_row.content_type, settings.azure_sas_minutes),
            303,
        )
        _cache_control_no_store(response)
        return response
    path = storage.path(evidence_row.stored_name)
    if not path.exists():
        raise HTTPException(404, "Stored evidence is unavailable.")
    response = FileResponse(path, media_type=evidence_row.content_type, filename=evidence_row.original_name)
    _cache_control_no_store(response)
    return response


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

    normalised_app_code = normalise_participant_app_access_code(payload.invitation_token)
    access_code = None
    if normalised_app_code:
        access_code = db.scalar(
            select(ParticipantAppAccessCode).where(
                ParticipantAppAccessCode.code_hash == token_hash(normalised_app_code)
            )
        )
        invitation = (
            db.get(ParticipantInvitation, access_code.participant_invitation_id)
            if access_code
            and access_code.redeemed_at is None
            and unexpired(access_code.expires_at)
            else None
        )
    else:
        invitation = resolve_invitation_by_token(db, payload.invitation_token)
    if not invitation or invitation.revoked_at or not unexpired(invitation.expires_at):
        raise HTTPException(400, "This participant link is invalid or expired.")
    if access_code and not invitation.accepted_at:
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
    audit(
        db,
        invitation.organisation_id,
        None,
        "participant.api_session_exchanged",
        "participant_invitation",
        invitation.id,
        "portal" if invitation.accepted_at else "consent_required",
    )
    if access_code:
        access_code.redeemed_at = now()
    db.commit()
    _cache_control_no_store(response)
    return _participant_session_exchange_response(
        raw_token,
        session_row,
        invitation,
        participant_row,
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
            display_name=participant_row.name,
            consent_status=participant_row.consent_status,
        ),
        invitation=InvitationContext(
            study_id=invitation.study_id,
            invitation_status="accepted" if invitation.accepted_at else "valid",
            expires_at=invitation.expires_at,
            accepted_at=invitation.accepted_at,
            requires_study_documents=invitation.consent_bundle_id is not None,
        ),
        next_action="portal" if invitation.accepted_at else "consent_required",
        study_scope=[invitation.study_id],
    )


@app.get(
    "/api/v1/participant/session/available-studies",
    response_model=AvailableStudyListResponse,
)
def participant_api_available_studies(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    _session_row, invitation, participant_row = _resolve_participant_api_context(request, db)
    rows = _participant_switchable_studies(db, invitation, participant_row)
    _cache_control_no_store(response)
    return AvailableStudyListResponse(
        data=[
            StudySummary(
                study_id=study_row.id,
                title=study_row.title,
                description=study_row.description,
                status=study_row.status,
                methodology=study_row.methodology,
                enrolled=True,
            )
            for _candidate, study_row in rows
        ]
    )


@app.post(
    "/api/v1/participant/session/switch",
    response_model=SessionExchangeResponse,
)
def participant_api_session_switch(
    payload: SessionSwitchRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    _require_json_content_type(request)
    source_session, invitation, participant_row = _resolve_participant_api_context(request, db)
    if payload.study_id == invitation.study_id:
        raise HTTPException(400, "The requested study is already active.")

    _enforce_rate_limit(
        request,
        db,
        scope="participant_api_session_switch",
        ip_limit=settings.rate_limit_portal_write_ip,
        account_key=f"invitation:{invitation.id}",
        account_limit=settings.rate_limit_portal_write_token,
    )
    available = _participant_switchable_studies(db, invitation, participant_row)
    target = next(
        (
            candidate
            for candidate, study_row in available
            if study_row.id == payload.study_id
        ),
        None,
    )
    if target is None:
        raise HTTPException(403, "Requested study is outside participant scope.")

    # Preserve the one-active-session-per-invitation safeguard.  The source
    # session stays valid until the new token has been delivered, so a dropped
    # response cannot strand the participant outside both studies.
    target_sessions = db.scalars(
        select(PublicAuthSession).where(
            PublicAuthSession.scope == PARTICIPANT_API_SCOPE,
            PublicAuthSession.participant_invitation_id == target.id,
            PublicAuthSession.revoked_at.is_(None),
        )
    ).all()
    for existing in target_sessions:
        if existing.id != source_session.id:
            existing.revoked_at = now()

    raw_token, target_session = create_participant_api_session(
        db,
        participant_invitation_id=target.id,
        ttl_seconds=settings.session_max_age_seconds,
    )
    audit(
        db,
        invitation.organisation_id,
        None,
        "participant.api_session_switched",
        "participant_invitation",
        target.id,
        str(target.study_id),
    )
    db.commit()
    _cache_control_no_store(response)
    return _participant_session_exchange_response(
        raw_token,
        target_session,
        target,
        participant_row,
    )


@app.get("/api/v1/participant/profile", response_model=ParticipantProfile)
def participant_api_profile(request: Request, response: Response, db: Session = Depends(get_db)):
    _session_row, _invitation, participant_row = _resolve_participant_api_context(request, db)
    _cache_control_no_store(response)
    return ParticipantProfile(
        display_name=participant_row.name,
        communication_preference=participant_row.communication_preference,
        consent_status=participant_row.consent_status,
    )


@app.get("/api/v1/participant/legal-documents", response_model=StudyLegalDocumentsResponse)
def participant_api_legal_documents(request: Request, response: Response, db: Session = Depends(get_db)):
    _session_row, invitation, _participant_row = _resolve_participant_api_context(request, db)
    study_row = study(db, invitation.study_id, invitation.organisation_id)
    governance = governance_for_study(db, study_row)
    try:
        bound_documents = require_bound_documents(db, invitation, governance)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    documents = [
        LegalDocumentReference(
            document_type=item.document_type,
            title=item.title,
            version=item.version,
            reference=item.reference,
            effective_date=item.effective_date,
            body=item.body,
            content_sha256=item.content_sha256,
        )
        for item in bound_documents
    ]
    _cache_control_no_store(response)
    return StudyLegalDocumentsResponse(study_id=study_row.id, bundle_id=invitation.consent_bundle_id, documents=documents)


@app.put("/api/v1/participant/profile", response_model=ParticipantProfile)
def participant_api_profile_update(
    payload: UpdateParticipantProfileRequest,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=128),
    db: Session = Depends(get_db),
):
    _require_json_content_type(request)
    invitation, participant_row, _study_row = _resolve_participant_api_study_scope(request, db, write_scope=True)
    try:
        _record_participant_idempotency(db, invitation.id, "profile_update", idempotency_key)
        participant_row.communication_preference = payload.communication_preference
        audit(db, invitation.organisation_id, None, "participant.profile_updated", "participant", participant_row.id, "communication_preference")
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    _cache_control_no_store(response)
    return ParticipantProfile(display_name=participant_row.name, communication_preference=participant_row.communication_preference, consent_status=participant_row.consent_status)


@app.post("/api/v1/participant/consent", response_model=ConsentAcceptanceResponse)
def participant_api_consent_accept(
    payload: ConsentAcceptanceRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    _require_json_content_type(request)
    _session_row, invitation, participant_row = _resolve_participant_api_context(request, db)
    if invitation.revoked_at or not unexpired(invitation.expires_at):
        raise _participant_api_unauthorised()
    if not invitation.accepted_at:
        governance = governance_for_study(db, study(db, invitation.study_id, invitation.organisation_id))
        try:
            bound_documents = require_bound_documents(db, invitation, governance)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        if bound_documents and payload.document_hashes != {item.document_type: item.content_sha256 for item in bound_documents}:
            raise HTTPException(409, "The consent documents have not been confirmed. Review the exact study documents and try again.")
        capture_consent_document_evidence(
            invitation,
            governance,
        )
        grant_participant_consent(invitation, participant_row, now())
        audit(db, invitation.organisation_id, None, "participant.api_consent_accepted", "participant", participant_row.id, str(invitation.study_id))
        db.commit()
    _cache_control_no_store(response)
    return ConsentAcceptanceResponse(consent_status="granted", accepted_at=invitation.accepted_at)


@app.get("/api/v1/participant/submissions", response_model=SubmissionHistoryResponse)
def participant_api_submission_history(
    request: Request,
    response: Response,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    _invitation, participant_row, study_row = _resolve_participant_api_study_scope(request, db, write_scope=False)
    rows = db.execute(
        select(ActivityResponse, Activity.title, Activity.prompt)
        .join(Activity, Activity.id == ActivityResponse.activity_id)
        .where(
            ActivityResponse.organisation_id == participant_row.organisation_id,
            ActivityResponse.study_id == study_row.id,
            ActivityResponse.participant_id == participant_row.id,
        ).order_by(ActivityResponse.updated_at.desc()).limit(limit)
    ).all()
    response_ids = [item.id for item, _title, _prompt in rows]
    evidence_by_response: dict[int, list[EvidenceFile]] = {}
    if response_ids:
        evidence_rows = db.scalars(
            select(EvidenceFile)
            .where(
                EvidenceFile.organisation_id == participant_row.organisation_id,
                EvidenceFile.study_id == study_row.id,
                EvidenceFile.participant_id == participant_row.id,
                EvidenceFile.response_id.in_(response_ids),
            )
            .order_by(EvidenceFile.created_at.asc(), EvidenceFile.id.asc())
        ).all()
        for evidence_row in evidence_rows:
            evidence_by_response.setdefault(int(evidence_row.response_id), []).append(evidence_row)
    project_row = db.scalar(
        select(Project).where(
            Project.id == study_row.project_id,
            Project.organisation_id == participant_row.organisation_id,
        )
    )
    data: list[SubmissionHistoryItem] = []
    for item, title, prompt in rows:
        value = _response_value_from_json(item.value_json)
        data.append(
            SubmissionHistoryItem(
                response_id=item.id,
                activity_id=item.activity_id,
                activity_title=title,
                activity_prompt=prompt or None,
                study_title=study_row.title,
                project_title=project_row.title if project_row else study_row.title,
                answer=value.answer if value else None,
                choices=value.choices if value else [],
                location=_participant_response_location(item),
                evidence=[
                    SubmissionEvidenceItem(
                        evidence_id=evidence.id,
                        original_name=evidence.original_name,
                        content_type=evidence.content_type,
                        scan_status=_participant_evidence_scan_status(evidence.scan_status),
                        downloadable=is_evidence_downloadable(evidence.scan_status),
                        created_at=evidence.created_at,
                    )
                    for evidence in evidence_by_response.get(item.id, [])
                ],
                status=item.status,
                submitted_at=item.submitted_at,
                updated_at=item.updated_at,
            )
        )
    _cache_control_no_store(response)
    return SubmissionHistoryResponse(
        study_id=study_row.id,
        data=data,
        pagination=Pagination(limit=limit, has_more=False),
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
    if participant_row.consent_status != ConsentStatus.granted.value:
        raise HTTPException(403, "Participant consent is no longer active.")

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
            StudyEnrolment.status != "withdrawn",
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


@app.get(
    "/api/v1/participant/activities",
    response_model=ActivityListResponse,
    response_model_exclude_unset=True,
)
def participant_api_activities(
    request: Request,
    response: Response,
    study_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
):
    _session_row, invitation, participant_row = _resolve_participant_api_context(request, db)
    if not invitation.accepted_at:
        raise HTTPException(403, "Participant consent has not been accepted.")
    if participant_row.consent_status != ConsentStatus.granted.value:
        raise HTTPException(403, "Participant consent is no longer active.")
    if study_id is not None and study_id != invitation.study_id:
        raise HTTPException(403, "Requested study is outside participant scope.")

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
            StudyEnrolment.status != "withdrawn",
        )
    ) is not None
    if not enrolled:
        raise HTTPException(403, "Participant is not enrolled in this study.")

    activities = list(
        db.scalars(
            select(Activity)
            .where(
                Activity.organisation_id == invitation.organisation_id,
                Activity.study_id == invitation.study_id,
            )
            .order_by(Activity.position.asc(), Activity.id.asc())
        )
    )

    response_rows = list(
        db.scalars(
            select(ActivityResponse).where(
                ActivityResponse.organisation_id == invitation.organisation_id,
                ActivityResponse.study_id == invitation.study_id,
                ActivityResponse.participant_id == participant_row.id,
            )
        )
    )
    responses_by_activity_id: dict[int, list[ActivityResponse]] = {}
    for response_row in response_rows:
        responses_by_activity_id.setdefault(response_row.activity_id, []).append(response_row)

    data: list[ActivitySummary] = []
    for activity_row in activities:
        window = activity_window(study_row, activity_row, now())
        activity_responses = responses_by_activity_id.get(activity_row.id, [])
        response_row = max(activity_responses, key=lambda row: row.updated_at) if activity_responses else None
        response_summary = (
            ActivityResponseSummary(
                status=response_row.status,
                submitted_at=response_row.submitted_at,
                updated_at=response_row.updated_at,
            )
            if response_row
            else None
        )
        item = _participant_activity_summary(activity_row, window)
        item.allow_multiple_entries = activity_row.allow_multiple_entries
        item.submitted_entry_count = sum(row.status == "submitted" for row in activity_responses)
        if response_summary:
            item.response = response_summary
        data.append(item)

    _cache_control_no_store(response)
    return ActivityListResponse(data=data)


def _response_value_from_json(value_json: str | None) -> ActivityResponseValue | None:
    try:
        payload = json.loads(value_json or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    value = ActivityResponseValue()
    if "answer" in payload and isinstance(payload["answer"], str):
        value.answer = payload["answer"]
    if "choices" in payload and isinstance(payload["choices"], list):
        value.choices = [x for x in payload["choices"] if isinstance(x, str)]
    if "evidence_id" in payload and isinstance(payload["evidence_id"], int) and payload["evidence_id"] > 0:
        value.evidence_id = payload["evidence_id"]
    if not value.model_fields_set:
        return None
    return value


def _participant_response_location(response_row: ActivityResponse) -> EntryLocation | None:
    """Return a complete stored location only; incomplete legacy rows stay hidden."""
    if (
        response_row.location_latitude is None
        or response_row.location_longitude is None
        or response_row.location_accuracy_metres is None
        or response_row.location_source != "device"
        or response_row.location_captured_at is None
    ):
        return None
    captured_at = response_row.location_captured_at
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    return EntryLocation(
        latitude=response_row.location_latitude,
        longitude=response_row.location_longitude,
        accuracy_metres=response_row.location_accuracy_metres,
        source="device",
        captured_at=captured_at,
    )


def _store_participant_response_location(
    response_row: ActivityResponse,
    location: EntryLocation | None,
) -> None:
    if location is None:
        response_row.location_latitude = None
        response_row.location_longitude = None
        response_row.location_accuracy_metres = None
        response_row.location_source = None
        response_row.location_captured_at = None
        return
    captured_at = location.captured_at
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise HTTPException(400, "Location capture time must include a timezone.")
    if captured_at > now() + timedelta(minutes=5):
        raise HTTPException(400, "Location capture time cannot be in the future.")
    response_row.location_latitude = location.latitude
    response_row.location_longitude = location.longitude
    response_row.location_accuracy_metres = location.accuracy_metres
    response_row.location_source = location.source
    response_row.location_captured_at = captured_at.astimezone(timezone.utc)


def _participant_activity_options(activity_row: Activity) -> list[str] | None:
    if activity_row.activity_type not in {"single_choice", "multiple_choice", "ranking"}:
        return None

    try:
        payload = json.loads(activity_row.options_json or "[]")
    except json.JSONDecodeError:
        return []

    if not isinstance(payload, list):
        return []

    return [option.strip() for option in payload if isinstance(option, str) and option.strip()]


def _validate_activity_response_value(
    activity_row: Activity,
    value: dict[str, object],
    action: str,
) -> dict[str, object]:
    if action not in {"draft", "submit"}:
        raise HTTPException(400, "Invalid response action.")

    answer = str(value.get("answer") or "")
    raw_choices = value.get("choices") or []
    choices = [x.strip() for x in raw_choices if isinstance(x, str) and x.strip()]
    value["answer"] = answer
    value["choices"] = choices

    if activity_row.activity_type not in {"single_choice", "multiple_choice", "ranking"}:
        return value

    if answer.strip():
        raise HTTPException(400, "Choice activities must use the available options.")

    options = _participant_activity_options(activity_row) or []
    if len(options) < 2:
        raise HTTPException(409, "This activity does not have enough configured options.")
    if len(choices) != len(set(choices)):
        raise HTTPException(400, "Each option may only be selected once.")
    if any(choice not in options for choice in choices):
        raise HTTPException(400, "The response contains an option that is not available.")

    if activity_row.activity_type == "single_choice" and len(choices) > 1:
        raise HTTPException(400, "Select one option only.")
    if activity_row.activity_type == "ranking" and action == "submit" and choices and len(choices) != len(options):
        raise HTTPException(400, "Rank every option before submitting.")
    if action == "submit" and activity_row.required and not choices:
        raise HTTPException(400, "A response is required.")

    return value


def _participant_activity_summary(activity_row: Activity, window: dict[str, object]) -> ActivitySummary:
    item = ActivitySummary(
        activity_id=activity_row.id,
        title=activity_row.title,
        prompt=activity_row.prompt or None,
        activity_type=activity_row.activity_type,
        required=bool(activity_row.required),
        allow_multiple_entries=bool(activity_row.allow_multiple_entries),
        allow_participant_location=bool(activity_row.allow_participant_location),
        position=activity_row.position,
        availability=ActivityAvailability(
            status=str(window.get("status") or "open"),
            release_at=window.get("release_at"),
            due_at=window.get("due_at"),
        ),
    )

    options = _participant_activity_options(activity_row)
    if options is not None:
        item.options = options

    return item


@app.get(
    "/api/v1/participant/activities/{activity_id}",
    response_model=ActivityDetailResponse,
    response_model_exclude_unset=True,
)
def participant_api_activity_detail(
    request: Request,
    response: Response,
    activity_id: int = ApiPath(..., ge=1),
    db: Session = Depends(get_db),
):
    _session_row, invitation, participant_row = _resolve_participant_api_context(request, db)
    if not invitation.accepted_at:
        raise HTTPException(403, "Participant consent has not been accepted.")
    if participant_row.consent_status != ConsentStatus.granted.value:
        raise HTTPException(403, "Participant consent is no longer active.")

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
            StudyEnrolment.status != "withdrawn",
        )
    ) is not None
    if not enrolled:
        raise HTTPException(403, "Participant is not enrolled in this study.")

    activity_row = db.scalar(
        select(Activity).where(
            Activity.id == activity_id,
            Activity.organisation_id == invitation.organisation_id,
            Activity.study_id == invitation.study_id,
        )
    )
    if not activity_row:
        raise HTTPException(404, "Activity not found.")

    response_row = db.scalar(
        select(ActivityResponse).where(
            ActivityResponse.organisation_id == invitation.organisation_id,
            ActivityResponse.study_id == invitation.study_id,
            ActivityResponse.activity_id == activity_row.id,
            ActivityResponse.participant_id == participant_row.id,
        )
    )

    window = activity_window(study_row, activity_row, now())
    result = ActivityDetailResponse(activity=_participant_activity_summary(activity_row, window))

    if response_row:
        response_item = ActivityDetailResponseItem(
            response_id=response_row.id,
            status=response_row.status,
        )
        value = _response_value_from_json(response_row.value_json)
        if value is not None:
            response_item.value = value
            response_item.value.location = _participant_response_location(response_row)
        if response_row.submitted_at is not None:
            response_item.submitted_at = response_row.submitted_at
        if response_row.updated_at is not None:
            response_item.updated_at = response_row.updated_at
        result.response = response_item

    _cache_control_no_store(response)
    return result


def _resolve_participant_api_activity_scope(
    request: Request,
    db: Session,
    activity_id: int,
) -> tuple[ParticipantInvitation, Participant, Study, Activity]:
    _session_row, invitation, participant_row = _resolve_participant_api_context(request, db)
    if not invitation.accepted_at:
        raise HTTPException(403, "Participant consent has not been accepted.")
    if participant_row.consent_status != ConsentStatus.granted.value:
        raise HTTPException(403, "Participant consent is no longer active.")

    _enforce_rate_limit(
        request,
        db,
        scope="participant_portal_write",
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
            StudyEnrolment.status != "withdrawn",
        )
    ) is not None
    if not enrolled:
        raise HTTPException(403, "Participant is not enrolled in this study.")

    activity_row = db.scalar(
        select(Activity).where(
            Activity.id == activity_id,
            Activity.organisation_id == invitation.organisation_id,
            Activity.study_id == invitation.study_id,
        )
    )
    if not activity_row:
        raise HTTPException(404, "Activity not found.")

    window = activity_window(study_row, activity_row, now())
    if window["status"] == "upcoming":
        raise HTTPException(409, "This activity is not available yet.")
    if window["status"] == "closed":
        raise HTTPException(409, "The due date for this activity has passed.")

    return invitation, participant_row, study_row, activity_row


def _participant_response_value_from_payload(
    payload: DraftResponseRequest,
    activity_row: Activity,
    action: str,
) -> dict[str, object]:
    cleaned_choices = [x.strip() for x in payload.choices if isinstance(x, str) and x.strip()]
    value: dict[str, object] = {
        "answer": payload.answer or "",
        "choices": cleaned_choices,
    }
    if payload.evidence_id is not None:
        value["evidence_id"] = payload.evidence_id
    if payload.location is not None and not activity_row.allow_participant_location:
        raise HTTPException(400, "Location is not enabled for this activity.")
    return _validate_activity_response_value(activity_row, value, action)


def _participant_evidence_scan_status(scan_status: str | None) -> str:
    token = (scan_status or "").strip().lower().replace(" ", "_")
    if token in {"pending", "clean", "infected", "scan_failed"}:
        return token
    if token in {"error", "failed", "not_scanned", "not_configured"}:
        return "scan_failed"
    return "pending"


def _participant_evidence_metadata(evidence_row: EvidenceFile) -> EvidenceMetadata:
    return EvidenceMetadata(
        evidence_id=evidence_row.id,
        activity_id=evidence_row.activity_id,
        original_name=evidence_row.original_name,
        content_type=evidence_row.content_type,
        size_bytes=evidence_row.size_bytes,
        scan_status=_participant_evidence_scan_status(evidence_row.scan_status),
        created_at=evidence_row.created_at,
    )


def _resolve_participant_api_evidence_scope(
    request: Request,
    db: Session,
    evidence_id: int,
) -> tuple[ParticipantInvitation, Participant, Study, EvidenceFile]:
    _session_row, invitation, participant_row = _resolve_participant_api_context(request, db)
    if not invitation.accepted_at:
        raise HTTPException(403, "Participant consent has not been accepted.")
    if participant_row.consent_status != ConsentStatus.granted.value:
        raise HTTPException(403, "Participant consent is no longer active.")

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
            StudyEnrolment.status != "withdrawn",
        )
    ) is not None
    if not enrolled:
        raise HTTPException(403, "Participant is not enrolled in this study.")

    evidence_row = db.scalar(
        select(EvidenceFile).where(
            EvidenceFile.id == evidence_id,
            EvidenceFile.organisation_id == invitation.organisation_id,
            EvidenceFile.study_id == invitation.study_id,
            EvidenceFile.participant_id == participant_row.id,
        )
    )
    if not evidence_row:
        raise HTTPException(404, "Evidence not found.")

    return invitation, participant_row, study_row, evidence_row


def _resolve_participant_api_study_scope(
    request: Request,
    db: Session,
    *,
    write_scope: bool,
) -> tuple[ParticipantInvitation, Participant, Study]:
    _session_row, invitation, participant_row = _resolve_participant_api_context(request, db)
    if not invitation.accepted_at:
        raise HTTPException(403, "Participant consent has not been accepted.")
    if participant_row.consent_status != ConsentStatus.granted.value:
        raise HTTPException(403, "Participant consent is no longer active.")

    _enforce_rate_limit(
        request,
        db,
        scope="participant_portal_write" if write_scope else "participant_portal_read",
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
            StudyEnrolment.status != "withdrawn",
        )
    ) is not None
    if not enrolled:
        raise HTTPException(403, "Participant is not enrolled in this study.")

    return invitation, participant_row, study_row


def _record_participant_idempotency(
    db: Session,
    invitation_id: int,
    action: str,
    idempotency_key: str | None,
) -> None:
    if not idempotency_key:
        return
    scoped_key = f"participant:{invitation_id}:{action}:{idempotency_key}"
    if token_already_redeemed(db, "participant_api_idempotency", scoped_key):
        raise HTTPException(409, "Duplicate request was already processed.")
    record_token_redemption(db, "participant_api_idempotency", scoped_key)


def _update_activity_response_if_not_submitted(
    db: Session,
    response_id: int,
    value: dict[str, object],
    action: str,
) -> bool:
    submitted_at = now() if action == "submit" else None
    status = "submitted" if action == "submit" else "draft"
    result = db.execute(
        update(ActivityResponse)
        .where(
            ActivityResponse.id == response_id,
            ActivityResponse.status != "submitted",
        )
        .values(
            value_json=json.dumps(value),
            status=status,
            submitted_at=submitted_at,
            updated_at=now(),
        )
    )
    return result.rowcount == 1


def _require_json_content_type(request: Request) -> None:
    content_type = (request.headers.get("content-type") or "").strip().lower()
    if not content_type.startswith("application/json"):
        raise HTTPException(415, "Unsupported content type.")
    return None


@app.put("/api/v1/participant/activities/{activity_id}/draft", response_model=DraftResponseResult)
def participant_api_activity_response_draft(
    payload: DraftResponseRequest,
    request: Request,
    response: Response,
    activity_id: int = ApiPath(..., ge=1),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=128),
    _content_type_ok: None = Depends(_require_json_content_type),
    db: Session = Depends(get_db),
):
    invitation, participant_row, _study_row, activity_row = _resolve_participant_api_activity_scope(request, db, activity_id)
    entry_key_hash = token_hash(idempotency_key) if idempotency_key else None
    value = _participant_response_value_from_payload(payload, activity_row, "draft")

    existing = db.scalar(
        select(ActivityResponse).where(
            ActivityResponse.organisation_id == invitation.organisation_id,
            ActivityResponse.study_id == invitation.study_id,
            ActivityResponse.activity_id == activity_row.id,
            ActivityResponse.participant_id == participant_row.id,
        ).where(ActivityResponse.client_entry_key_hash == entry_key_hash)
        if activity_row.allow_multiple_entries and entry_key_hash else select(ActivityResponse).where(
            ActivityResponse.organisation_id == invitation.organisation_id,
            ActivityResponse.study_id == invitation.study_id,
            ActivityResponse.activity_id == activity_row.id,
            ActivityResponse.participant_id == participant_row.id,
        )
    )
    if existing and existing.status == "submitted":
        raise HTTPException(409, "Activity response has already been submitted.")

    if payload.evidence_id is not None:
        evidence_ok = db.scalar(
            select(EvidenceFile.id).where(
                EvidenceFile.id == payload.evidence_id,
                EvidenceFile.organisation_id == invitation.organisation_id,
                EvidenceFile.study_id == invitation.study_id,
                EvidenceFile.activity_id == activity_row.id,
                EvidenceFile.participant_id == participant_row.id,
            )
        ) is not None
        if not evidence_ok:
            raise HTTPException(400, "Evidence reference is invalid for this activity.")

    try:
        response_row = existing or resolve_or_create_activity_response(
            db,
            organisation_id=invitation.organisation_id,
            study_id=invitation.study_id,
            activity_id=activity_row.id,
            participant_id=participant_row.id,
            repeatable=activity_row.allow_multiple_entries,
            client_entry_key_hash=entry_key_hash,
        )
        if existing:
            if not _update_activity_response_if_not_submitted(db, response_row.id, value, "draft"):
                raise HTTPException(409, "Activity response has already been submitted.")
            db.refresh(response_row)
        else:
            apply_response_action(response_row, value, "draft", now())
        _store_participant_response_location(response_row, payload.location)
        audit(
            db,
            invitation.organisation_id,
            None,
            "activity.draft",
            "activity_response",
            response_row.id,
            str(activity_row.id),
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Activity response state conflict.")
    except Exception:
        db.rollback()
        raise

    _cache_control_no_store(response)
    return DraftResponseResult(
        response_id=response_row.id,
        status="draft",
        updated_at=response_row.updated_at,
    )


@app.post("/api/v1/participant/activities/{activity_id}/submit", response_model=SubmittedResponseResult)
def participant_api_activity_response_submit(
    payload: SubmitResponseRequest,
    request: Request,
    response: Response,
    activity_id: int = ApiPath(..., ge=1),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=128),
    _content_type_ok: None = Depends(_require_json_content_type),
    db: Session = Depends(get_db),
):
    invitation, participant_row, _study_row, activity_row = _resolve_participant_api_activity_scope(request, db, activity_id)
    entry_key_hash = token_hash(idempotency_key) if idempotency_key else None
    value = _participant_response_value_from_payload(payload, activity_row, "submit")
    has_answer = bool((payload.answer or "").strip())
    has_choices = bool(value.get("choices"))
    has_evidence = payload.evidence_id is not None
    if activity_row.activity_type in {"photo", "audio", "video", "file"} and not has_evidence:
        raise HTTPException(400, "Upload the required evidence before submitting this activity.")
    if activity_row.required and not has_answer and not has_choices and not has_evidence:
        raise HTTPException(400, "A response is required.")

    if payload.evidence_id is not None:
        evidence_ok = db.scalar(
            select(EvidenceFile.id).where(
                EvidenceFile.id == payload.evidence_id,
                EvidenceFile.organisation_id == invitation.organisation_id,
                EvidenceFile.study_id == invitation.study_id,
                EvidenceFile.activity_id == activity_row.id,
                EvidenceFile.participant_id == participant_row.id,
            )
        ) is not None
        if not evidence_ok:
            raise HTTPException(400, "Evidence reference is invalid for this activity.")

    try:
        existing = resolve_or_create_activity_response(
            db,
            organisation_id=invitation.organisation_id,
            study_id=invitation.study_id,
            activity_id=activity_row.id,
            participant_id=participant_row.id,
            repeatable=activity_row.allow_multiple_entries,
            client_entry_key_hash=entry_key_hash,
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Activity response state conflict.")
    if existing and existing.status == "submitted":
        existing_value = json.loads(existing.value_json or "{}")
        existing_location = _participant_response_location(existing)
        if existing_value != value or (
            (existing_location.model_dump(mode="json") if existing_location else None)
            != (payload.location.model_dump(mode="json") if payload.location else None)
        ):
            raise HTTPException(409, "Activity response has already been submitted.")
        _cache_control_no_store(response)
        return SubmittedResponseResult(
            response_id=existing.id,
            status="submitted",
            submitted_at=existing.submitted_at or existing.updated_at,
            updated_at=existing.updated_at,
        )

    try:
        response_row = existing
        if not _update_activity_response_if_not_submitted(db, response_row.id, value, "submit"):
            raise HTTPException(409, "Activity response has already been submitted.")
        db.refresh(response_row)
        _store_participant_response_location(response_row, payload.location)
        audit(
            db,
            invitation.organisation_id,
            None,
            "activity.submitted",
            "activity_response",
            response_row.id,
            str(activity_row.id),
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Activity response state conflict.")
    except Exception:
        db.rollback()
        raise

    _cache_control_no_store(response)
    return SubmittedResponseResult(
        response_id=response_row.id,
        status="submitted",
        submitted_at=response_row.submitted_at or response_row.updated_at,
        updated_at=response_row.updated_at,
    )


@app.post(
    "/api/v1/participant/activities/{activity_id}/evidence-uploads",
    response_model=EvidenceUploadResponse,
    status_code=201,
)
def participant_api_activity_evidence_upload(
    request: Request,
    response: Response,
    activity_id: int = ApiPath(..., ge=1),
    form_activity_id: int = Form(..., alias="activity_id", ge=1),
    file: UploadFile = File(...),
    note: str | None = Form(default=None, max_length=2000),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=128),
    db: Session = Depends(get_db),
):
    del note
    if form_activity_id != activity_id:
        raise HTTPException(400, "Form activity_id does not match path activity_id.")

    invitation, participant_row, _study_row, activity_row = _resolve_participant_api_activity_scope(request, db, activity_id)
    upload_key_hash = token_hash(idempotency_key) if idempotency_key else None
    if upload_key_hash:
        previously_uploaded = db.scalar(
            select(EvidenceFile).where(
                EvidenceFile.organisation_id == invitation.organisation_id,
                EvidenceFile.study_id == invitation.study_id,
                EvidenceFile.participant_id == participant_row.id,
                EvidenceFile.activity_id == activity_row.id,
                EvidenceFile.upload_key_hash == upload_key_hash,
            )
        )
        if previously_uploaded:
            _cache_control_no_store(response)
            return EvidenceUploadResponse(
                evidence=_participant_evidence_metadata(previously_uploaded)
            )
    existing_response = db.scalar(
        select(ActivityResponse).where(
            ActivityResponse.organisation_id == invitation.organisation_id,
            ActivityResponse.study_id == invitation.study_id,
            ActivityResponse.activity_id == activity_row.id,
            ActivityResponse.participant_id == participant_row.id,
        ).where(
            ActivityResponse.client_entry_key_hash == upload_key_hash
        ) if activity_row.allow_multiple_entries and upload_key_hash else select(ActivityResponse).where(
            ActivityResponse.organisation_id == invitation.organisation_id,
            ActivityResponse.study_id == invitation.study_id,
            ActivityResponse.activity_id == activity_row.id,
            ActivityResponse.participant_id == participant_row.id,
        )
    )
    if existing_response and existing_response.status == "submitted":
        raise HTTPException(409, "Activity response has already been submitted.")

    original = Path(file.filename or "").name
    if not original:
        raise HTTPException(400, "A file is required.")
    validate_evidence_upload_metadata(original, file.content_type, activity_row.activity_type)

    try:
        stored = storage.save_stream(file.file, original, settings.max_upload_mb * 1024 * 1024)
    except ValueError as exc:
        raise HTTPException(413, str(exc))

    stored_key = stored.key
    try:
        if stored.provider == "local":
            local_path = storage.path(stored.key)
            scan_status, scan_detail = scan_file(local_path)
            if scan_status == "infected":
                delete_stored_object_safely(stored.key, "infected")
                audit(db, invitation.organisation_id, None, "evidence.rejected", "activity", activity_row.id, scan_detail)
                db.commit()
                raise HTTPException(400, "The uploaded file failed malware screening.")
        else:
            scan_status, scan_detail = "pending", "Awaiting Microsoft Defender for Storage on-upload scan."

        response_row = existing_response or resolve_or_create_activity_response(
            db,
            organisation_id=invitation.organisation_id,
            study_id=invitation.study_id,
            activity_id=activity_row.id,
            participant_id=participant_row.id,
            repeatable=activity_row.allow_multiple_entries,
            client_entry_key_hash=upload_key_hash,
        )
        db.flush()
        evidence_row = build_evidence_file(
            organisation_id=invitation.organisation_id,
            study_id=invitation.study_id,
            activity_id=activity_row.id,
            participant_id=participant_row.id,
            response_id=response_row.id,
            original_name=original,
            stored_name=stored.key,
            content_type=file.content_type or "application/octet-stream",
            size_bytes=stored.size,
            sha256_hex=stored.sha256_hex,
            scan_status=scan_status,
            scan_detail=scan_detail,
            storage_provider=stored.provider,
            blob_uri=stored.uri,
        )
        evidence_row.upload_key_hash = upload_key_hash
        db.add(evidence_row)
        db.flush()
        if activity_row.activity_type in {"photo", "audio", "video", "file"}:
            apply_response_action(
                response_row,
                {"answer": "", "choices": [], "evidence_id": evidence_row.id},
                "submit",
                now(),
            )
            audit(
                db,
                invitation.organisation_id,
                None,
                "activity.submitted",
                "activity_response",
                response_row.id,
                str(activity_row.id),
            )
        audit(db, invitation.organisation_id, None, "evidence.uploaded", "evidence_file", evidence_row.id, str(activity_row.id))
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        delete_stored_object_safely(stored_key, "upload_processing_failed")
        raise

    _cache_control_no_store(response)
    return EvidenceUploadResponse(evidence=_participant_evidence_metadata(evidence_row))


@app.get(
    "/api/v1/participant/evidence/{evidence_id}/status",
    response_model=EvidenceStatusResponse,
)
def participant_api_evidence_status(
    request: Request,
    response: Response,
    evidence_id: int = ApiPath(..., ge=1),
    db: Session = Depends(get_db),
):
    _invitation, _participant_row, _study_row, evidence_row = _resolve_participant_api_evidence_scope(request, db, evidence_id)

    if evidence_row.storage_provider == "azure_blob":
        latest_status, latest_detail = storage.scan_result(evidence_row.stored_name)
        if latest_status != "pending" or evidence_row.scan_status == "pending":
            evidence_row.scan_status = latest_status
            evidence_row.scan_detail = latest_detail
            if latest_status in {"clean", "infected", "scan_failed"}:
                evidence_row.scan_completed_at = now()
            db.commit()

    _cache_control_no_store(response)
    return EvidenceStatusResponse(
        evidence=_participant_evidence_metadata(evidence_row),
        downloadable=is_evidence_downloadable(evidence_row.scan_status),
    )


@app.get("/api/v1/participant/evidence/{evidence_id}")
def participant_api_evidence_download(
    request: Request,
    evidence_id: int = ApiPath(..., ge=1),
    db: Session = Depends(get_db),
):
    _invitation, _participant, _study, evidence_row = _resolve_participant_api_evidence_scope(
        request, db, evidence_id
    )
    refresh_evidence_scan_status(db, evidence_row)
    ensure_clean_scan_for_download(evidence_row.scan_status)
    if evidence_row.storage_provider == "azure_blob":
        response = RedirectResponse(
            storage.download_url(
                evidence_row.stored_name,
                evidence_row.original_name,
                evidence_row.content_type,
                settings.azure_sas_minutes,
            ),
            303,
        )
    else:
        path = storage.path(evidence_row.stored_name)
        if not path.exists():
            raise HTTPException(404, "Stored evidence is unavailable.")
        response = FileResponse(
            path,
            media_type=evidence_row.content_type,
            filename=evidence_row.original_name,
        )
    _cache_control_no_store(response)
    return response


@app.get("/api/v1/participant/messages", response_model=MessageListResponse)
def participant_api_messages(
    request: Request,
    response: Response,
    cursor: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    invitation, participant_row, study_row = _resolve_participant_api_study_scope(request, db, write_scope=False)
    del invitation
    rows = list_participant_visible_messages(
        db,
        study_id=study_row.id,
        participant_id=participant_row.id,
    )
    data = [
        ParticipantMessageSummary(
            message_id=row.id,
            sender_type=row.sender_type,
            body=row.body,
            created_at=row.created_at,
        )
        for row in rows[:limit]
    ]
    _cache_control_no_store(response)
    return MessageListResponse(
        data=data,
        pagination=Pagination(
            cursor=cursor,
            next_cursor=None,
            limit=limit,
            has_more=False,
        ),
    )


@app.post("/api/v1/participant/messages", response_model=CreateMessageResponse, status_code=201)
def participant_api_message_create(
    payload: CreateMessageRequest,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=128),
    _content_type_ok: None = Depends(_require_json_content_type),
    db: Session = Depends(get_db),
):
    invitation, participant_row, study_row = _resolve_participant_api_study_scope(request, db, write_scope=True)
    body = payload.body.strip()
    if not body:
        raise HTTPException(400, "Message body is required.")

    scoped_idempotency_key = (
        f"participant:{invitation.id}:messages_create:{idempotency_key}"
        if idempotency_key
        else None
    )
    idempotency_key_hash = (
        token_hash(scoped_idempotency_key) if scoped_idempotency_key else None
    )
    if idempotency_key_hash:
        existing = db.scalar(
            select(ParticipantMessage).where(
                ParticipantMessage.organisation_id == invitation.organisation_id,
                ParticipantMessage.study_id == invitation.study_id,
                ParticipantMessage.participant_id == participant_row.id,
                ParticipantMessage.idempotency_key_hash == idempotency_key_hash,
            )
        )
        if existing:
            if existing.body != body:
                raise HTTPException(409, "Idempotency key was already used for another message.")
            _cache_control_no_store(response)
            return CreateMessageResponse(
                message=ParticipantMessageSummary(
                    message_id=existing.id,
                    sender_type=existing.sender_type,
                    body=existing.body,
                    created_at=existing.created_at,
                )
            )

    try:
        _record_participant_idempotency(db, invitation.id, "messages_create", idempotency_key)
        row = create_participant_message(
            invitation,
            body=body,
        )
        row.idempotency_key_hash = idempotency_key_hash
        db.add(row)
        db.flush()
        audit(
            db,
            invitation.organisation_id,
            None,
            "participant.message_created",
            "participant_message",
            row.id,
            str(study_row.id),
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        if idempotency_key_hash:
            existing = db.scalar(
                select(ParticipantMessage).where(
                    ParticipantMessage.organisation_id == invitation.organisation_id,
                    ParticipantMessage.study_id == invitation.study_id,
                    ParticipantMessage.participant_id == participant_row.id,
                    ParticipantMessage.idempotency_key_hash == idempotency_key_hash,
                )
            )
            if existing and existing.body == body:
                _cache_control_no_store(response)
                return CreateMessageResponse(
                    message=ParticipantMessageSummary(
                        message_id=existing.id,
                        sender_type=existing.sender_type,
                        body=existing.body,
                        created_at=existing.created_at,
                    )
                )
        raise HTTPException(409, "Message state conflict.")
    except Exception:
        db.rollback()
        raise

    _cache_control_no_store(response)
    return CreateMessageResponse(
        message=ParticipantMessageSummary(
            message_id=row.id,
            sender_type=row.sender_type,
            body=row.body,
            created_at=row.created_at,
        )
    )


@app.post("/api/v1/participant/privacy/withdrawal-requests", response_model=PrivacyRequestAcknowledgement, status_code=202)
def participant_api_withdrawal_request(
    payload: WithdrawalRequest,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=128),
    _content_type_ok: None = Depends(_require_json_content_type),
    db: Session = Depends(get_db),
):
    invitation, participant_row, study_row = _resolve_participant_api_study_scope(request, db, write_scope=True)
    target_study_id = payload.study_id or invitation.study_id
    if payload.scope == "study" and target_study_id != invitation.study_id:
        raise HTTPException(403, "Requested study is outside participant scope.")

    try:
        _record_participant_idempotency(db, invitation.id, "privacy_withdrawal", idempotency_key)
        apply_participant_withdrawal(db, invitation, participant_row, payload.scope)
        privacy_request = ParticipantPrivacyRequest(
            organisation_id=invitation.organisation_id,
            participant_id=participant_row.id,
            study_id=study_row.id if payload.scope == "study" else None,
            request_type="withdrawal",
            scope=payload.scope,
            status="completed",
            categories_json=json.dumps(["study_access", "participant_sessions", "invitations", "future_collection"]),
            completed_at=now(),
        )
        db.add(privacy_request)
        db.flush()
        request_id = int(privacy_request.id)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Withdrawal request conflict.")
    except Exception:
        db.rollback()
        raise

    _cache_control_no_store(response)
    return PrivacyRequestAcknowledgement(
        request_id=request_id,
        request_type="withdrawal",
        status="completed",
        submitted_at=now(),
        message="You have withdrawn from this study. You can no longer submit material for it.",
    )


@app.post("/api/v1/participant/privacy/deletion-requests", response_model=PrivacyRequestAcknowledgement, status_code=202)
def participant_api_deletion_request(
    payload: DeletionRequest,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=128),
    _content_type_ok: None = Depends(_require_json_content_type),
    db: Session = Depends(get_db),
):
    invitation, participant_row, study_row = _resolve_participant_api_study_scope(request, db, write_scope=True)
    if payload.study_id is not None and payload.study_id != invitation.study_id:
        raise HTTPException(403, "Requested study is outside participant scope.")

    try:
        _record_participant_idempotency(db, invitation.id, "privacy_deletion", idempotency_key)
        # Access revocation takes effect before deletion work, even when a
        # storage provider must be retried later.
        apply_participant_withdrawal(
            db,
            invitation,
            participant_row,
            "all" if payload.scope == "account" else "study",
        )
        privacy_request = ParticipantPrivacyRequest(
            organisation_id=invitation.organisation_id,
            participant_id=participant_row.id,
            study_id=study_row.id if payload.scope == "study" else None,
            request_type="deletion",
            scope=payload.scope,
            status="received",
        )
        db.add(privacy_request)
        db.flush()
        request_id = int(privacy_request.id)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Deletion request conflict.")
    except Exception:
        db.rollback()
        raise

    governance_study_ids = [study_row.id]
    if payload.scope == "account":
        governance_study_ids = list(
            db.scalars(
                select(StudyEnrolment.study_id).where(
                    StudyEnrolment.organisation_id == invitation.organisation_id,
                    StudyEnrolment.participant_id == participant_row.id,
                )
            )
        )
    governance_rows = list(
        db.scalars(
            select(StudyGovernance).where(
                StudyGovernance.organisation_id == invitation.organisation_id,
                StudyGovernance.study_id.in_(governance_study_ids),
            )
        )
    )
    controller_review_required = any(
        item.deletion_retention_exception.strip().lower() not in {"", "none", "none."}
        for item in governance_rows
    )
    if controller_review_required:
        privacy_request.status = "requires_controller_review"
        privacy_request.retention_exceptions_json = json.dumps(["controller_documented_retention_exception"])
        db.commit()
        deletion_completed = False
    else:
        deletion_completed = process_deletion_request(db, storage, privacy_request)
    current = db.get(ParticipantPrivacyRequest, request_id)
    _cache_control_no_store(response)
    return PrivacyRequestAcknowledgement(
        request_id=request_id,
        request_type="deletion",
        status="completed" if deletion_completed else (current.status if current else "failed_retrying"),
        submitted_at=now(),
        message=(
            "Your identifiable active study data has been deleted. Protected backups expire under the applicable retention schedule."
            if deletion_completed
            else (
                "Your access has ended. The study controller must review a documented retention exception before deletion can be completed."
                if current and current.status == "requires_controller_review"
                else "Your access has ended. We are safely retrying deletion of active data; it is not yet marked complete."
            )
        ),
    )


@app.post("/privacy/deletion-requests/{request_id}/retry")
def retry_participant_deletion_request(
    request_id: int,
    u=Depends(roles("owner", "admin")),
    csrf_ok: None = Depends(csrf_protect),
    db: Session = Depends(get_db),
):
    """Controlled retry for a failed live-system deletion; no raw data is logged."""
    privacy_request = db.scalar(
        select(ParticipantPrivacyRequest).where(
            ParticipantPrivacyRequest.id == request_id,
            ParticipantPrivacyRequest.organisation_id == u.organisation_id,
            ParticipantPrivacyRequest.request_type == "deletion",
        )
    )
    if not privacy_request:
        raise HTTPException(404, "Deletion request not found.")
    if privacy_request.status == "completed":
        return {"request_id": request_id, "status": "completed"}
    completed = process_deletion_request(db, storage, privacy_request)
    refreshed = db.get(ParticipantPrivacyRequest, request_id)
    return {
        "request_id": request_id,
        "status": "completed" if completed else (refreshed.status if refreshed else "failed_retrying"),
    }

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


def _conversation_scope(db: Session, user: User, study_id: int, participant_id: int):
    study_row = study(db, study_id, user.organisation_id)
    permission = require_study_permission(db, user, study_row)
    participant_row = participant(db, participant_id, user.organisation_id)
    enrolment = db.scalar(
        select(StudyEnrolment).where(
            StudyEnrolment.organisation_id == user.organisation_id,
            StudyEnrolment.study_id == study_row.id,
            StudyEnrolment.participant_id == participant_row.id,
        )
    )
    if not enrolment:
        raise HTTPException(404, "Conversation not found.")
    return study_row, participant_row, enrolment, permission


@app.get("/messages", response_class=HTMLResponse)
def researcher_conversations(
    request: Request,
    q: str = "",
    study_id: int | None = None,
    status_filter: str = "",
    page: int = 1,
    u=Depends(current_user),
    db: Session = Depends(get_db),
):
    if status_filter not in {"", "unread"}:
        raise HTTPException(400, "Invalid message status filter.")
    accessible_studies = (
        select(Study.id).where(Study.organisation_id == u.organisation_id)
        if u.role in {"owner", "admin", "observer"}
        else study_scope_for_user(u)
    )
    unread_count = func.sum(
        case(
            (
                and_(
                    ParticipantMessage.sender_type == "participant",
                    ParticipantMessage.internal_note == False,
                    ParticipantMessage.read_at.is_(None),
                ),
                1,
            ),
            else_=0,
        )
    )
    latest_at = func.max(ParticipantMessage.created_at)
    stmt = (
        select(
            StudyEnrolment.study_id.label("study_id"),
            StudyEnrolment.participant_id.label("participant_id"),
            Study.title.label("study_title"),
            Participant.name.label("participant_name"),
            Participant.reference.label("participant_reference"),
            latest_at.label("latest_at"),
            unread_count.label("unread_count"),
        )
        .join(Study, Study.id == StudyEnrolment.study_id)
        .join(Participant, Participant.id == StudyEnrolment.participant_id)
        .outerjoin(
            ParticipantMessage,
            and_(
                ParticipantMessage.organisation_id == StudyEnrolment.organisation_id,
                ParticipantMessage.study_id == StudyEnrolment.study_id,
                ParticipantMessage.participant_id == StudyEnrolment.participant_id,
                ParticipantMessage.internal_note == False,
            ),
        )
        .where(
            StudyEnrolment.organisation_id == u.organisation_id,
            StudyEnrolment.status != "withdrawn",
            StudyEnrolment.study_id.in_(accessible_studies),
        )
        .group_by(
            StudyEnrolment.study_id,
            StudyEnrolment.participant_id,
            Study.title,
            Participant.name,
            Participant.reference,
        )
    )
    if study_id is not None:
        if not db.scalar(accessible_studies.where(Study.id == study_id)):
            raise HTTPException(403, "You do not have access to this study.")
        stmt = stmt.where(StudyEnrolment.study_id == study_id)
    if q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Participant.name.ilike(term),
                Participant.reference.ilike(term),
                Study.title.ilike(term),
            )
        )
    if status_filter == "unread":
        stmt = stmt.having(unread_count > 0)
    stmt = stmt.order_by(latest_at.desc(), Participant.name.asc())
    page = max(1, page)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.offset((page - 1) * 25).limit(25)).all()
    pages = max(1, (total + 24) // 25)
    available_studies = db.scalars(
        select(Study)
        .where(Study.organisation_id == u.organisation_id, Study.id.in_(accessible_studies))
        .order_by(Study.title)
    ).all()
    return render(
        request,
        "messages.html",
        user=u,
        conversations=rows,
        q=q,
        study_id=study_id,
        status_filter=status_filter,
        studies=available_studies,
        page=page,
        pages=pages,
        total=total,
    )


@app.get("/messages/{study_id}/{participant_id}", response_class=HTMLResponse)
def researcher_conversation(
    study_id: int,
    participant_id: int,
    request: Request,
    u=Depends(current_user),
    db: Session = Depends(get_db),
):
    study_row, participant_row, enrolment, permission = _conversation_scope(db, u, study_id, participant_id)
    rows = db.scalars(
        select(ParticipantMessage)
        .where(
            ParticipantMessage.organisation_id == u.organisation_id,
            ParticipantMessage.study_id == study_row.id,
            ParticipantMessage.participant_id == participant_row.id,
        )
        .order_by(ParticipantMessage.created_at, ParticipantMessage.id)
    ).all()
    visible_messages = [row for row in rows if not row.internal_note]
    internal_notes = [row for row in rows if row.internal_note]
    read_result = db.execute(
        update(ParticipantMessage)
        .where(
            ParticipantMessage.organisation_id == u.organisation_id,
            ParticipantMessage.study_id == study_row.id,
            ParticipantMessage.participant_id == participant_row.id,
            ParticipantMessage.sender_type == "participant",
            ParticipantMessage.internal_note == False,
            ParticipantMessage.read_at.is_(None),
        )
        .values(read_at=now())
    )
    if read_result.rowcount:
        audit(db,u.organisation_id,u.id,"message.participant_messages_read","participant",participant_row.id,str(study_row.id)); db.commit()
        read_time = now()
        for message in visible_messages:
            if message.sender_type == "participant" and message.read_at is None:
                message.read_at = read_time
    return render(
        request,
        "message_conversation.html",
        user=u,
        study=study_row,
        participant=participant_row,
        enrolment=enrolment,
        messages=visible_messages,
        internal_notes=internal_notes,
        can_send=permission in {"edit", "manage"} and enrolment.status != "withdrawn",
    )


def _create_researcher_conversation_entry(
    *,
    db: Session,
    user: User,
    study_id: int,
    participant_id: int,
    body: str,
    internal_note: bool,
):
    study_row, participant_row, enrolment, permission = _conversation_scope(db, user, study_id, participant_id)
    if permission not in {"edit", "manage"}:
        raise HTTPException(403, "You do not have permission to update this conversation.")
    if not internal_note and enrolment.status == "withdrawn":
        raise HTTPException(409, "Messages cannot be sent to a withdrawn participant.")
    cleaned_body = body.strip()
    if not cleaned_body:
        raise HTTPException(400, "Message cannot be empty.")
    row = create_researcher_message(
        organisation_id=user.organisation_id,
        study_id=study_row.id,
        participant_id=participant_row.id,
        sender_user_id=user.id,
        body=cleaned_body,
        internal_note=internal_note,
    )
    db.add(row)
    db.flush()
    audit(
        db,
        user.organisation_id,
        user.id,
        "message.internal_note_created" if internal_note else "message.participant_visible_created",
        "participant_message",
        row.id,
        str(study_row.id),
    )
    db.commit()


@app.post("/messages/{study_id}/{participant_id}")
def researcher_conversation_send(
    study_id: int,
    participant_id: int,
    body: str = Form(..., max_length=10000),
    u=Depends(roles("owner", "admin", "researcher")),
    csrf_ok: None = Depends(csrf_protect),
    db: Session = Depends(get_db),
):
    _create_researcher_conversation_entry(db=db,user=u,study_id=study_id,participant_id=participant_id,body=body,internal_note=False)
    return RedirectResponse(f"/messages/{study_id}/{participant_id}#conversation", 303)


@app.post("/messages/{study_id}/{participant_id}/notes")
def researcher_conversation_note(
    study_id: int,
    participant_id: int,
    body: str = Form(..., max_length=10000),
    u=Depends(roles("owner", "admin", "researcher")),
    csrf_ok: None = Depends(csrf_protect),
    db: Session = Depends(get_db),
):
    _create_researcher_conversation_entry(db=db,user=u,study_id=study_id,participant_id=participant_id,body=body,internal_note=True)
    return RedirectResponse(f"/messages/{study_id}/{participant_id}#internal-notes", 303)
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
