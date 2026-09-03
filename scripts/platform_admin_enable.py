"""One narrowly-scoped platform-administrator enable transition.

This module is deliberately not a CLI.  The production worker can call only
``execute_platform_admin_enable`` after it has validated the fixed queue
operation; callers cannot supply a target state, reason, flags, or arguments.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.db import SessionLocal
from app.models import OrganisationMembership, User
from scripts.bootstrap_admin import BootstrapError, normalise_email


class PlatformAdminEnableError(RuntimeError):
    """Raised when the fixed false-to-true transition is unsafe."""


EXPECTED_OWNER_MEMBERSHIPS = ((1, "owner", True), (4, "owner", True))


@dataclass(frozen=True)
class MembershipSnapshot:
    organisation_id: int
    role: str
    is_active: bool


@dataclass(frozen=True)
class AccountSnapshot:
    """Every User field except the single field this operation may change."""

    id: int
    organisation_id: int
    name: str
    email: str
    password_hash: str | None
    external_provider: str | None
    external_subject: str | None
    last_login_at: object
    session_version: int
    failed_login_count: int
    locked_until: object
    role: str
    is_active: bool
    created_at: object


@dataclass(frozen=True)
class PlatformAdminEnableResult:
    user_id: int
    active: bool
    previous_is_platform_admin: bool
    is_platform_admin: bool
    changed: bool
    memberships: tuple[MembershipSnapshot, ...]
    memberships_unchanged: bool
    account_fields_unchanged: bool

    def approved_result(self) -> dict[str, object]:
        """Return the only result shape that may leave the worker."""
        result = asdict(self)
        result["memberships"] = list(result["memberships"])
        return result


def _account_snapshot(user: User) -> AccountSnapshot:
    return AccountSnapshot(
        id=user.id,
        organisation_id=user.organisation_id,
        name=user.name,
        email=user.email,
        password_hash=user.password_hash,
        external_provider=user.external_provider,
        external_subject=user.external_subject,
        last_login_at=user.last_login_at,
        session_version=user.session_version,
        failed_login_count=user.failed_login_count,
        locked_until=user.locked_until,
        role=user.role,
        is_active=bool(user.is_active),
        created_at=user.created_at,
    )


def _locked_by_email(db: Session, normalized_email: str) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(func.lower(User.email) == normalized_email)
            .order_by(User.id)
            .with_for_update()
        )
    )


def _locked_by_id(db: Session, user_id: int) -> list[User]:
    return list(
        db.scalars(select(User).where(User.id == user_id).with_for_update())
    )


def _locked_memberships(db: Session, user_id: int) -> tuple[MembershipSnapshot, ...]:
    return tuple(
        MembershipSnapshot(
            organisation_id=row.organisation_id,
            role=row.role,
            is_active=bool(row.is_active),
        )
        for row in db.scalars(
            select(OrganisationMembership)
            .where(OrganisationMembership.user_id == user_id)
            .order_by(OrganisationMembership.organisation_id, OrganisationMembership.id)
            .with_for_update()
        )
    )


def _require_expected_memberships(
    memberships: tuple[MembershipSnapshot, ...],
) -> None:
    observed = tuple(
        (item.organisation_id, item.role, item.is_active) for item in memberships
    )
    if observed != EXPECTED_OWNER_MEMBERSHIPS:
        raise PlatformAdminEnableError("Expected active owner memberships are not present.")


def _resolve_target(
    db: Session, *, email: str, expected_user_id: int
) -> User:
    if type(expected_user_id) is not int or expected_user_id <= 0:
        raise PlatformAdminEnableError("An expected positive user ID is required.")
    try:
        normalized_email = normalise_email(email)
    except BootstrapError as exc:
        raise PlatformAdminEnableError(str(exc)) from exc

    email_matches = _locked_by_email(db, normalized_email)
    id_matches = _locked_by_id(db, expected_user_id)
    if len(email_matches) != 1 or len(id_matches) != 1:
        raise PlatformAdminEnableError("The target account could not be established exactly.")
    email_user = email_matches[0]
    id_user = id_matches[0]
    if email_user.id != id_user.id:
        raise PlatformAdminEnableError("The target account could not be established exactly.")
    return email_user


def platform_admin_enable(
    db: Session, *, email: str, expected_user_id: int
) -> PlatformAdminEnableResult:
    """Change only one active, expected account from false to true.

    The enclosing transaction commits only after all post-write checks pass.
    """
    user = _resolve_target(db, email=email, expected_user_id=expected_user_id)
    if not user.is_active or bool(user.is_platform_admin):
        raise PlatformAdminEnableError("The target account is not eligible for this transition.")

    account_before = _account_snapshot(user)
    memberships_before = _locked_memberships(db, user.id)
    _require_expected_memberships(memberships_before)

    update_result = db.execute(
        update(User)
        .where(
            User.id == user.id,
            User.is_active.is_(True),
            User.is_platform_admin.is_(False),
        )
        .values(is_platform_admin=True)
        .execution_options(synchronize_session=False)
    )
    if update_result.rowcount != 1:
        raise PlatformAdminEnableError("The target account changed before the transition could commit.")

    db.expire(user)
    db.refresh(user)
    memberships_after = _locked_memberships(db, user.id)
    if (
        not user.is_active
        or not bool(user.is_platform_admin)
        or _account_snapshot(user) != account_before
        or memberships_after != memberships_before
        or db.new
        or db.dirty
        or db.deleted
    ):
        raise PlatformAdminEnableError("Post-write verification failed.")

    return PlatformAdminEnableResult(
        user_id=user.id,
        active=True,
        previous_is_platform_admin=False,
        is_platform_admin=True,
        changed=True,
        memberships=memberships_after,
        memberships_unchanged=True,
        account_fields_unchanged=True,
    )


def execute_platform_admin_enable(
    session_factory: sessionmaker = SessionLocal,
    *,
    email: str,
    expected_user_id: int,
) -> PlatformAdminEnableResult:
    """Run the fixed operation in one transaction; any error rolls it back."""
    with session_factory.begin() as db:
        return platform_admin_enable(
            db,
            email=email,
            expected_user_id=expected_user_id,
        )
