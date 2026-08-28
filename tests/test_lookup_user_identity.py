from __future__ import annotations

import json
from dataclasses import asdict
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.orm import sessionmaker

import scripts.lookup_user_identity as lookup_script
from app.db import Base
from app.models import AuditEvent, Organisation, OrganisationMembership, User
from scripts.lookup_user_identity import (
    UserIdentityLookupError,
    execute_user_identity_lookup,
)


@pytest.fixture
def identity_database(tmp_path):
    path = tmp_path / f"identity-{uuid4().hex}.db"
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
            password_hash="sensitive-password-hash",
            external_provider="entra",
            external_subject="sensitive-external-subject",
            role="researcher",
            is_active=active,
            is_platform_admin=platform_admin,
            session_version=7,
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


def test_exact_normalized_email_resolves_non_sensitive_identity(identity_database):
    _, factory = identity_database
    user_id, _, organisation_id = make_user(factory, platform_admin=True)

    result = execute_user_identity_lookup(
        factory,
        email=" EXISTING@EXAMPLE.ORG ",
    )

    assert result.user_id == user_id
    assert result.active is True
    assert result.is_platform_admin is True
    assert result.memberships == (
        lookup_script.MembershipIdentity(
            organisation_id=organisation_id,
            role="researcher",
            is_active=True,
        ),
    )
    rendered = json.dumps(asdict(result), sort_keys=True)
    assert "existing@example.org" not in rendered
    assert "sensitive-password-hash" not in rendered
    assert "sensitive-external-subject" not in rendered


def test_unknown_user_fails_closed_without_audit_or_mutation(identity_database):
    _, factory = identity_database
    user_id, membership_id, _ = make_user(factory)

    with pytest.raises(UserIdentityLookupError, match="exactly one"):
        execute_user_identity_lookup(factory, email="missing@example.org")

    with factory() as db:
        assert db.get(User, user_id).is_platform_admin is False
        assert db.get(OrganisationMembership, membership_id).role == "researcher"
        assert db.scalar(select(AuditEvent)) is None


def test_ambiguous_normalized_identity_fails_closed(identity_database, monkeypatch):
    _, factory = identity_database
    user_id, _, _ = make_user(factory)
    with factory() as db:
        user = db.get(User, user_id)
        monkeypatch.setattr(lookup_script, "_matching_users", lambda *_args: [user, user])
        with pytest.raises(UserIdentityLookupError, match="exactly one"):
            lookup_script.lookup_user_identity(db, email="existing@example.org")


def test_inactive_user_is_reported_but_not_changed(identity_database):
    _, factory = identity_database
    user_id, _, _ = make_user(factory, active=False)

    result = execute_user_identity_lookup(factory, email="existing@example.org")

    assert result.user_id == user_id
    assert result.active is False
    assert result.is_platform_admin is False
    with factory() as db:
        assert db.get(User, user_id).is_active is False
        assert db.scalar(select(AuditEvent)) is None


def test_lookup_executes_no_database_mutation(identity_database):
    engine, factory = identity_database
    user_id, membership_id, _ = make_user(factory)
    statements: list[str] = []

    def record_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    sqlalchemy_event.listen(engine, "before_cursor_execute", record_statement)
    try:
        result = execute_user_identity_lookup(factory, email="existing@example.org")
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", record_statement)

    assert result.user_id == user_id
    assert all(
        statement.lstrip().upper().startswith("SELECT")
        for statement in statements
    )
    with factory() as db:
        user = db.get(User, user_id)
        membership = db.get(OrganisationMembership, membership_id)
        assert user.is_platform_admin is False
        assert user.password_hash == "sensitive-password-hash"
        assert membership.role == "researcher"
        assert db.scalar(select(AuditEvent)) is None


def test_postgresql_lookup_enforces_read_only_transaction_and_rolls_back(monkeypatch):
    class Dialect:
        name = "postgresql"

    class Bind:
        dialect = Dialect()

    class ProbeSession:
        new = set()
        dirty = set()
        deleted = set()

        def __init__(self):
            self.statements = []
            self.rolled_back = False
            self.closed = False

        def get_bind(self):
            return Bind()

        def execute(self, statement):
            self.statements.append(str(statement))

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

        def commit(self):  # pragma: no cover - proves commit is never called
            raise AssertionError("read-only lookup must not commit")

    session = ProbeSession()
    expected = lookup_script.UserIdentity(
        user_id=1,
        active=True,
        is_platform_admin=False,
        memberships=(),
    )
    monkeypatch.setattr(lookup_script, "lookup_user_identity", lambda *_args, **_kwargs: expected)

    assert lookup_script.execute_user_identity_lookup(
        lambda: session,
        email="existing@example.org",
    ) == expected
    assert session.statements == ["SET TRANSACTION READ ONLY"]
    assert session.rolled_back is True
    assert session.closed is True
