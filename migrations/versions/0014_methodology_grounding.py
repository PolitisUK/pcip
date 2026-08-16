"""Add version-pinned study methodology configuration and AI provenance."""

from alembic import op
import sqlalchemy as sa


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def _columns(bind, table):
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def upgrade():
    bind = op.get_bind()
    if "study_methodology_configurations" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "study_methodology_configurations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organisation_id", sa.Integer(), sa.ForeignKey("organisations.id"), nullable=False),
            sa.Column("study_id", sa.Integer(), sa.ForeignKey("studies.id"), nullable=False),
            sa.Column("primary_methodology_id", sa.String(length=30), nullable=False, server_default=""),
            sa.Column("methodology_variant", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("secondary_methodologies_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("research_questions", sa.Text(), nullable=False, server_default=""),
            sa.Column("protocol_reference", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("protocol_version", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("sampling_approach", sa.Text(), nullable=False, server_default=""),
            sa.Column("data_collection_plan", sa.Text(), nullable=False, server_default=""),
            sa.Column("ai_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("allowed_ai_tasks_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("human_review_required", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("library_version", sa.String(length=30), nullable=False, server_default="1.0.0"),
            sa.Column("researcher_notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("researcher_confirmed_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("researcher_confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("study_id", name="uq_study_methodology_configuration_study"),
        )
        op.create_index("ix_study_methodology_configuration_scope", "study_methodology_configurations", ["organisation_id", "study_id"])
    existing = _columns(bind, "research_analysis_suggestions")
    additions = [
        ("methodology_id", sa.String(length=30), ""), ("methodology_variant", sa.String(length=80), ""),
        ("methodology_library_version", sa.String(length=30), ""), ("methodology_rule_references_json", sa.Text(), "[]"),
        ("protocol_version", sa.String(length=80), ""), ("evidence_item_ids_json", sa.Text(), "[]"),
        ("model_provider", sa.String(length=80), ""), ("model_deployment", sa.String(length=120), ""),
        ("prompt_template_version", sa.String(length=80), "research-analysis-v1"),
    ]
    with op.batch_alter_table("research_analysis_suggestions") as batch:
        for name, column_type, default in additions:
            if name not in existing:
                batch.add_column(sa.Column(name, column_type, nullable=False, server_default=default))
        if "human_review_required" not in existing:
            batch.add_column(sa.Column("human_review_required", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    bind = op.get_bind()
    if "study_methodology_configurations" in sa.inspect(bind).get_table_names():
        op.drop_index("ix_study_methodology_configuration_scope", table_name="study_methodology_configurations")
        op.drop_table("study_methodology_configurations")
    existing = _columns(bind, "research_analysis_suggestions")
    names = ["methodology_id", "methodology_variant", "methodology_library_version", "methodology_rule_references_json", "protocol_version", "evidence_item_ids_json", "model_provider", "model_deployment", "prompt_template_version", "human_review_required"]
    with op.batch_alter_table("research_analysis_suggestions") as batch:
        for name in names:
            if name in existing:
                batch.drop_column(name)
