"""Bind participant invitations to immutable study consent documents."""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "study_consent_documents" not in tables:
        op.create_table(
            "study_consent_documents",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organisation_id", sa.Integer(), sa.ForeignKey("organisations.id"), nullable=False),
            sa.Column("study_id", sa.Integer(), sa.ForeignKey("studies.id"), nullable=False),
            sa.Column("document_type", sa.String(length=40), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("version", sa.String(length=80), nullable=False),
            sa.Column("reference", sa.String(length=500), nullable=False),
            sa.Column("effective_date", sa.String(length=30), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("content_sha256", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("study_id", "document_type", "content_sha256", name="uq_study_consent_document_content"),
        )
        op.create_index("ix_study_consent_documents_scope", "study_consent_documents", ["organisation_id", "study_id", "document_type"])
    if "study_consent_bundles" not in tables:
        op.create_table(
            "study_consent_bundles",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organisation_id", sa.Integer(), sa.ForeignKey("organisations.id"), nullable=False),
            sa.Column("study_id", sa.Integer(), sa.ForeignKey("studies.id"), nullable=False),
            sa.Column("bundle_sha256", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("study_id", "bundle_sha256", name="uq_study_consent_bundle_content"),
        )
        op.create_index("ix_study_consent_bundles_scope", "study_consent_bundles", ["organisation_id", "study_id"])
    if "study_consent_bundle_documents" not in tables:
        op.create_table(
            "study_consent_bundle_documents",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("bundle_id", sa.Integer(), sa.ForeignKey("study_consent_bundles.id"), nullable=False),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("study_consent_documents.id"), nullable=False),
            sa.Column("document_type", sa.String(length=40), nullable=False),
            sa.UniqueConstraint("bundle_id", "document_type", name="uq_study_consent_bundle_document_type"),
        )
    governance_columns = {column["name"] for column in sa.inspect(bind).get_columns("study_governance")}
    if "current_consent_bundle_id" not in governance_columns:
        with op.batch_alter_table("study_governance") as batch:
            batch.add_column(sa.Column("current_consent_bundle_id", sa.Integer(), sa.ForeignKey("study_consent_bundles.id"), nullable=True))
            batch.create_index("ix_study_governance_current_consent_bundle_id", ["current_consent_bundle_id"])
    invitation_columns = {column["name"] for column in sa.inspect(bind).get_columns("participant_invitations")}
    if "consent_bundle_id" not in invitation_columns:
        with op.batch_alter_table("participant_invitations") as batch:
            batch.add_column(sa.Column("consent_bundle_id", sa.Integer(), sa.ForeignKey("study_consent_bundles.id"), nullable=True))
            batch.create_index("ix_participant_invitations_consent_bundle_id", ["consent_bundle_id"])


def downgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "participant_invitations" in tables:
        columns = {column["name"] for column in sa.inspect(bind).get_columns("participant_invitations")}
        if "consent_bundle_id" in columns:
            with op.batch_alter_table("participant_invitations") as batch:
                batch.drop_index("ix_participant_invitations_consent_bundle_id")
                batch.drop_column("consent_bundle_id")
    if "study_governance" in tables:
        columns = {column["name"] for column in sa.inspect(bind).get_columns("study_governance")}
        if "current_consent_bundle_id" in columns:
            with op.batch_alter_table("study_governance") as batch:
                batch.drop_index("ix_study_governance_current_consent_bundle_id")
                batch.drop_column("current_consent_bundle_id")
    for table_name in ("study_consent_bundle_documents", "study_consent_bundles", "study_consent_documents"):
        if table_name in sa.inspect(bind).get_table_names():
            op.drop_table(table_name)
