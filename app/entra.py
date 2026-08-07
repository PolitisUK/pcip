from __future__ import annotations

from authlib.integrations.starlette_client import OAuth
from .config import settings


class EntraAuthError(Exception):
    pass


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


def complete_login(*args, **kwargs):
    raise EntraAuthError("Entra integration is not configured")


def logout_url(*args, **kwargs):
    if not configured():
        return None
    tenant = settings.entra_tenant_id or ""
    return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/logout"


def role_from_claims(claims: dict | None = None):
    claims = claims or {}
    roles = claims.get("roles") or []
    if isinstance(roles, str):
        roles = [roles]
    for role in roles:
        if isinstance(role, str) and role.lower() == "civic.admin":
            return "admin"
    return None


def safe_role_assignment(current_role: str | None, mapped_role: str | None):
    if not mapped_role:
        return current_role
    allowed_roles = {"owner", "admin", "researcher", "observer"}
    if mapped_role not in allowed_roles:
        return current_role
    if current_role in {"owner", "admin"} and mapped_role in {"researcher", "observer"}:
        return current_role
    if current_role is None:
        return mapped_role
    return current_role


def start_login(*args, **kwargs):
    raise EntraAuthError("Entra integration is not configured")


def validate_claims(claims: dict | None = None, expected_nonce: str | None = None):
    claims = claims or {}
    issuer = claims.get("iss", "")
    expected_tenant = settings.entra_tenant_id
    allowed_tenant = expected_tenant or ""
    if allowed_tenant:
        tid = str(claims.get("tid") or "")
        if tid and tid != allowed_tenant:
            raise EntraAuthError("The Microsoft tenant is not permitted for this workspace.")
        if issuer:
            if not issuer.endswith(f"/{allowed_tenant}/v2.0") and f"/tenant-{allowed_tenant}/" not in issuer and f"/{allowed_tenant}/" not in issuer:
                raise EntraAuthError("The Microsoft tenant is not permitted for this workspace.")
    if expected_nonce and claims.get("nonce") != expected_nonce:
        raise EntraAuthError("The Microsoft sign-in nonce is invalid.")
    return claims


oauth = create_oauth()
