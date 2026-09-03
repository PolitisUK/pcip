from __future__ import annotations

import json
from dataclasses import asdict
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.orm import sessionmaker

import scripts.platform_admin_dry_run as dry_run_script
from app.db import Base
from app.models import AuditEvent, Organisation, OrganisationMembership, User
from scripts.platform_admin_dry_run import (
    PlatformAdminDryRunError,
    execute_platform_admin_dry_run,
)


@pytest.fixture
def dry_run_database(tmp_path):
    path = tmp_path / f"platform-admin-dry-run-{uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    yield engine, factory
    engine.dispose()


def make_user(
    factory,
    *,
    email="existing@example.org",
    active=True,
    platform_admin=False,
):
    with factory.begin() as db:
        organisation = Organisation(
            name=f"Organisation-{uuid4().hex}",
            slug=f"org-{uuid4().hex}",
        )
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
            failed_login_count=2,
        )
        db.add(user)
        db.flush()
        membership = OrganisationMembership(
            user_id=user.id,
            organisation_id=organisation.id,
            role="owner",
            is_active=True,
        )
        db.add(membership)
        db.flush()
        return user.id, membership.id, organisation.id


def test_valid_dry_run_binds_identifiers_and_preserves_all_state(dry_run_database):
    _, factory = dry_run_database
    user_id, membership_id, organisation_id = make_user(factory)

    result = execute_platform_admin_dry_run(
        factory,
        email=" EXISTING@EXAMPLE.ORG ",
        expected_user_id=user_id,
    )

    assert asdict(result) == {
        "user_id": user_id,
        "active": True,
        "current_is_platform_admin": False,
        "intended_is_platform_admin": True,
        "would_change": True,
        "memberships": (
            {"organisation_id": organisation_id, "role": "owner", "is_active": True},
        ),
        "memberships_unchanged": True,
        "account_fields_unchanged": True,
    }
    rendered = json.dumps(asdict(result), sort_keys=True)
    assert "existing@example.org" not in rendered
    assert "sensitive-password-hash" not in rendered
    assert "sensitive-external-subject" not in rendered
    with factory() as db:
        user = db.get(User, user_id)
        membership = db.get(OrganisationMembership, membership_id)
        assert user.is_platform_admin is False
        assert user.is_active is True
        assert user.password_hash == "sensitive-password-hash"
        assert user.external_subject == "sensitive-external-subject"
        assert user.session_version == 7
        assert user.failed_login_count == 2
        assert membership.role == "owner"
        assert membership.is_active is True
        assert db.scalar(select(AuditEvent)) is None


@pytest.mark.parametrize(
    ("email", "id_offset", "message"),
    [
        ("missing@example.org", 0, "exactly one"),
        ("existing@example.org", 1, "does not match"),
        ("other@example.org", 0, "exactly one"),
    ],
)
def test_unknown_or_mismatched_identifiers_fail_closed(
    dry_run_database,
    email,
    id_offset,
    message,
):
    _, factory = dry_run_database
    user_id, _, _ = make_user(factory)

    with pytest.raises(PlatformAdminDryRunError, match=message):
        execute_platform_admin_dry_run(
            factory,
            email=email,
            expected_user_id=user_id + id_offset,
        )

    with factory() as db:
        assert db.get(User, user_id).is_platform_admin is False
        assert db.scalar(select(AuditEvent)) is None


def test_ambiguous_normalized_email_fails_closed(dry_run_database, monkeypatch):
    _, factory = dry_run_database
    user_id, _, _ = make_user(factory)
    with factory() as db:
        user = db.get(User, user_id)
        monkeypatch.setattr(
            dry_run_script, "_matching_users", lambda *_args: [user, user]
        )
        with pytest.raises(PlatformAdminDryRunError, match="exactly one"):
            dry_run_script.platform_admin_dry_run(
                db,
                email="existing@example.org",
                expected_user_id=user_id,
            )


def test_inactive_user_is_reported_without_proposing_a_change(dry_run_database):
    _, factory = dry_run_database
    user_id, _, _ = make_user(factory, active=False)

    result = execute_platform_admin_dry_run(
        factory,
        email="existing@example.org",
        expected_user_id=user_id,
    )

    assert result.active is False
    assert result.current_is_platform_admin is False
    assert result.intended_is_platform_admin is False
    assert result.would_change is False


def test_already_platform_admin_is_reported_as_no_change(dry_run_database):
    _, factory = dry_run_database
    user_id, _, _ = make_user(factory, platform_admin=True)

    result = execute_platform_admin_dry_run(
        factory,
        email="existing@example.org",
        expected_user_id=user_id,
    )

    assert result.current_is_platform_admin is True
    assert result.intended_is_platform_admin is True
    assert result.would_change is False


def test_dry_run_executes_only_selects_and_creates_no_audit(dry_run_database):
    engine, factory = dry_run_database
    user_id, _, _ = make_user(factory)
    statements: list[str] = []

    def record_statement(
        _conn, _cursor, statement, _parameters, _context, _executemany
    ):
        statements.append(statement)

    sqlalchemy_event.listen(engine, "before_cursor_execute", record_statement)
    try:
        execute_platform_admin_dry_run(
            factory,
            email="existing@example.org",
            expected_user_id=user_id,
        )
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", record_statement)

    assert statements
    assert all(
        statement.lstrip().upper().startswith("SELECT") for statement in statements
    )
    with factory() as db:
        assert db.get(User, user_id).is_platform_admin is False
        assert db.scalar(select(AuditEvent)) is None


def test_postgresql_dry_run_sets_read_only_then_rolls_back(monkeypatch):
    class Dialect:
        name = "postgresql"

    class Bind:
        dialect = Dialect()

    class ProbeSession:
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
            raise AssertionError("dry run must never commit")

    session = ProbeSession()
    expected = dry_run_script.PlatformAdminDryRunResult(
        user_id=1,
        active=True,
        current_is_platform_admin=False,
        intended_is_platform_admin=True,
        would_change=True,
        memberships=(),
        memberships_unchanged=True,
        account_fields_unchanged=True,
    )
    monkeypatch.setattr(
        dry_run_script, "platform_admin_dry_run", lambda *_args, **_kwargs: expected
    )

    assert (
        execute_platform_admin_dry_run(
            lambda: session,
            email="existing@example.org",
            expected_user_id=1,
        )
        == expected
    )
    assert session.statements == ["SET TRANSACTION READ ONLY"]
    assert session.rolled_back is True
    assert session.closed is True


def test_postgresql_read_only_transaction_rejects_an_attempted_mutation(monkeypatch):
    class Dialect:
        name = "postgresql"

    class Bind:
        dialect = Dialect()

    class ReadOnlyProbe:
        def __init__(self):
            self.read_only = False
            self.rolled_back = False
            self.closed = False

        def get_bind(self):
            return Bind()

        def execute(self, statement):
            sql = str(statement).strip().upper()
            if sql == "SET TRANSACTION READ ONLY":
                self.read_only = True
                return
            if self.read_only and sql.startswith("UPDATE"):
                raise RuntimeError("cannot execute UPDATE in a read-only transaction")
            raise AssertionError(sql)

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    session = ReadOnlyProbe()

    def attempt_mutation(db, **_kwargs):
        db.execute(text("UPDATE users SET is_platform_admin = true"))

    monkeypatch.setattr(dry_run_script, "platform_admin_dry_run", attempt_mutation)
    with pytest.raises(RuntimeError, match="read-only transaction"):
        execute_platform_admin_dry_run(
            lambda: session,
            email="existing@example.org",
            expected_user_id=1,
        )
    assert session.read_only is True
    assert session.rolled_back is True
    assert session.closed is True


def test_cli_rejects_mutation_flags_and_arbitrary_arguments():
    for argv in (
        ["--email", "existing@example.org", "--expected-user-id", "1", "--enable"],
        [
            "--email",
            "existing@example.org",
            "--expected-user-id",
            "1",
            "--dry-run=false",
        ],
        [
            "--email",
            "existing@example.org",
            "--expected-user-id",
            "1",
            "--module",
            "os",
        ],
        [
            "--email",
            "existing@example.org",
            "--expected-user-id",
            "1",
            "--command",
            "id",
        ],
    ):
        with pytest.raises(SystemExit) as exc:
            dry_run_script.main(argv)
        assert exc.value.code == 2
