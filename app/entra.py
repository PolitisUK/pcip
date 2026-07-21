from authlib.integrations.starlette_client import OAuth
from .config import settings


def configured() -> bool:
    return bool(settings.entra_enabled and settings.entra_tenant_id and settings.entra_client_id and settings.entra_client_secret)


def create_oauth() -> OAuth:
    oauth = OAuth()
    if configured():
        oauth.register(
            name="entra",
            client_id=settings.entra_client_id,
            client_secret=settings.entra_client_secret,
            server_metadata_url=f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0/.well-known/openid-configuration",
            client_kwargs={"scope": "openid profile email"},
        )
    return oauth

oauth = create_oauth()
