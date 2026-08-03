"""Add authentication hardening fields to users.

Revision ID: 0004_authentication_hardening
Revises: 0003_entra_identity
Create Date: 2026-07-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("users")}
    added_columns: list[str] = []

    with op.batch_alter_table("users") as batch:
        if "session_version" not in columns:
            batch.add_column(
                sa.Column(
                    "session_version",
                    sa.Integer(),
                    nullable=False,
                    server_default="1",
                )
            )
            added_columns.append("session_version")
        if "failed_login_count" not in columns:
            batch.add_column(
                sa.Column(
                    "failed_login_count",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                )
            )
            added_columns.append("failed_login_count")
        if "locked_until" not in columns:
            batch.add_column(
                sa.Column(
                    "locked_until",
                    sa.DateTime(timezone=True),
                    nullable=True,
                )
            )

    if added_columns:
        with op.batch_alter_table("users") as batch:
            for column_name in added_columns:
                if column_name != "locked_until":
                    batch.alter_column(column_name, server_default=None)


def downgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("users")
    }
    with op.batch_alter_table("users") as batch:
        for column_name in (
            "locked_until",
            "failed_login_count",
            "session_version",
        ):
            if column_name in columns:
                batch.drop_column(column_name)
