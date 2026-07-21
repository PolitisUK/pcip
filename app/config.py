from pydantic_settings import BaseSettings, SettingsConfigDict

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

settings = Settings()
