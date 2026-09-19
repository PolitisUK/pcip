"""Add passage-level researcher code applications."""
import sqlalchemy as sa
from alembic import op
revision="0027"; down_revision="0026"; branch_labels=None; depends_on=None
def upgrade():
    b=op.get_bind()
    if "code_applications" in sa.inspect(b).get_table_names(): return
    op.create_table("code_applications", sa.Column("id",sa.Integer(),primary_key=True),sa.Column("organisation_id",sa.Integer(),sa.ForeignKey("organisations.id"),nullable=False),sa.Column("study_id",sa.Integer(),sa.ForeignKey("studies.id"),nullable=False),sa.Column("analysis_target_id",sa.Integer(),sa.ForeignKey("analysis_targets.id"),nullable=False),sa.Column("research_code_id",sa.Integer(),sa.ForeignKey("research_codes.id"),nullable=False),sa.Column("applied_by_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=False),sa.Column("anchor_json",sa.Text(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")),sa.UniqueConstraint("analysis_target_id","research_code_id","applied_by_id","anchor_json",name="uq_code_application_exact"))
    op.create_index("ix_code_applications_scope","code_applications",["organisation_id","study_id","analysis_target_id"])
    for n,c in (("ix_code_applications_organisation_id",["organisation_id"]),("ix_code_applications_study_id",["study_id"]),("ix_code_applications_analysis_target_id",["analysis_target_id"]),("ix_code_applications_research_code_id",["research_code_id"]),("ix_code_applications_applied_by_id",["applied_by_id"])): op.create_index(n,"code_applications",c)
def downgrade(): op.drop_table("code_applications")
