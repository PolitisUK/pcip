import logging
import os
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
    app_name: str = "Citizen Centric"
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
    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = 60
    rate_limit_login_ip: int = 500
    rate_limit_login_account: int = 200
    rate_limit_forgot_password_ip: int = 200
    rate_limit_forgot_password_account: int = 60
    rate_limit_password_reset_ip: int = 200
    rate_limit_password_reset_token: int = 60
    rate_limit_invitation_accept_ip: int = 200
    rate_limit_invitation_accept_token: int = 60
    rate_limit_portal_write_ip: int = 600
    rate_limit_portal_write_token: int = 200
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
    debug: bool = False
    seed_demo_data: bool = True
    local_login_enabled: bool = True
    entra_enabled: bool = False
    entra_tenant_id: str | None = None
    entra_client_id: str | None = None
    entra_client_secret: str | None = None
    entra_redirect_uri: str | None = None
    entra_post_logout_redirect_uri: str | None = None
    entra_default_organisation_slug: str | None = None
    entra_allowed_domains: str = ""
    entra_auto_provision: bool = False
    entra_default_role: str = "researcher"
    entra_role_map: str = ""
    entra_sync_roles: bool = False
    entra_allow_role_elevation: bool = False
    applicationinsights_connection_string: str | None = None
    log_level: str = "INFO"
    key_vault_url: str | None = None
    key_vault_secret_database_url: str = "database-url"
    key_vault_secret_secret_key: str = "session-secret"
    key_vault_secret_defender_webhook: str = "defender-webhook-secret"
    key_vault_secret_entra_client_secret: str = "entra-client-secret"
    startup_validate_migrations: bool = True
    privacy_retention_days: int = 365
    privacy_retention_statuses: str = "withdrawn,completed"
    privacy_retention_action: str = "anonymise"
    privacy_retention_policy_days: str = "standard:365,sensitive:730"
    password_reset_token_minutes: int = 60
    researcher_invitation_expiry_hours: int = 48
    participant_invitation_expiry_hours: int = 720
    public_auth_session_reset_minutes: int = 15
    public_auth_session_researcher_invite_minutes: int = 60
    public_auth_session_participant_portal_minutes: int = 720
    csp_enabled: bool = True
    require_redis_rate_limit_in_production: bool = True
    redis_url: str | None = None
    redis_prefix: str = "pcip:rl"
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


def _normalised_environment(environment: str) -> str:
    token = environment.strip().lower()
    aliases = {
        "dev": "development",
        "testing": "test",
    }
    return aliases.get(token, token)


def apply_key_vault_overrides(runtime: Settings) -> None:
    vault_url = (runtime.key_vault_url or "").strip()
    if not vault_url:
        return

    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
    except ImportError as exc:
        raise RuntimeError("Azure Key Vault support requires azure-identity and azure-keyvault-secrets.") from exc

    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    client = SecretClient(vault_url=vault_url, credential=credential)

    logger = logging.getLogger("pcip.config")

    def _load_secret(runtime_attr: str, env_name: str, secret_name: str | None):
        if not secret_name or os.getenv(env_name):
            return
        try:
            secret_value = client.get_secret(secret_name).value
        except Exception as exc:
            logger.warning("key_vault_secret_unavailable env=%s name=%s error=%s", env_name, secret_name, exc.__class__.__name__)
            return
        if secret_value:
            setattr(runtime, runtime_attr, secret_value)

    _load_secret("database_url", "DATABASE_URL", runtime.key_vault_secret_database_url)
    _load_secret("secret_key", "SECRET_KEY", runtime.key_vault_secret_secret_key)
    _load_secret("azure_defender_webhook_secret", "AZURE_DEFENDER_WEBHOOK_SECRET", runtime.key_vault_secret_defender_webhook)
    _load_secret("entra_client_secret", "ENTRA_CLIENT_SECRET", runtime.key_vault_secret_entra_client_secret)


def validate_runtime_settings(runtime: Settings) -> None:
    environment = _normalised_environment(getattr(runtime, "environment", ""))
    if environment not in {"development", "test", "staging", "production"}:
        raise RuntimeError("ENVIRONMENT must be one of development, test, staging, production.")

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

    if getattr(runtime, "debug", False):
        errors.append("DEBUG must be disabled outside development.")

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

    database_url = getattr(runtime, "database_url", "")
    if not database_url.strip():
        errors.append("DATABASE_URL must be configured outside development.")
    if database_url.strip().lower().startswith("sqlite"):
        errors.append("DATABASE_URL cannot use sqlite outside development; configure Azure SQL/PostgreSQL.")

    backend = getattr(runtime, "storage_backend", "local").strip().lower()

    if backend == "azure_blob":
        storage_account_url = (
            getattr(runtime, "azure_storage_account_url", None) or ""
        ).strip()
        storage_connection = (
            getattr(runtime, "azure_storage_connection_string", None) or ""
        ).strip()
        storage_container = (
            getattr(runtime, "azure_storage_container", "") or ""
        ).strip()

        if not storage_container:
            errors.append(
                "AZURE_STORAGE_CONTAINER is required for STORAGE_BACKEND=azure_blob."
            )

        if environment == "production":
            if not storage_account_url:
                errors.append(
                    "AZURE_STORAGE_ACCOUNT_URL is required in production."
                )

            if storage_connection:
                errors.append(
                    "AZURE_STORAGE_CONNECTION_STRING must not be configured in production."
                )

        elif not storage_account_url and not storage_connection:
            errors.append(
                "AZURE_STORAGE_ACCOUNT_URL or AZURE_STORAGE_CONNECTION_STRING is required for STORAGE_BACKEND=azure_blob."
            )

    if getattr(runtime, "entra_enabled", False):
        missing_entra = [
            name
            for name, value in [
                ("ENTRA_TENANT_ID", getattr(runtime, "entra_tenant_id", None)),
                ("ENTRA_CLIENT_ID", getattr(runtime, "entra_client_id", None)),
                ("ENTRA_CLIENT_SECRET", getattr(runtime, "entra_client_secret", None)),
            ]
            if not (value or "").strip()
        ]
        if missing_entra:
            errors.append("Missing Microsoft Entra configuration: " + ", ".join(missing_entra) + ".")

        for name, value in [
            ("ENTRA_REDIRECT_URI", getattr(runtime, "entra_redirect_uri", None)),
            ("ENTRA_POST_LOGOUT_REDIRECT_URI", getattr(runtime, "entra_post_logout_redirect_uri", None)),
        ]:
            if not (value or "").strip():
                continue
            parsed = urlsplit(value.strip())
            if parsed.scheme.lower() != "https" or not parsed.hostname:
                errors.append(f"{name} must be a valid HTTPS URL when configured.")

        role_map = (getattr(runtime, "entra_role_map", "") or "").strip()
        if role_map:
            allowed_roles = {"owner", "admin", "researcher", "observer"}
            entries = [x.strip() for x in role_map.split(",") if x.strip()]
            for entry in entries:
                if ":" not in entry:
                    errors.append("ENTRA_ROLE_MAP entries must use 'external_claim:app_role' format.")
                    break
                _, mapped_role = entry.split(":", 1)
                if mapped_role.strip().lower() not in allowed_roles:
                    errors.append("ENTRA_ROLE_MAP can only map to owner/admin/researcher/observer.")
                    break

    if environment == "production":
        if not getattr(runtime, "csp_enabled", True):
            errors.append("CSP_ENABLED must remain true in production.")
        if backend != "azure_blob":
            errors.append("STORAGE_BACKEND must be azure_blob in production.")
        if getattr(runtime, "require_redis_rate_limit_in_production", True) and not (getattr(runtime, "redis_url", "") or "").strip():
            errors.append("REDIS_URL must be configured in production for distributed rate limiting.")

        if isinstance(runtime, Settings):
            required_env_vars = ["SECRET_KEY", "DATABASE_URL", "AZURE_DEFENDER_WEBHOOK_SECRET"]
            if getattr(runtime, "entra_enabled", False):
                required_env_vars.append("ENTRA_CLIENT_SECRET")
            missing_env = [name for name in required_env_vars if not (os.getenv(name) or "").strip()]
            if missing_env:
                errors.append("Production secrets must be supplied through environment variables: " + ", ".join(missing_env) + ".")

    key_vault_url = (getattr(runtime, "key_vault_url", None) or "").strip()
    if key_vault_url:
        parsed = urlsplit(key_vault_url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme.lower() != "https" or not host:
            errors.append("KEY_VAULT_URL must be a valid HTTPS URL when configured.")
        elif "vault.azure.net" not in host:
            errors.append("KEY_VAULT_URL should target an Azure Key Vault host (*.vault.azure.net).")

    if errors:
        raise RuntimeError("Unsafe hosted configuration: " + " ".join(errors))


settings = Settings()
apply_key_vault_overrides(settings)
