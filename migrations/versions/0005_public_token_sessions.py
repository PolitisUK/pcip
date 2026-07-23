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
    op.create_table(
        "public_token_exchanges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=60), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "token_hash"),
    )
    op.create_index(
        "ix_public_token_exchanges_scope",
        "public_token_exchanges",
        ["scope"],
        unique=False,
    )
    op.create_index(
        "ix_public_token_exchanges_token_hash",
        "public_token_exchanges",
        ["token_hash"],
        unique=False,
    )

    op.create_table(
        "public_auth_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=60), nullable=False),
        sa.Column("session_hash", sa.String(length=255), nullable=False),
        sa.Column("password_reset_id", sa.Integer(), nullable=True),
        sa.Column("invitation_id", sa.Integer(), nullable=True),
        sa.Column("participant_invitation_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["invitation_id"], ["invitations.id"]),
        sa.ForeignKeyConstraint(["participant_invitation_id"], ["participant_invitations.id"]),
        sa.ForeignKeyConstraint(["password_reset_id"], ["password_resets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_public_auth_sessions_scope",
        "public_auth_sessions",
        ["scope"],
        unique=False,
    )
    op.create_index(
        "ix_public_auth_sessions_session_hash",
        "public_auth_sessions",
        ["session_hash"],
        unique=True,
    )
    op.create_index(
        "ix_public_auth_sessions_password_reset_id",
        "public_auth_sessions",
        ["password_reset_id"],
        unique=False,
    )
    op.create_index(
        "ix_public_auth_sessions_invitation_id",
        "public_auth_sessions",
        ["invitation_id"],
        unique=False,
    )
    op.create_index(
        "ix_public_auth_sessions_participant_invitation_id",
        "public_auth_sessions",
        ["participant_invitation_id"],
        unique=False,
    )
    op.create_index(
        "ix_public_auth_sessions_expires_at",
        "public_auth_sessions",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_public_auth_sessions_expires_at", table_name="public_auth_sessions")
    op.drop_index("ix_public_auth_sessions_participant_invitation_id", table_name="public_auth_sessions")
    op.drop_index("ix_public_auth_sessions_invitation_id", table_name="public_auth_sessions")
    op.drop_index("ix_public_auth_sessions_password_reset_id", table_name="public_auth_sessions")
    op.drop_index("ix_public_auth_sessions_session_hash", table_name="public_auth_sessions")
    op.drop_index("ix_public_auth_sessions_scope", table_name="public_auth_sessions")
    op.drop_table("public_auth_sessions")

    op.drop_index("ix_public_token_exchanges_token_hash", table_name="public_token_exchanges")
    op.drop_index("ix_public_token_exchanges_scope", table_name="public_token_exchanges")
    op.drop_table("public_token_exchanges")
