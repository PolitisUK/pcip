from __future__ import annotations

import json
from dataclasses import asdict
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker

import scripts.set_platform_admin as platform_admin_script
from app.db import Base
from app.models import AuditEvent, Organisation, OrganisationMembership, User
from scripts.set_platform_admin import (
    PlatformAdminChangeError,
    execute_platform_admin_change,
)


@pytest.fixture
def platform_admin_database(tmp_path):
    path = tmp_path / f"platform-admin-{uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    yield engine, factory
    engine.dispose()


def make_user(factory, *, email="existing@example.org", active=True, platform_admin=False):
    with factory.begin() as db:
        organisation = Organisation(name=f"Organisation-{uuid4().hex}", slug=f"org-{uuid4().hex}")
        db.add(organisation)
        db.flush()
        user = User(
            organisation_id=organisation.id,
            name="Existing user",
            email=email,
            password_hash="unchanged-password-hash",
            external_provider="entra",
            external_subject="external-subject",
            role="researcher",
            is_active=active,
            is_platform_admin=platform_admin,
            session_version=7,
            failed_login_count=2,
        )
        db.add(user)
        db.flush()
        membership = OrganisationMembership(
            user_id=user.id,
            organisation_id=organisation.id,
            role="researcher",
            is_active=True,
        )
        db.add(membership)
        db.flush()
        return user.id, membership.id, organisation.id


def change(factory, user_id, **overrides):
    values = {
        "email": "existing@example.org",
        "expected_user_id": user_id,
        "enabled": True,
        "reason": "Authorised platform administration access",
        "dry_run": False,
        "confirmed": True,
    }
    values.update(overrides)
    return execute_platform_admin_change(factory, **values)


def test_exact_active_existing_user_dry_run_preserves_every_record(platform_admin_database):
    _, factory = platform_admin_database
    user_id, membership_id, organisation_id = make_user(factory)

    result = change(
        factory,
        user_id,
        email=" EXISTING@EXAMPLE.ORG ",
        dry_run=True,
        confirmed=False,
    )

    assert result.dry_run is True
    assert result.changed is True
    assert result.user_id == user_id
    assert result.previous_is_platform_admin is False
    assert result.new_is_platform_admin is True
    assert result.membership_count == 1
    assert result.audit_event_id is None
    assert result.memberships[0].id == membership_id
    assert result.memberships[0].organisation_id == organisation_id
    assert result.memberships[0].role == "researcher"
    rendered = json.dumps(asdict(result), sort_keys=True)
    assert "existing@example.org" not in rendered
    assert "unchanged-password-hash" not in rendered
    assert "external-subject" not in rendered
    with factory() as db:
        assert db.get(User, user_id).is_platform_admin is False
        assert db.scalar(select(AuditEvent)) is None


def test_exact_promotion_is_audited_and_preserves_user_and_membership(platform_admin_database):
    _, factory = platform_admin_database
    user_id, membership_id, organisation_id = make_user(factory)

    result = change(factory, user_id)

    assert result.changed is True
    assert result.previous_is_platform_admin is False
    assert result.new_is_platform_admin is True
    assert result.audit_event_id is not None
    with factory() as db:
        user = db.get(User, user_id)
        membership = db.get(OrganisationMembership, membership_id)
        audit = db.get(AuditEvent, result.audit_event_id)
        assert user.is_active is True
        assert user.is_platform_admin is True
        assert user.password_hash == "unchanged-password-hash"
        assert user.external_provider == "entra"
        assert user.external_subject == "external-subject"
        assert user.session_version == 7
        assert user.failed_login_count == 2
        assert membership.organisation_id == organisation_id
        assert membership.role == "researcher"
        assert membership.is_active is True
        assert audit.action == "platform_admin.existing_user_access_set"
        assert audit.entity_id == str(user_id)
        assert audit.organisation_id == organisation_id
        assert "previous_is_platform_admin=False" in audit.detail
        assert "new_is_platform_admin=True" in audit.detail
        assert "source=scripts.set_platform_admin" in audit.detail
        assert "existing@example.org" not in audit.detail


def test_exact_demotion_is_audited(platform_admin_database):
    _, factory = platform_admin_database
    user_id, _, _ = make_user(factory, platform_admin=True)

    result = change(factory, user_id, enabled=False)

    assert result.changed is True
    assert result.previous_is_platform_admin is True
    assert result.new_is_platform_admin is False
    with factory() as db:
        assert db.get(User, user_id).is_platform_admin is False
        assert db.get(AuditEvent, result.audit_event_id) is not None


@pytest.mark.parametrize(
    ("initial", "enabled"),
    [(True, True), (False, False)],
)
def test_noop_is_safe_but_retains_an_audit_trail(platform_admin_database, initial, enabled):
    _, factory = platform_admin_database
    user_id, _, _ = make_user(factory, platform_admin=initial)

    result = change(factory, user_id, enabled=enabled)

    assert result.changed is False
    assert result.audit_event_id is not None
    with factory() as db:
        assert db.get(User, user_id).is_platform_admin is initial
        assert db.scalar(select(AuditEvent).where(AuditEvent.id == result.audit_event_id))


@pytest.mark.parametrize(
    ("email", "message"),
    [("not an email", "valid administrator email"), ("missing@example.org", "exactly one")],
)
def test_invalid_or_unknown_identity_fails_closed(platform_admin_database, email, message):
    _, factory = platform_admin_database
    user_id, _, _ = make_user(factory)

    with pytest.raises(PlatformAdminChangeError, match=message):
        change(factory, user_id, email=email)

    with factory() as db:
        assert db.get(User, user_id).is_platform_admin is False
        assert db.scalar(select(AuditEvent)) is None


def test_duplicate_normalized_matches_fail_closed(platform_admin_database, monkeypatch):
    _, factory = platform_admin_database
    user_id, _, _ = make_user(factory)
    with factory() as db:
        user = db.get(User, user_id)
        monkeypatch.setattr(
            platform_admin_script,
            "_locked_matching_users",
            lambda *_args: [user, user],
        )
        with pytest.raises(PlatformAdminChangeError, match="exactly one"):
            platform_admin_script.set_platform_admin(
                db,
                email="existing@example.org",
                expected_user_id=user_id,
                enabled=True,
                reason="Approved",
            )


def test_expected_id_mismatch_inactive_user_and_missing_confirmation_are_refused(platform_admin_database):
    _, factory = platform_admin_database
    user_id, _, _ = make_user(factory)

    with pytest.raises(PlatformAdminChangeError, match="does not match"):
        change(factory, user_id + 1)
    with pytest.raises(PlatformAdminChangeError, match="confirm-production-change"):
        change(factory, user_id, confirmed=False)

    inactive_user_id, _, _ = make_user(
        factory,
        email="inactive@example.org",
        active=False,
    )
    with pytest.raises(PlatformAdminChangeError, match="inactive"):
        change(factory, inactive_user_id, email="inactive@example.org")

    with factory() as db:
        assert db.get(User, user_id).is_platform_admin is False
        assert db.get(User, inactive_user_id).is_platform_admin is False
        assert db.scalar(select(AuditEvent)) is None


def test_no_other_user_is_modified(platform_admin_database):
    _, factory = platform_admin_database
    user_id, _, _ = make_user(factory)
    other_user_id, _, _ = make_user(factory, email="other@example.org", platform_admin=False)

    change(factory, user_id)

    with factory() as db:
        assert db.get(User, user_id).is_platform_admin is True
        assert db.get(User, other_user_id).is_platform_admin is False


def test_audit_failure_rolls_back_platform_admin_change(platform_admin_database):
    _, factory = platform_admin_database
    user_id, _, _ = make_user(factory)

    def reject_audit(*_args, **_kwargs):
        raise RuntimeError("simulated audit failure")

    sqlalchemy_event.listen(AuditEvent, "before_insert", reject_audit)
    try:
        with pytest.raises(RuntimeError, match="simulated audit failure"):
            change(factory, user_id)
    finally:
        sqlalchemy_event.remove(AuditEvent, "before_insert", reject_audit)

    with factory() as db:
        assert db.get(User, user_id).is_platform_admin is False
        assert db.scalar(select(AuditEvent)) is None


def test_postgresql_target_query_uses_a_row_lock(platform_admin_database):
    _, factory = platform_admin_database

    class CapturingSession:
        statement = None

        def scalars(self, statement):
            self.statement = statement
            return []

    db = CapturingSession()
    assert platform_admin_script._locked_matching_users(db, "existing@example.org") == []
    assert "FOR UPDATE" in str(
        db.statement.compile(dialect=postgresql.dialect())
    ).upper()
