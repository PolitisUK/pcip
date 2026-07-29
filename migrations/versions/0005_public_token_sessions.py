"""Add public token exchange tracking and server-side public auth sessions.

Revision ID: 0005_public_token_sessions
Revises: 0004_authentication_hardening
Create Date: 2026-07-23
"""

from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())

    if "public_token_exchanges" not in tables:
        op.create_table(
            "public_token_exchanges",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("scope", sa.String(length=60), nullable=False),
            sa.Column("token_hash", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("scope", "token_hash"),
        )
    token_indexes = {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes(
            "public_token_exchanges"
        )
    }
    if "ix_public_token_exchanges_scope" not in token_indexes:
        op.create_index(
            "ix_public_token_exchanges_scope",
            "public_token_exchanges",
            ["scope"],
            unique=False,
        )
    if "ix_public_token_exchanges_token_hash" not in token_indexes:
        op.create_index(
            "ix_public_token_exchanges_token_hash",
            "public_token_exchanges",
            ["token_hash"],
            unique=False,
        )

    if "public_auth_sessions" not in tables:
        op.create_table(
            "public_auth_sessions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("scope", sa.String(length=60), nullable=False),
            sa.Column("session_hash", sa.String(length=255), nullable=False),
            sa.Column("password_reset_id", sa.Integer(), nullable=True),
            sa.Column("invitation_id", sa.Integer(), nullable=True),
            sa.Column(
                "participant_invitation_id",
                sa.Integer(),
                nullable=True,
            ),
            sa.Column(
                "expires_at",
                sa.DateTime(timezone=True),
                nullable=False,
            ),
            sa.Column(
                "revoked_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["invitation_id"],
                ["invitations.id"],
            ),
            sa.ForeignKeyConstraint(
                ["participant_invitation_id"],
                ["participant_invitations.id"],
            ),
            sa.ForeignKeyConstraint(
                ["password_reset_id"],
                ["password_resets.id"],
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    session_indexes = {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes(
            "public_auth_sessions"
        )
    }
    for index_name, columns, unique in (
        ("ix_public_auth_sessions_scope", ["scope"], False),
        ("ix_public_auth_sessions_session_hash", ["session_hash"], True),
        (
            "ix_public_auth_sessions_password_reset_id",
            ["password_reset_id"],
            False,
        ),
        (
            "ix_public_auth_sessions_invitation_id",
            ["invitation_id"],
            False,
        ),
        (
            "ix_public_auth_sessions_participant_invitation_id",
            ["participant_invitation_id"],
            False,
        ),
        ("ix_public_auth_sessions_expires_at", ["expires_at"], False),
    ):
        if index_name not in session_indexes:
            op.create_index(
                index_name,
                "public_auth_sessions",
                columns,
                unique=unique,
            )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "public_auth_sessions" in tables:
        op.drop_table("public_auth_sessions")
    if "public_token_exchanges" in tables:
        op.drop_table("public_token_exchanges")
