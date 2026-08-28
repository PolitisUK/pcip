"""Safely change platform-administrator status for one existing user.

This is intentionally separate from ``bootstrap_admin``: it never creates a
user, membership, or organisation, and it never changes authentication data.
Run it only through an authorised production execution path.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import SessionLocal
from app.models import AuditEvent, OrganisationMembership, User
from app.services import audit
from scripts.bootstrap_admin import BootstrapError, normalise_email


class PlatformAdminChangeError(RuntimeError):
    """Raised when an existing-user platform-admin change would be unsafe."""


@dataclass(frozen=True)
class MembershipSnapshot:
    id: int
    organisation_id: int
    role: str
    is_active: bool


@dataclass(frozen=True)
class PlatformAdminChangeResult:
    user_id: int
    active: bool
    previous_is_platform_admin: bool
    new_is_platform_admin: bool
    changed: bool
    dry_run: bool
    membership_count: int
    memberships: tuple[MembershipSnapshot, ...]
    audit_event_id: int | None = None


@dataclass(frozen=True)
class AuthenticationSnapshot:
    """Fields this command must not change; never serialised or logged."""

    password_hash: str | None
    external_provider: str | None
    external_subject: str | None
    last_login_at: object
    session_version: int
    failed_login_count: int
    locked_until: object


def _memberships(db: Session, user_id: int) -> tuple[MembershipSnapshot, ...]:
    """Read and lock the target memberships so their snapshot stays stable."""
    rows = db.scalars(
        select(OrganisationMembership)
        .where(OrganisationMembership.user_id == user_id)
        .order_by(OrganisationMembership.id)
        .with_for_update()
    ).all()
    return tuple(
        MembershipSnapshot(
            id=row.id,
            organisation_id=row.organisation_id,
            role=row.role,
            is_active=row.is_active,
        )
        for row in rows
    )


def _authentication_snapshot(user: User) -> AuthenticationSnapshot:
    return AuthenticationSnapshot(
        password_hash=user.password_hash,
        external_provider=user.external_provider,
        external_subject=user.external_subject,
        last_login_at=user.last_login_at,
        session_version=user.session_version,
        failed_login_count=user.failed_login_count,
        locked_until=user.locked_until,
    )


def _locked_matching_users(db: Session, normalized_email: str) -> list[User]:
    """Return every exact normalized match, locked on PostgreSQL."""
    statement = (
        select(User)
        .where(func.lower(User.email) == normalized_email)
        .order_by(User.id)
        .with_for_update()
    )
    return list(db.scalars(statement))


def _validate_change_inputs(*, expected_user_id: int, reason: str) -> str:
    if expected_user_id <= 0:
        raise PlatformAdminChangeError("An expected positive user ID is required.")
    cleaned_reason = " ".join(reason.split())
    if not cleaned_reason:
        raise PlatformAdminChangeError("A non-empty approval reason is required.")
    if len(cleaned_reason) > 400:
        raise PlatformAdminChangeError("The approval reason is too long.")
    return cleaned_reason


def set_platform_admin(
    db: Session,
    *,
    email: str,
    expected_user_id: int,
    enabled: bool,
    reason: str,
    dry_run: bool = False,
) -> PlatformAdminChangeResult:
    """Set only one active existing user's platform-admin flag, atomically."""
    try:
        normalized_email = normalise_email(email)
    except BootstrapError as exc:
        raise PlatformAdminChangeError(str(exc)) from exc
    cleaned_reason = _validate_change_inputs(
        expected_user_id=expected_user_id,
        reason=reason,
    )

    matches = _locked_matching_users(db, normalized_email)
    if len(matches) != 1:
        raise PlatformAdminChangeError(
            "Expected exactly one existing user for the supplied normalized email."
        )
    user = matches[0]
    if user.id != expected_user_id:
        raise PlatformAdminChangeError("The expected user ID does not match the email.")
    if not user.is_active:
        raise PlatformAdminChangeError("Platform administration cannot be changed for an inactive user.")

    memberships_before = _memberships(db, user.id)
    authentication_before = _authentication_snapshot(user)
    platform_admin_before = {
        user_id: is_platform_admin
        for user_id, is_platform_admin in db.execute(
            select(User.id, User.is_platform_admin)
        )
    }
    previous = bool(user.is_platform_admin)
    requested = bool(enabled)
    changed = previous != requested

    if dry_run:
        return PlatformAdminChangeResult(
            user_id=user.id,
            active=True,
            previous_is_platform_admin=previous,
            new_is_platform_admin=requested,
            changed=changed,
            dry_run=True,
            membership_count=len(memberships_before),
            memberships=memberships_before,
        )

    user.is_platform_admin = requested
    audit(
        db,
        organisation_id=user.organisation_id,
        actor_user_id=None,
        action="platform_admin.existing_user_access_set",
        entity_type="user",
        entity_id=str(user.id),
        detail=(
            f"previous_is_platform_admin={previous}; "
            f"new_is_platform_admin={requested}; "
            f"reason={cleaned_reason}; source=scripts.set_platform_admin"
        ),
    )
    db.flush()

    db.refresh(user)
    memberships_after = _memberships(db, user.id)
    platform_admin_after = {
        user_id: is_platform_admin
        for user_id, is_platform_admin in db.execute(
            select(User.id, User.is_platform_admin)
        )
    }
    audit_event = db.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.action == "platform_admin.existing_user_access_set",
            AuditEvent.entity_type == "user",
            AuditEvent.entity_id == str(user.id),
        )
        .order_by(AuditEvent.id.desc())
    )

    expected_platform_admin = dict(platform_admin_before)
    expected_platform_admin[user.id] = requested
    if (
        not user.is_active
        or bool(user.is_platform_admin) != requested
        or _authentication_snapshot(user) != authentication_before
        or memberships_after != memberships_before
        or platform_admin_after != expected_platform_admin
        or audit_event is None
    ):
        raise PlatformAdminChangeError("Post-change verification failed; transaction was rolled back.")

    return PlatformAdminChangeResult(
        user_id=user.id,
        active=True,
        previous_is_platform_admin=previous,
        new_is_platform_admin=requested,
        changed=changed,
        dry_run=False,
        membership_count=len(memberships_before),
        memberships=memberships_before,
        audit_event_id=audit_event.id,
    )


def _verify_committed_change(
    session_factory: sessionmaker,
    *,
    email: str,
    expected_user_id: int,
    enabled: bool,
    result: PlatformAdminChangeResult,
) -> None:
    """Independently confirm the committed, non-sensitive invariants."""
    normalized_email = normalise_email(email)
    with session_factory() as db:
        matches = _locked_matching_users(db, normalized_email)
        if len(matches) != 1:
            raise PlatformAdminChangeError("Committed identity verification was ambiguous.")
        user = matches[0]
        audit_event = db.get(AuditEvent, result.audit_event_id)
        if (
            user.id != expected_user_id
            or not user.is_active
            or bool(user.is_platform_admin) != bool(enabled)
            or _memberships(db, user.id) != result.memberships
            or audit_event is None
            or audit_event.action != "platform_admin.existing_user_access_set"
            or audit_event.entity_id != str(user.id)
        ):
            raise PlatformAdminChangeError("Committed post-change verification failed.")


def execute_platform_admin_change(
    session_factory: sessionmaker = SessionLocal,
    *,
    confirmed: bool = False,
    **kwargs,
) -> PlatformAdminChangeResult:
    """Execute an approved change in one transaction, or a read-only dry run."""
    if not kwargs.get("dry_run", False) and not confirmed:
        raise PlatformAdminChangeError(
            "--confirm-production-change is required unless --dry-run is used."
        )
    with session_factory.begin() as db:
        result = set_platform_admin(db, **kwargs)
    if not result.dry_run:
        _verify_committed_change(
            session_factory,
            email=kwargs["email"],
            expected_user_id=kwargs["expected_user_id"],
            enabled=kwargs["enabled"],
            result=result,
        )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Set platform-administrator status for one existing active user."
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--expected-user-id", type=int, required=True)
    state = parser.add_mutually_exclusive_group(required=True)
    state.add_argument("--enable", action="store_true")
    state.add_argument("--disable", action="store_true")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--confirm-production-change",
        action="store_true",
        help="Required for any write, after recorded approval.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = execute_platform_admin_change(
            email=args.email,
            expected_user_id=args.expected_user_id,
            enabled=args.enable,
            reason=args.reason,
            dry_run=args.dry_run,
            confirmed=args.confirm_production_change,
        )
    except PlatformAdminChangeError as exc:
        parser.exit(2, f"Platform-admin change refused: {exc}\n")
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
