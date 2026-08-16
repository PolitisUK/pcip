"""Add controller-supplied study governance and launch-readiness data."""

from alembic import op
import sqlalchemy as sa


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    if "study_governance" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "study_governance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organisation_id", sa.Integer(), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("study_id", sa.Integer(), sa.ForeignKey("studies.id"), nullable=False),
        sa.Column("controller_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("controller_privacy_contact", sa.String(255), nullable=False, server_default=""),
        sa.Column("sponsor_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("research_contact", sa.String(255), nullable=False, server_default=""),
        sa.Column("participant_population", sa.Text(), nullable=False, server_default=""),
        sa.Column("data_categories", sa.Text(), nullable=False, server_default=""),
        sa.Column("special_category_data", sa.String(30), nullable=False, server_default="not_assessed"),
        sa.Column("article_6_lawful_basis", sa.Text(), nullable=False, server_default=""),
        sa.Column("article_9_condition", sa.Text(), nullable=False, server_default=""),
        sa.Column("participation_consent_configured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("participant_information_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("privacy_information_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("retention_description", sa.Text(), nullable=False, server_default=""),
        sa.Column("withdrawal_process_defined", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deletion_handling_defined", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("features_assessed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enabled_features_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("ai_features_disclosed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("international_transfer_assessment", sa.String(30), nullable=False, server_default="not_assessed"),
        sa.Column("ethics_status", sa.String(30), nullable=False, server_default="not_assessed"),
        sa.Column("dpia_status", sa.String(30), nullable=False, server_default="not_assessed"),
        sa.Column("security_considerations", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("study_id", name="uq_study_governance_study"),
    )
    op.create_index("ix_study_governance_scope", "study_governance", ["organisation_id", "study_id"])


def downgrade():
    if "study_governance" not in sa.inspect(op.get_bind()).get_table_names():
        return
    op.drop_index("ix_study_governance_scope", table_name="study_governance")
    op.drop_table("study_governance")
