"""Add researcher-authored, source-linked working themes."""

from alembic import op
import sqlalchemy as sa


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    if "research_themes" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "research_themes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organisation_id", sa.Integer(), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("study_id", sa.Integer(), sa.ForeignKey("studies.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_suggestion_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(30), nullable=False, server_default="researcher_draft"),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_research_themes_scope", "research_themes", ["organisation_id", "study_id"])


def downgrade():
    if "research_themes" not in sa.inspect(op.get_bind()).get_table_names():
        return
    op.drop_index("ix_research_themes_scope", table_name="research_themes")
    op.drop_table("research_themes")
