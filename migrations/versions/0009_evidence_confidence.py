"""Add qualitative, review-gated evidence confidence assessments."""
from alembic import op
import sqlalchemy as sa

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None

def upgrade():
    if 'evidence_confidence_assessments' in sa.inspect(op.get_bind()).get_table_names(): return
    op.create_table('evidence_confidence_assessments', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('organisation_id', sa.Integer(), sa.ForeignKey('organisations.id'), nullable=False), sa.Column('study_id', sa.Integer(), sa.ForeignKey('studies.id'), nullable=False), sa.Column('focus', sa.String(200), nullable=False), sa.Column('supporting_response_ids_json', sa.Text(), nullable=False, server_default='[]'), sa.Column('contradicting_response_ids_json', sa.Text(), nullable=False, server_default='[]'), sa.Column('category', sa.String(30), nullable=False, server_default='weak'), sa.Column('explanation', sa.Text(), nullable=False, server_default=''), sa.Column('limitations_json', sa.Text(), nullable=False, server_default='[]'), sa.Column('strengthening_needs_json', sa.Text(), nullable=False, server_default='[]'), sa.Column('status', sa.String(30), nullable=False, server_default='awaiting_researcher_review'), sa.Column('reviewer_user_id', sa.Integer(), sa.ForeignKey('users.id')), sa.Column('reviewer_note', sa.Text(), nullable=False, server_default=''), sa.Column('reviewed_at', sa.DateTime(timezone=True)), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_evidence_confidence_scope', 'evidence_confidence_assessments', ['organisation_id', 'study_id'])

def downgrade():
    if 'evidence_confidence_assessments' not in sa.inspect(op.get_bind()).get_table_names(): return
    op.drop_index('ix_evidence_confidence_scope', table_name='evidence_confidence_assessments')
    op.drop_table('evidence_confidence_assessments')
