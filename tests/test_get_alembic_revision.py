from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from scripts.get_alembic_revision import (
    AlembicRevisionLookupError,
    execute_get_alembic_revision,
)


def revision_session_factory(rows: list[object]):
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num TEXT)"))
        for row in rows:
            connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
                {"revision": row},
            )
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def test_fixed_lookup_returns_only_one_valid_revision():
    result = execute_get_alembic_revision(revision_session_factory(["0023"]))

    assert result.approved_result() == {"alembic_revision": "0023"}


@pytest.mark.parametrize("rows", [[], ["0023", "0024"], ["head"], [None], [23]])
def test_fixed_lookup_fails_closed_for_missing_multiple_or_malformed_revisions(rows):
    with pytest.raises(AlembicRevisionLookupError):
        execute_get_alembic_revision(revision_session_factory(rows))


def test_fixed_lookup_uses_no_caller_controlled_query_input(monkeypatch):
    captured: list[str] = []
    factory = revision_session_factory(["0023"])
    session = factory()
    original_execute = session.execute

    def execute(statement, *args, **kwargs):
        captured.append(str(statement))
        return original_execute(statement, *args, **kwargs)

    monkeypatch.setattr(session, "execute", execute)
    result = execute_get_alembic_revision(lambda: session)

    assert result.approved_result() == {"alembic_revision": "0023"}
    assert captured == ["SELECT version_num FROM alembic_version"]
