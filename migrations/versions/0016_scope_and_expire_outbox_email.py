"""Scope new participant outbox email and set a short retention expiry."""

from alembic import op
import sqlalchemy as sa


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

RETENTION_DAYS = 30


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("outbox_emails")}
    with op.batch_alter_table("outbox_emails") as batch:
        if "participant_id" not in columns:
            batch.add_column(sa.Column("participant_id", sa.Integer(), nullable=True))
        if "study_id" not in columns:
            batch.add_column(sa.Column("study_id", sa.Integer(), nullable=True))
        if "retention_expires_at" not in columns:
            batch.add_column(sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=True))
    if bind.dialect.name == "postgresql":
        op.execute(
            "UPDATE outbox_emails SET retention_expires_at = CURRENT_TIMESTAMP + INTERVAL '30 days' "
            "WHERE retention_expires_at IS NULL"
        )
    else:
        op.execute(
            "UPDATE outbox_emails SET retention_expires_at = datetime('now', '+30 days') "
            "WHERE retention_expires_at IS NULL"
        )
    with op.batch_alter_table("outbox_emails") as batch:
        batch.alter_column("retention_expires_at", nullable=False)
        batch.create_index("ix_outbox_emails_retention_expires_at", ["retention_expires_at"])
        batch.create_index("ix_outbox_emails_participant_scope", ["organisation_id", "participant_id", "study_id"])


def downgrade():
    with op.batch_alter_table("outbox_emails") as batch:
        batch.drop_index("ix_outbox_emails_participant_scope")
        batch.drop_index("ix_outbox_emails_retention_expires_at")
        batch.drop_column("retention_expires_at")
        batch.drop_column("study_id")
        batch.drop_column("participant_id")
