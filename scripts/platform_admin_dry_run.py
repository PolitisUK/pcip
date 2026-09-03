"""Read-only production assessment for enabling one platform administrator.

This module is deliberately separate from the mutating platform-admin command.
It can describe only the fixed ``false -> true`` transition and always runs in
an explicitly read-only transaction on PostgreSQL.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.db import SessionLocal
from app.models import OrganisationMembership, User
from scripts.bootstrap_admin import BootstrapError, normalise_email


class PlatformAdminDryRunError(RuntimeError):
    """Raised when a platform-admin dry run cannot fail closed safely."""


@dataclass(frozen=True)
class MembershipSnapshot:
    organisation_id: int
    role: str
    is_active: bool


@dataclass(frozen=True)
class MembershipState:
    """Complete membership state used only for equality checks, never output."""

    id: int
    user_id: int
    organisation_id: int
    role: str
    is_active: bool
    created_at: object


@dataclass(frozen=True)
class AccountSnapshot:
    """Sensitive account state used only for equality checks, never output."""

    email: str
    name: str
    organisation_id: int
    role: str
    is_active: bool
    password_hash: str | None
    external_provider: str | None
    external_subject: str | None
    last_login_at: object
    session_version: int
    failed_login_count: int
    locked_until: object
    created_at: object


@dataclass(frozen=True)
class PlatformAdminDryRunResult:
    user_id: int
    active: bool
    current_is_platform_admin: bool
    intended_is_platform_admin: bool
    would_change: bool
    memberships: tuple[MembershipSnapshot, ...]
    memberships_unchanged: bool
    account_fields_unchanged: bool


def _matching_users(db: Session, normalized_email: str) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(func.lower(User.email) == normalized_email)
            .order_by(User.id)
        )
    )


def _membership_state(db: Session, user_id: int) -> tuple[MembershipState, ...]:
    return tuple(
        MembershipState(
            id=row.id,
            user_id=row.user_id,
            organisation_id=row.organisation_id,
            role=row.role,
            is_active=bool(row.is_active),
            created_at=row.created_at,
        )
        for row in db.scalars(
            select(OrganisationMembership)
            .where(OrganisationMembership.user_id == user_id)
            .order_by(OrganisationMembership.id)
        )
    )


def _account_snapshot(user: User) -> AccountSnapshot:
    return AccountSnapshot(
        email=user.email,
        name=user.name,
        organisation_id=user.organisation_id,
        role=user.role,
        is_active=bool(user.is_active),
        password_hash=user.password_hash,
        external_provider=user.external_provider,
        external_subject=user.external_subject,
        last_login_at=user.last_login_at,
        session_version=user.session_version,
        failed_login_count=user.failed_login_count,
        locked_until=user.locked_until,
        created_at=user.created_at,
    )


def platform_admin_dry_run(
    db: Session,
    *,
    email: str,
    expected_user_id: int,
) -> PlatformAdminDryRunResult:
    """Assess the fixed enable transition without invoking mutating code."""
    if type(expected_user_id) is not int or expected_user_id <= 0:
        raise PlatformAdminDryRunError("An expected positive user ID is required.")
    try:
        normalized_email = normalise_email(email)
    except BootstrapError as exc:
        raise PlatformAdminDryRunError(str(exc)) from exc

    matches = _matching_users(db, normalized_email)
    if len(matches) != 1:
        raise PlatformAdminDryRunError(
            "Expected exactly one existing user for the supplied normalized email."
        )
    user = matches[0]
    if user.id != expected_user_id:
        raise PlatformAdminDryRunError("The expected user ID does not match the email.")

    account_before = _account_snapshot(user)
    membership_state_before = _membership_state(db, user.id)
    memberships = tuple(
        MembershipSnapshot(
            organisation_id=item.organisation_id,
            role=item.role,
            is_active=item.is_active,
        )
        for item in membership_state_before
    )
    current = bool(user.is_platform_admin)

    # An inactive account is reported explicitly but never proposed for change.
    eligible = bool(user.is_active)
    intended = True if eligible else current
    would_change = eligible and not current

    account_after = _account_snapshot(user)
    membership_state_after = _membership_state(db, user.id)
    account_unchanged = account_after == account_before
    memberships_unchanged = membership_state_after == membership_state_before
    if (
        not account_unchanged
        or not memberships_unchanged
        or db.new
        or db.dirty
        or db.deleted
    ):
        raise PlatformAdminDryRunError("Read-only dry run detected pending changes.")

    return PlatformAdminDryRunResult(
        user_id=user.id,
        active=eligible,
        current_is_platform_admin=current,
        intended_is_platform_admin=intended,
        would_change=would_change,
        memberships=memberships,
        memberships_unchanged=True,
        account_fields_unchanged=True,
    )


def execute_platform_admin_dry_run(
    session_factory: sessionmaker = SessionLocal,
    *,
    email: str,
    expected_user_id: int,
) -> PlatformAdminDryRunResult:
    """Execute in a server-enforced read-only transaction and always roll back."""
    db = session_factory()
    try:
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text("SET TRANSACTION READ ONLY"))
        return platform_admin_dry_run(
            db,
            email=email,
            expected_user_id=expected_user_id,
        )
    finally:
        db.rollback()
        db.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only assessment of enabling platform administration."
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--expected-user-id", type=int, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = execute_platform_admin_dry_run(
            email=args.email,
            expected_user_id=args.expected_user_id,
        )
    except PlatformAdminDryRunError as exc:
        raise SystemExit(f"Platform-admin dry run refused: {exc}") from exc
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
