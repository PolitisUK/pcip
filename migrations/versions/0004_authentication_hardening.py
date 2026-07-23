"""Add authentication hardening fields to users.

Revision ID: 0004_authentication_hardening
Revises: 0003_entra_identity
Create Date: 2026-07-23
"""

from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "session_version",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch.add_column(
            sa.Column(
                "failed_login_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(
            sa.Column(
                "locked_until",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )

    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "session_version",
            server_default=None,
        )
        batch.alter_column(
            "failed_login_count",
            server_default=None,
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("locked_until")
        batch.drop_column("failed_login_count")
        batch.drop_column("session_version")
