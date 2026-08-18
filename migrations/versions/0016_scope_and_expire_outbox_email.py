"""Scope new participant outbox email and set a short retention expiry."""

import sqlalchemy as sa
from alembic import op

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
    # Migration 0001 creates the current SQLAlchemy metadata in an empty
    # database, so these indexes may already exist there.  Existing
    # installations at 0015 need them created by this migration.
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("outbox_emails")}
    if "ix_outbox_emails_retention_expires_at" not in indexes:
        op.create_index("ix_outbox_emails_retention_expires_at", "outbox_emails", ["retention_expires_at"])
    if "ix_outbox_emails_participant_scope" not in indexes:
        op.create_index(
            "ix_outbox_emails_participant_scope",
            "outbox_emails",
            ["organisation_id", "participant_id", "study_id"],
        )


def downgrade():
    with op.batch_alter_table("outbox_emails") as batch:
        batch.drop_index("ix_outbox_emails_participant_scope")
        batch.drop_index("ix_outbox_emails_retention_expires_at")
        batch.drop_column("retention_expires_at")
        batch.drop_column("study_id")
        batch.drop_column("participant_id")
