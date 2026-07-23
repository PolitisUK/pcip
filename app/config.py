from pydantic_settings import BaseSettings, SettingsConfigDict
from urllib.parse import urlsplit


KNOWN_WEAK_SECRET_KEYS = {
    "",
    "dev-only-change-me",
    "change-this-in-production",
    "replace-before-production",
    "secret",
    "changeme",
}

LOCAL_HOSTS = {
    "localhost",
    "127.0.0.1",
    "testserver",
}

class Settings(BaseSettings):
    app_name: str = "Politis Civic Intelligence"
    secret_key: str = "dev-only-change-me"
    database_url: str = "sqlite:///./data/app.db"
    base_url: str = "http://127.0.0.1:8000"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = "no-reply@example.org"
    smtp_use_tls: bool = True
    cookie_secure: bool = False
    session_cookie_secure: bool = False
    session_max_age_seconds: int = 60 * 60 * 12
    login_max_failed_attempts: int = 5
    login_lockout_seconds: int = 15 * 60
    trusted_hosts: str = "127.0.0.1,localhost,testserver"
    allowed_origins: str = "http://127.0.0.1:8000,http://localhost:8000,http://testserver"
    max_upload_mb: int = 25
    allowed_upload_extensions: str = ".jpg,.jpeg,.png,.webp,.mp3,.wav,.m4a,.mp4,.mov,.pdf,.doc,.docx,.txt,.csv"
    local_storage_path: str = "./data/uploads"
    storage_backend: str = "local"
    azure_storage_account_url: str | None = None
    azure_storage_connection_string: str | None = None
    azure_storage_container: str = "evidence"
    azure_defender_webhook_secret: str | None = None
    defender_require_clean_download: bool = True
    development_allow_unscanned_downloads: bool = False
    azure_sas_minutes: int = 5
    clamav_host: str | None = None
    clamav_port: int = 3310
    environment: str = "development"
    seed_demo_data: bool = True
    local_login_enabled: bool = True
    entra_enabled: bool = False
    entra_tenant_id: str | None = None
    entra_client_id: str | None = None
    entra_client_secret: str | None = None
    entra_default_organisation_slug: str | None = None
    entra_allowed_domains: str = ""
    entra_auto_provision: bool = False
    entra_default_role: str = "researcher"
    applicationinsights_connection_string: str | None = None
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')


def _csv_values(value: str) -> list[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


def _is_secret_strong(secret: str) -> bool:
    if len(secret) < 32:
        return False
    classes = [
        any(c.islower() for c in secret),
        any(c.isupper() for c in secret),
        any(c.isdigit() for c in secret),
        any(not c.isalnum() for c in secret),
    ]
    return sum(classes) >= 3


def _is_non_development(environment: str) -> bool:
    return environment.strip().lower() not in {"development", "dev", "test", "testing"}


def validate_runtime_settings(runtime: Settings) -> None:
    if not _is_non_development(runtime.environment):
        return

    errors: list[str] = []

    secret = (runtime.secret_key or "").strip()
    if secret.lower() in KNOWN_WEAK_SECRET_KEYS or not _is_secret_strong(secret):
        errors.append("SECRET_KEY must be non-default and at least 32 chars with mixed character classes.")

    if not runtime.cookie_secure:
        errors.append("COOKIE_SECURE must be enabled outside development.")

    if not runtime.session_cookie_secure:
        errors.append("SESSION_COOKIE_SECURE must be enabled outside development.")

    base = urlsplit(runtime.base_url.strip())
    base_host = (base.hostname or "").lower()
    if base.scheme.lower() != "https" or not base_host:
        errors.append("BASE_URL must be a valid HTTPS URL outside development.")

    trusted_hosts = [x.lower() for x in _csv_values(runtime.trusted_hosts)]
    if not trusted_hosts:
        errors.append("TRUSTED_HOSTS must include at least one explicit host outside development.")
    else:
        if "*" in trusted_hosts:
            errors.append("TRUSTED_HOSTS cannot contain wildcard hosts outside development.")
        if any(x in LOCAL_HOSTS for x in trusted_hosts):
            errors.append("TRUSTED_HOSTS cannot include localhost/testserver entries outside development.")
        if base_host and base_host not in trusted_hosts:
            errors.append("TRUSTED_HOSTS must include the BASE_URL host outside development.")

    allowed_origins = _csv_values(runtime.allowed_origins)
    if not allowed_origins:
        errors.append("ALLOWED_ORIGINS must include at least one explicit HTTPS origin outside development.")
    else:
        normalised: set[str] = set()
        for origin in allowed_origins:
            parsed = urlsplit(origin)
            host = (parsed.hostname or "").lower()
            if parsed.scheme.lower() != "https" or not host:
                errors.append("ALLOWED_ORIGINS must contain valid HTTPS origins outside development.")
                continue
            if host in LOCAL_HOSTS:
                errors.append("ALLOWED_ORIGINS cannot include localhost/testserver entries outside development.")
            normalised.add(f"{parsed.scheme.lower()}://{host}")
        if base_host and f"https://{base_host}" not in normalised:
            errors.append("ALLOWED_ORIGINS must include the HTTPS origin for BASE_URL host outside development.")

    if not (runtime.azure_defender_webhook_secret or "").strip():
        errors.append("AZURE_DEFENDER_WEBHOOK_SECRET must be configured outside development.")

    if errors:
        raise RuntimeError("Unsafe hosted configuration: " + " ".join(errors))


settings = Settings()
