"""Create the first privileged account for an existing or new organisation."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from typing import Sequence

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.db import SessionLocal
from app.models import AuditEvent, Organisation, OrganisationMembership, User


PRIVILEGED_ROLES = ("owner", "admin")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class BootstrapError(RuntimeError):
    """Raised when the requested bootstrap would be unsafe or ambiguous."""


@dataclass(frozen=True)
class BootstrapResult:
    organisation_name: str
    organisation_slug: str
    email: str
    role: str
    dry_run: bool
    organisation_created: bool
    account_created: bool
    platform_admin: bool = False
    user_id: int | None = None


def normalise_email(value: str) -> str:
    try:
        return validate_email(value.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise BootstrapError("A valid administrator email address is required.") from exc


def validate_inputs(
    *,
    organisation_name: str,
    organisation_slug: str,
    administrator_name: str,
    role: str,
) -> None:
    if not organisation_name.strip():
        raise BootstrapError("Organisation name is required.")
    if not SLUG_RE.fullmatch(organisation_slug):
        raise BootstrapError(
            "Organisation slug must contain lowercase letters, numbers, and internal hyphens."
        )
    if not administrator_name.strip():
        raise BootstrapError("Administrator name is required.")
    if role not in PRIVILEGED_ROLES:
        raise BootstrapError("Bootstrap role must be owner or admin.")


def _lock_bootstrap_scope(db: Session, organisation_slug: str) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:scope))"),
            {"scope": f"pcip-admin-bootstrap:{organisation_slug}"},
        )


def bootstrap_admin(
    db: Session,
    *,
    organisation_name: str,
    organisation_slug: str,
    administrator_name: str,
    email: str,
    role: str = "owner",
    create_organisation: bool = False,
    dry_run: bool = False,
    platform_admin: bool = False,
) -> BootstrapResult:
    organisation_name = organisation_name.strip()
    administrator_name = administrator_name.strip()
    organisation_slug = organisation_slug.strip()
    email = normalise_email(email)
    validate_inputs(
        organisation_name=organisation_name,
        organisation_slug=organisation_slug,
        administrator_name=administrator_name,
        role=role,
    )

    required_tables = {
        "organisations",
        "users",
        "organisation_memberships",
        "audit_events",
    }
    available_tables = set(inspect(db.get_bind()).get_table_names())
    missing_tables = required_tables - available_tables
    if missing_tables:
        raise BootstrapError(
            "Database migrations are incomplete; required bootstrap tables are missing."
        )

    _lock_bootstrap_scope(db, organisation_slug)

    organisation = db.scalar(
        select(Organisation).where(Organisation.slug == organisation_slug)
    )
    organisation_created = organisation is None
    if organisation is None and not create_organisation:
        raise BootstrapError(
            "The organisation does not exist; rerun with --create-organisation after approval."
        )
    if organisation is not None and organisation.name != organisation_name:
        raise BootstrapError(
            "The organisation slug already exists with a different name."
        )

    duplicate = db.scalar(
        select(User.id).where(func.lower(User.email) == email)
    )
    if duplicate is not None:
        raise BootstrapError(
            "An account already exists for this email address; bootstrap will not alter it."
        )

    if organisation is not None:
        privileged_count = db.scalar(
            select(func.count(OrganisationMembership.id))
            .join(User, User.id == OrganisationMembership.user_id)
            .where(
                OrganisationMembership.organisation_id == organisation.id,
                OrganisationMembership.is_active.is_(True),
                OrganisationMembership.role.in_(PRIVILEGED_ROLES),
                User.is_active.is_(True),
            )
        )
        if privileged_count:
            raise BootstrapError(
                "An active owner or administrator already exists; use the supported invitation flow."
            )

    if dry_run:
        return BootstrapResult(
            organisation_name=organisation_name,
            organisation_slug=organisation_slug,
            email=email,
            role=role,
            dry_run=True,
            organisation_created=organisation_created,
            account_created=True,
            platform_admin=platform_admin,
        )

    if organisation is None:
        organisation = Organisation(
            name=organisation_name,
            slug=organisation_slug,
        )
        db.add(organisation)
        db.flush()

    user = User(
        organisation_id=organisation.id,
        name=administrator_name,
        email=email,
        password_hash=None,
        role=role,
        is_platform_admin=platform_admin,
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        OrganisationMembership(
            user_id=user.id,
            organisation_id=organisation.id,
            role=role,
            is_active=True,
        )
    )
    db.add(
        AuditEvent(
            organisation_id=organisation.id,
            actor_user_id=None,
            action="auth.admin_bootstrapped",
            entity_type="user",
            entity_id=str(user.id),
            detail=(
                f"role={role}; platform_admin={platform_admin}; "
                "source=scripts.bootstrap_admin"
            ),
        )
    )
    db.flush()

    return BootstrapResult(
        organisation_name=organisation.name,
        organisation_slug=organisation.slug,
        email=email,
        role=role,
        dry_run=False,
        organisation_created=organisation_created,
        account_created=True,
        platform_admin=platform_admin,
        user_id=user.id,
    )


def execute_bootstrap(
    session_factory: sessionmaker = SessionLocal,
    **kwargs,
) -> BootstrapResult:
    with session_factory.begin() as db:
        return bootstrap_admin(db, **kwargs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create the first owner or administrator without creating or logging a password."
        )
    )
    parser.add_argument("--organisation-name", required=True)
    parser.add_argument("--organisation-slug", required=True)
    parser.add_argument("--name", dest="administrator_name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", choices=PRIVILEGED_ROLES, default="owner")
    parser.add_argument("--create-organisation", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--platform-admin",
        action="store_true",
        help="Grant Politis-only global administration; use only with explicit approval.",
    )
    parser.add_argument(
        "--confirm-production-bootstrap",
        action="store_true",
        help="Required for a write; confirms the production bootstrap was approved.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.dry_run and not args.confirm_production_bootstrap:
        parser.error(
            "--confirm-production-bootstrap is required unless --dry-run is used."
        )
    try:
        result = execute_bootstrap(
            organisation_name=args.organisation_name,
            organisation_slug=args.organisation_slug,
            administrator_name=args.administrator_name,
            email=args.email,
            role=args.role,
            create_organisation=args.create_organisation,
            dry_run=args.dry_run,
            platform_admin=args.platform_admin,
        )
    except BootstrapError as exc:
        parser.exit(2, f"Bootstrap refused: {exc}\n")
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
