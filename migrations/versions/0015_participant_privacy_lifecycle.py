"""Add participant withdrawal/deletion lifecycle evidence."""

from alembic import op
import sqlalchemy as sa


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    governance_columns = {column["name"] for column in sa.inspect(bind).get_columns("study_governance")}
    if "deletion_retention_exception" not in governance_columns:
        with op.batch_alter_table("study_governance") as batch:
            batch.add_column(sa.Column("deletion_retention_exception", sa.Text(), nullable=False, server_default=""))
    if "participant_privacy_requests" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "participant_privacy_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organisation_id", sa.Integer(), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("participant_id", sa.Integer(), sa.ForeignKey("participants.id"), nullable=True),
        sa.Column("study_id", sa.Integer(), sa.ForeignKey("studies.id"), nullable=True),
        sa.Column("request_type", sa.String(30), nullable=False),
        sa.Column("scope", sa.String(30), nullable=False, server_default="study"),
        sa.Column("status", sa.String(40), nullable=False, server_default="received"),
        sa.Column("retriable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("categories_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("retention_exceptions_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(80), nullable=False, server_default=""),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_participant_privacy_request_scope",
        "participant_privacy_requests",
        ["organisation_id", "study_id", "status"],
    )


def downgrade():
    bind = op.get_bind()
    if "participant_privacy_requests" in sa.inspect(bind).get_table_names():
        op.drop_index("ix_participant_privacy_request_scope", table_name="participant_privacy_requests")
        op.drop_table("participant_privacy_requests")
    governance_columns = {column["name"] for column in sa.inspect(bind).get_columns("study_governance")}
    if "deletion_retention_exception" in governance_columns:
        with op.batch_alter_table("study_governance") as batch:
            batch.drop_column("deletion_retention_exception")
