"""Return the sole current Alembic revision through a fixed read-only query.

This is an implementation detail of the protected production-operations
worker.  It is not a database console, accepts no caller-controlled query
input, and cannot run migrations or write application data.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.db import SessionLocal


class AlembicRevisionLookupError(RuntimeError):
    """Raised when the single revision cannot be established safely."""


_REVISION_PATTERN = re.compile(r"[0-9]{4}\Z")


@dataclass(frozen=True)
class AlembicRevision:
    alembic_revision: str

    def approved_result(self) -> dict[str, str]:
        return asdict(self)


def get_alembic_revision(db: Session) -> AlembicRevision:
    """Perform the one fixed Alembic version lookup and validate its result."""
    rows = list(db.execute(text("SELECT version_num FROM alembic_version")))
    if len(rows) != 1:
        raise AlembicRevisionLookupError("Expected exactly one Alembic revision.")
    revision = rows[0][0]
    if not isinstance(revision, str) or not _REVISION_PATTERN.fullmatch(revision):
        raise AlembicRevisionLookupError("The Alembic revision is malformed.")
    if db.new or db.dirty or db.deleted:
        raise AlembicRevisionLookupError("Read-only lookup detected pending changes.")
    return AlembicRevision(alembic_revision=revision)


def execute_get_alembic_revision(
    session_factory: sessionmaker = SessionLocal,
) -> AlembicRevision:
    """Run the fixed query in a read-only transaction and always roll back."""
    db = session_factory()
    try:
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text("SET TRANSACTION READ ONLY"))
        return get_alembic_revision(db)
    finally:
        db.rollback()
        db.close()
