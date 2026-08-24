"""Add one-time app access codes and idempotent evidence uploads."""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "participant_app_access_codes" not in inspector.get_table_names():
        op.create_table(
            "participant_app_access_codes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organisation_id", sa.Integer(), sa.ForeignKey("organisations.id"), nullable=False),
            sa.Column("participant_invitation_id", sa.Integer(), sa.ForeignKey("participant_invitations.id"), nullable=False),
            sa.Column("code_hash", sa.String(length=255), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_participant_app_access_codes_organisation_id", "participant_app_access_codes", ["organisation_id"])
        op.create_index("ix_participant_app_access_codes_participant_invitation_id", "participant_app_access_codes", ["participant_invitation_id"])
        op.create_index("ix_participant_app_access_codes_code_hash", "participant_app_access_codes", ["code_hash"], unique=True)
        op.create_index("ix_participant_app_access_codes_expires_at", "participant_app_access_codes", ["expires_at"])
    evidence_columns = {column["name"] for column in sa.inspect(bind).get_columns("evidence_files")}
    evidence_constraints = {
        constraint["name"]
        for constraint in sa.inspect(bind).get_unique_constraints("evidence_files")
    }
    with op.batch_alter_table("evidence_files") as batch:
        if "upload_key_hash" not in evidence_columns:
            batch.add_column(sa.Column("upload_key_hash", sa.String(length=64), nullable=True))
        if "uq_evidence_participant_upload_key" not in evidence_constraints:
            batch.create_unique_constraint(
                "uq_evidence_participant_upload_key",
                ["organisation_id", "participant_id", "activity_id", "upload_key_hash"],
            )
    message_columns = {column["name"] for column in sa.inspect(bind).get_columns("participant_messages")}
    message_constraints = {
        constraint["name"]
        for constraint in sa.inspect(bind).get_unique_constraints("participant_messages")
    }
    with op.batch_alter_table("participant_messages") as batch:
        if "idempotency_key_hash" not in message_columns:
            batch.add_column(sa.Column("idempotency_key_hash", sa.String(length=64), nullable=True))
        if "uq_participant_message_client_key" not in message_constraints:
            batch.create_unique_constraint(
                "uq_participant_message_client_key",
                ["organisation_id", "participant_id", "study_id", "idempotency_key_hash"],
            )


def downgrade():
    bind = op.get_bind()
    if "participant_messages" in sa.inspect(bind).get_table_names():
        columns = {column["name"] for column in sa.inspect(bind).get_columns("participant_messages")}
        constraints = {
            constraint["name"]
            for constraint in sa.inspect(bind).get_unique_constraints("participant_messages")
        }
        with op.batch_alter_table("participant_messages") as batch:
            if "uq_participant_message_client_key" in constraints:
                batch.drop_constraint("uq_participant_message_client_key", type_="unique")
            if "idempotency_key_hash" in columns:
                batch.drop_column("idempotency_key_hash")
    if "evidence_files" in sa.inspect(bind).get_table_names():
        columns = {column["name"] for column in sa.inspect(bind).get_columns("evidence_files")}
        constraints = {
            constraint["name"]
            for constraint in sa.inspect(bind).get_unique_constraints("evidence_files")
        }
        with op.batch_alter_table("evidence_files") as batch:
            if "uq_evidence_participant_upload_key" in constraints:
                batch.drop_constraint("uq_evidence_participant_upload_key", type_="unique")
            if "upload_key_hash" in columns:
                batch.drop_column("upload_key_hash")
    if "participant_app_access_codes" in sa.inspect(bind).get_table_names():
        op.drop_table("participant_app_access_codes")
