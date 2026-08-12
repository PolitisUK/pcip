from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import AuditEvent, Organisation, OrganisationMembership, User
from scripts.bootstrap_admin import BootstrapError, execute_bootstrap


@pytest.fixture
def bootstrap_database(tmp_path):
    path = tmp_path / f"bootstrap-{uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    yield engine, factory
    engine.dispose()


def bootstrap_kwargs(**overrides):
    values = {
        "organisation_name": "CitizenCentric",
        "organisation_slug": "citizencentric",
        "administrator_name": "Thomas Foreman",
        "email": "thomas.foreman@politisconsulting.co.uk",
        "role": "owner",
        "create_organisation": True,
        "dry_run": False,
    }
    values.update(overrides)
    return values


def test_dry_run_does_not_create_records(bootstrap_database):
    _, factory = bootstrap_database
    result = execute_bootstrap(factory, **bootstrap_kwargs(dry_run=True))

    assert result.dry_run is True
    assert result.organisation_created is True
    assert result.account_created is True
    with factory() as db:
        assert db.scalar(select(Organisation)) is None
        assert db.scalar(select(User)) is None
        assert db.scalar(select(OrganisationMembership)) is None


def test_bootstrap_creates_owner_membership_and_audit_atomically(bootstrap_database):
    _, factory = bootstrap_database
    result = execute_bootstrap(factory, **bootstrap_kwargs())

    assert result.role == "owner"
    assert result.organisation_created is True
    with factory() as db:
        organisation = db.scalar(select(Organisation))
        user = db.scalar(select(User))
        membership = db.scalar(select(OrganisationMembership))
        audit = db.scalar(select(AuditEvent))

        assert organisation.name == "CitizenCentric"
        assert organisation.slug == "citizencentric"
        assert user.email == "thomas.foreman@politisconsulting.co.uk"
        assert user.password_hash is None
        assert user.role == "owner"
        assert user.is_active is True
        assert membership.user_id == user.id
        assert membership.organisation_id == organisation.id
        assert membership.role == "owner"
        assert membership.is_active is True
        assert audit.action == "auth.admin_bootstrapped"
        assert audit.actor_user_id is None


def test_bootstrap_refuses_duplicate_global_email(bootstrap_database):
    _, factory = bootstrap_database
    with factory.begin() as db:
        other = Organisation(name="Other", slug="other")
        db.add(other)
        db.flush()
        db.add(
            User(
                organisation_id=other.id,
                name="Existing Identity",
                email="thomas.foreman@politisconsulting.co.uk",
                password_hash=None,
                role="researcher",
            )
        )

    with pytest.raises(BootstrapError, match="already exists"):
        execute_bootstrap(factory, **bootstrap_kwargs())

    with factory() as db:
        assert db.scalar(
            select(Organisation).where(Organisation.slug == "citizencentric")
        ) is None


def test_bootstrap_refuses_existing_privileged_membership(bootstrap_database):
    _, factory = bootstrap_database
    with factory.begin() as db:
        organisation = Organisation(name="CitizenCentric", slug="citizencentric")
        db.add(organisation)
        db.flush()
        owner = User(
            organisation_id=organisation.id,
            name="Existing Owner",
            email="owner@example.org",
            password_hash=None,
            role="owner",
        )
        db.add(owner)
        db.flush()
        db.add(
            OrganisationMembership(
                user_id=owner.id,
                organisation_id=organisation.id,
                role="owner",
            )
        )

    with pytest.raises(BootstrapError, match="already exists"):
        execute_bootstrap(
            factory,
            **bootstrap_kwargs(create_organisation=False),
        )

    with factory() as db:
        assert db.scalar(select(func.count(User.id))) == 1


def test_bootstrap_rolls_back_every_record_when_audit_insert_fails(
    bootstrap_database,
):
    engine, factory = bootstrap_database

    def reject_audit(*_args, **_kwargs):
        raise RuntimeError("simulated audit failure")

    sqlalchemy_event.listen(AuditEvent, "before_insert", reject_audit)
    try:
        with pytest.raises(RuntimeError, match="simulated audit failure"):
            execute_bootstrap(factory, **bootstrap_kwargs())
    finally:
        sqlalchemy_event.remove(AuditEvent, "before_insert", reject_audit)

    with factory() as db:
        assert db.scalar(select(Organisation)) is None
        assert db.scalar(select(User)) is None
        assert db.scalar(select(OrganisationMembership)) is None
        assert db.scalar(select(AuditEvent)) is None


def test_bootstrap_requires_existing_organisation_without_create_flag(
    bootstrap_database,
):
    _, factory = bootstrap_database
    with pytest.raises(BootstrapError, match="does not exist"):
        execute_bootstrap(
            factory,
            **bootstrap_kwargs(create_organisation=False),
        )
