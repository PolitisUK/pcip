"""Add review-gated, source-traceable research analysis suggestions."""
from alembic import op
import sqlalchemy as sa
revision='0008'; down_revision='0007'; branch_labels=None; depends_on=None
def upgrade():
 if 'research_analysis_suggestions' in sa.inspect(op.get_bind()).get_table_names():
  return
 op.create_table('research_analysis_suggestions',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('organisation_id',sa.Integer(),sa.ForeignKey('organisations.id'),nullable=False),sa.Column('study_id',sa.Integer(),sa.ForeignKey('studies.id'),nullable=False),sa.Column('source_response_id',sa.Integer(),sa.ForeignKey('activity_responses.id'),nullable=False),sa.Column('source_snapshot',sa.Text(),nullable=False),sa.Column('suggested_codes_json',sa.Text(),nullable=False,server_default='[]'),sa.Column('provisional_insight',sa.Text(),nullable=False,server_default=''),sa.Column('confidence',sa.Float(),nullable=False,server_default='0'),sa.Column('status',sa.String(30),nullable=False,server_default='awaiting_researcher_review'),sa.Column('reviewer_user_id',sa.Integer(),sa.ForeignKey('users.id')),sa.Column('reviewer_note',sa.Text(),nullable=False,server_default=''),sa.Column('reviewed_at',sa.DateTime(timezone=True)),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
 op.create_index('ix_research_analysis_suggestions_scope','research_analysis_suggestions',['organisation_id','study_id'])
def downgrade():
 if 'research_analysis_suggestions' not in sa.inspect(op.get_bind()).get_table_names(): return
 op.drop_index('ix_research_analysis_suggestions_scope',table_name='research_analysis_suggestions'); op.drop_table('research_analysis_suggestions')
