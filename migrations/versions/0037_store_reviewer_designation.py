"""Add explicit fictional store-reviewer designation.

Revision ID: 0037
Revises: 0036
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "participants" not in inspector.get_table_names():
        # Historical partial-schema rehearsals intentionally omit this table.
        return
    columns = {
        column["name"]
        for column in inspector.get_columns("participants")
    }
    # Revision 0001 intentionally builds fresh rehearsal databases from the
    # current ORM metadata, so the new column can already be present there.
    if "is_store_reviewer" in columns:
        return
    op.add_column(
        "participants",
        sa.Column(
            "is_store_reviewer",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "participants" not in inspector.get_table_names():
        return
    columns = {
        column["name"]
        for column in inspector.get_columns("participants")
    }
    if "is_store_reviewer" in columns:
        op.drop_column("participants", "is_store_reviewer")
