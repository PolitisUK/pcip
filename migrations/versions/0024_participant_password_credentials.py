"""Add explicitly provisioned reusable participant app credentials.

Normal participant invitations and one-time application codes are unchanged.
The credential identifier is globally unique so password authentication can
resolve one tenant without revealing an organisation selector.
"""

import sqlalchemy as sa
from alembic import op


revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "participant_password_credentials" not in tables:
        op.create_table(
            "participant_password_credentials",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organisation_id", sa.Integer(), sa.ForeignKey("organisations.id"), nullable=False),
            sa.Column("participant_id", sa.Integer(), sa.ForeignKey("participants.id"), nullable=False),
            sa.Column("participant_invitation_id", sa.Integer(), sa.ForeignKey("participant_invitations.id"), nullable=False),
            sa.Column("login_identifier_normalised", sa.String(length=255), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("participant_invitation_id"),
            sa.UniqueConstraint("participant_id"),
            sa.UniqueConstraint("login_identifier_normalised"),
        )
        op.create_index("ix_participant_password_credentials_organisation_id", "participant_password_credentials", ["organisation_id"])
        op.create_index("ix_participant_password_credentials_participant_id", "participant_password_credentials", ["participant_id"])
        op.create_index("ix_participant_password_credentials_participant_invitation_id", "participant_password_credentials", ["participant_invitation_id"])
        op.create_index("ix_participant_password_credentials_login_identifier_normalised", "participant_password_credentials", ["login_identifier_normalised"])
        op.create_index("ix_participant_password_credentials_enabled", "participant_password_credentials", ["enabled"])
    if "public_auth_sessions" in tables:
        columns = {column["name"] for column in inspector.get_columns("public_auth_sessions")}
        if "participant_password_credential_id" not in columns:
            with op.batch_alter_table("public_auth_sessions") as batch:
                batch.add_column(
                    sa.Column(
                        "participant_password_credential_id",
                        sa.Integer(),
                        sa.ForeignKey(
                            "participant_password_credentials.id",
                            name="fk_public_auth_sessions_password_credential",
                        ),
                        nullable=True,
                    )
                )
                batch.create_index("ix_public_auth_sessions_participant_password_credential_id", ["participant_password_credential_id"])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "public_auth_sessions" in tables:
        columns = {column["name"] for column in inspector.get_columns("public_auth_sessions")}
        if "participant_password_credential_id" in columns:
            active = bind.execute(sa.text("SELECT 1 FROM public_auth_sessions WHERE participant_password_credential_id IS NOT NULL AND revoked_at IS NULL LIMIT 1")).first()
            if active:
                raise RuntimeError("Cannot downgrade 0024 while password-authenticated sessions remain active.")
            with op.batch_alter_table("public_auth_sessions") as batch:
                batch.drop_index("ix_public_auth_sessions_participant_password_credential_id")
                batch.drop_column("participant_password_credential_id")
    if "participant_password_credentials" in tables:
        op.drop_table("participant_password_credentials")
