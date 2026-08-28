"""Resolve one existing user for a separately controlled administrative action.

This operational command is deliberately read-only. It is not an HTTP route and
must be run only through an authorised production execution path.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Sequence

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.db import SessionLocal
from app.models import OrganisationMembership, User
from scripts.bootstrap_admin import BootstrapError, normalise_email


class UserIdentityLookupError(RuntimeError):
    """Raised when an exact read-only user identity lookup is unsafe."""


@dataclass(frozen=True)
class MembershipIdentity:
    organisation_id: int
    role: str
    is_active: bool


@dataclass(frozen=True)
class UserIdentity:
    user_id: int
    active: bool
    is_platform_admin: bool
    memberships: tuple[MembershipIdentity, ...]


def _matching_users(db: Session, normalized_email: str) -> list[User]:
    """Find every exact normalized-email match without taking a write lock."""
    return list(
        db.scalars(
            select(User)
            .where(func.lower(User.email) == normalized_email)
            .order_by(User.id)
        )
    )


def lookup_user_identity(db: Session, *, email: str) -> UserIdentity:
    """Return the non-sensitive identity state for exactly one existing user."""
    try:
        normalized_email = normalise_email(email)
    except BootstrapError as exc:
        raise UserIdentityLookupError(str(exc)) from exc

    matches = _matching_users(db, normalized_email)
    if len(matches) != 1:
        raise UserIdentityLookupError(
            "Expected exactly one existing user for the supplied normalized email."
        )
    user = matches[0]
    memberships = tuple(
        MembershipIdentity(
            organisation_id=row.organisation_id,
            role=row.role,
            is_active=row.is_active,
        )
        for row in db.scalars(
            select(OrganisationMembership)
            .where(OrganisationMembership.user_id == user.id)
            .order_by(OrganisationMembership.id)
        )
    )
    return UserIdentity(
        user_id=user.id,
        active=bool(user.is_active),
        is_platform_admin=bool(user.is_platform_admin),
        memberships=memberships,
    )


def execute_user_identity_lookup(
    session_factory: sessionmaker = SessionLocal,
    *,
    email: str,
) -> UserIdentity:
    """Perform one read-only lookup and guarantee rollback rather than commit."""
    db = session_factory()
    try:
        # PostgreSQL enforces read-only mode for the entire command transaction.
        # SQLite's test dialect has no equivalent setting; the session still never
        # flushes or commits and is always rolled back below.
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text("SET TRANSACTION READ ONLY"))
        result = lookup_user_identity(db, email=email)
        if db.new or db.dirty or db.deleted:
            raise UserIdentityLookupError(
                "Read-only lookup detected pending changes and was rolled back."
            )
        return result
    finally:
        db.rollback()
        db.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only exact lookup for one existing Citizen Centric user."
    )
    parser.add_argument("--email", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = execute_user_identity_lookup(email=args.email)
    except UserIdentityLookupError as exc:
        parser.exit(2, f"User identity lookup refused: {exc}\n")
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
