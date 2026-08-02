"""Enforce one active participant API session per invitation.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "public_auth_sessions" not in tables:
        return

    existing_indexes = {
        index["name"] for index in inspector.get_indexes("public_auth_sessions")
    }
    index_name = "ux_public_auth_sessions_participant_api_active_invitation"
    if index_name not in existing_indexes:
        op.create_index(
            index_name,
            "public_auth_sessions",
            ["participant_invitation_id"],
            unique=True,
            postgresql_where=sa.text(
                "scope = 'participant_api' "
                "AND revoked_at IS NULL "
                "AND participant_invitation_id IS NOT NULL"
            ),
            sqlite_where=sa.text(
                "scope = 'participant_api' "
                "AND revoked_at IS NULL "
                "AND participant_invitation_id IS NOT NULL"
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "public_auth_sessions" not in tables:
        return

    existing_indexes = {
        index["name"] for index in inspector.get_indexes("public_auth_sessions")
    }
    index_name = "ux_public_auth_sessions_participant_api_active_invitation"
    if index_name in existing_indexes:
        op.drop_index(index_name, table_name="public_auth_sessions")
