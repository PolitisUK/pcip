from __future__ import annotations

from dataclasses import asdict, replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql.dml import Update

import scripts.platform_admin_enable as enable_module
from app.db import Base
from app.models import AuditEvent, Organisation, OrganisationMembership, User
from scripts.platform_admin_enable import (
    PlatformAdminEnableError,
    execute_platform_admin_enable,
)


@pytest.fixture
def enable_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / f'platform-enable-{uuid4().hex}.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    yield engine, factory
    engine.dispose()


def make_expected_user(factory, *, active=True, platform_admin=False):
    with factory.begin() as db:
        primary = Organisation(id=1, name=f"Primary-{uuid4().hex}", slug=f"primary-{uuid4().hex}")
        second = Organisation(id=4, name=f"Second-{uuid4().hex}", slug=f"second-{uuid4().hex}")
        db.add_all([primary, second])
        db.flush()
        user = User(
            organisation_id=1,
            name="Existing user",
            email="existing@example.org",
            password_hash="sensitive-password-hash",
            external_provider="entra",
            external_subject="sensitive-external-subject",
            role="researcher",
            is_active=active,
            is_platform_admin=platform_admin,
            session_version=7,
            failed_login_count=2,
        )
        db.add(user)
        db.flush()
        db.add_all(
            [
                OrganisationMembership(user_id=user.id, organisation_id=1, role="owner", is_active=True),
                OrganisationMembership(user_id=user.id, organisation_id=4, role="owner", is_active=True),
            ]
        )
        return user.id


def user_state(factory, user_id):
    with factory() as db:
        user = db.get(User, user_id)
        memberships = tuple(
            (row.organisation_id, row.role, row.is_active)
            for row in db.scalars(
                select(OrganisationMembership)
                .where(OrganisationMembership.user_id == user_id)
                .order_by(OrganisationMembership.organisation_id)
            )
        )
        return {
            "id": user.id,
            "organisation_id": user.organisation_id,
            "name": user.name,
            "email": user.email,
            "password_hash": user.password_hash,
            "external_provider": user.external_provider,
            "external_subject": user.external_subject,
            "last_login_at": user.last_login_at,
            "session_version": user.session_version,
            "failed_login_count": user.failed_login_count,
            "locked_until": user.locked_until,
            "role": user.role,
            "is_active": user.is_active,
            "is_platform_admin": user.is_platform_admin,
            "created_at": user.created_at,
            "memberships": memberships,
        }


def test_enable_is_one_conditional_false_to_true_change(enable_database):
    engine, factory = enable_database
    user_id = make_expected_user(factory)
    before = user_state(factory, user_id)
    commits = []

    def record_commit(*_args):
        commits.append(True)

    event.listen(engine, "commit", record_commit)
    try:
        result = execute_platform_admin_enable(
            factory, email=" EXISTING@EXAMPLE.ORG ", expected_user_id=user_id
        )
    finally:
        event.remove(engine, "commit", record_commit)

    assert asdict(result) == {
        "user_id": user_id,
        "active": True,
        "previous_is_platform_admin": False,
        "is_platform_admin": True,
        "changed": True,
        "memberships": (
            {"organisation_id": 1, "role": "owner", "is_active": True},
            {"organisation_id": 4, "role": "owner", "is_active": True},
        ),
        "memberships_unchanged": True,
        "account_fields_unchanged": True,
    }
    after = user_state(factory, user_id)
    assert {key: value for key, value in after.items() if key != "is_platform_admin"} == {
        key: value for key, value in before.items() if key != "is_platform_admin"
    }
    assert after["is_platform_admin"] is True
    assert len(commits) == 1
    with factory() as db:
        assert db.scalar(select(AuditEvent)) is None


@pytest.mark.parametrize(
    "email,user_id",
    [
        ("", 1),
        ("missing@example.org", 1),
        ("existing@example.org", 999),
        ("existing@example.org", 0),
        ("existing@example.org", "1"),
    ],
)
def test_missing_unknown_or_malformed_target_fails_closed(enable_database, email, user_id):
    _, factory = enable_database
    expected_id = make_expected_user(factory)
    before = user_state(factory, expected_id)
    with pytest.raises(PlatformAdminEnableError):
        execute_platform_admin_enable(factory, email=email, expected_user_id=user_id)
    assert user_state(factory, expected_id) == before


def test_email_and_user_id_must_resolve_the_same_account(enable_database):
    _, factory = enable_database
    first_id = make_expected_user(factory)
    with factory.begin() as db:
        other = User(
            organisation_id=1,
            name="Other user",
            email="other@example.org",
            role="researcher",
            is_active=True,
            is_platform_admin=False,
        )
        db.add(other)
        db.flush()
        other_id = other.id
    with pytest.raises(PlatformAdminEnableError):
        execute_platform_admin_enable(factory, email="other@example.org", expected_user_id=first_id)
    assert user_state(factory, first_id)["is_platform_admin"] is False
    assert user_state(factory, other_id)["is_platform_admin"] is False


def test_ambiguous_email_resolution_fails_closed(enable_database, monkeypatch):
    _, factory = enable_database
    user_id = make_expected_user(factory)
    with factory() as db:
        user = db.get(User, user_id)
        monkeypatch.setattr(enable_module, "_locked_by_email", lambda *_args: [user, user])
        with pytest.raises(PlatformAdminEnableError):
            enable_module.platform_admin_enable(
                db, email="existing@example.org", expected_user_id=user_id
            )
    assert user_state(factory, user_id)["is_platform_admin"] is False


@pytest.mark.parametrize("active,platform_admin", [(False, False), (True, True)])
def test_ineligible_or_already_admin_never_updates(enable_database, active, platform_admin):
    engine, factory = enable_database
    user_id = make_expected_user(factory, active=active, platform_admin=platform_admin)
    statements = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with pytest.raises(PlatformAdminEnableError):
            execute_platform_admin_enable(factory, email="existing@example.org", expected_user_id=user_id)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert not any(statement.lstrip().upper().startswith("UPDATE") for statement in statements)


@pytest.mark.parametrize(
    "membership_mutator",
    [
        lambda db, user_id: db.query(OrganisationMembership).filter_by(user_id=user_id, organisation_id=4).delete(),
        lambda db, user_id: setattr(db.scalar(select(OrganisationMembership).where(OrganisationMembership.user_id == user_id, OrganisationMembership.organisation_id == 4)), "role", "researcher"),
        lambda db, user_id: setattr(db.scalar(select(OrganisationMembership).where(OrganisationMembership.user_id == user_id, OrganisationMembership.organisation_id == 4)), "is_active", False),
    ],
)
def test_unexpected_membership_state_fails_closed(enable_database, membership_mutator):
    _, factory = enable_database
    user_id = make_expected_user(factory)
    with factory.begin() as db:
        membership_mutator(db, user_id)
    with pytest.raises(PlatformAdminEnableError):
        execute_platform_admin_enable(factory, email="existing@example.org", expected_user_id=user_id)
    assert user_state(factory, user_id)["is_platform_admin"] is False


@pytest.mark.parametrize("rowcount", [0, 2])
def test_conditional_update_rowcount_anomalies_roll_back(enable_database, monkeypatch, rowcount):
    _, factory = enable_database
    user_id = make_expected_user(factory)
    original_execute = enable_module.Session.execute

    def guarded_execute(session, statement, *args, **kwargs):
        if isinstance(statement, Update):
            return SimpleNamespace(rowcount=rowcount)
        return original_execute(session, statement, *args, **kwargs)

    monkeypatch.setattr(enable_module.Session, "execute", guarded_execute)
    with pytest.raises(PlatformAdminEnableError):
        execute_platform_admin_enable(factory, email="existing@example.org", expected_user_id=user_id)
    assert user_state(factory, user_id)["is_platform_admin"] is False


def test_post_write_verification_failure_rolls_back(enable_database, monkeypatch):
    _, factory = enable_database
    user_id = make_expected_user(factory)
    original_snapshot = enable_module._account_snapshot
    calls = 0

    def changed_snapshot(user):
        nonlocal calls
        calls += 1
        snapshot = original_snapshot(user)
        return replace(snapshot, name="unexpected") if calls > 1 else snapshot

    monkeypatch.setattr(enable_module, "_account_snapshot", changed_snapshot)
    with pytest.raises(PlatformAdminEnableError):
        execute_platform_admin_enable(factory, email="existing@example.org", expected_user_id=user_id)
    assert user_state(factory, user_id)["is_platform_admin"] is False


def test_result_never_contains_email_or_authentication_material(enable_database):
    _, factory = enable_database
    user_id = make_expected_user(factory)
    approved_result = execute_platform_admin_enable(
        factory, email="existing@example.org", expected_user_id=user_id
    ).approved_result()
    assert isinstance(approved_result["memberships"], list)
    rendered = str(approved_result)
    assert "existing@example.org" not in rendered
    assert "sensitive-password-hash" not in rendered
    assert "sensitive-external-subject" not in rendered
