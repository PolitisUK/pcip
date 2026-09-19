"""Add passage-level researcher code applications."""
import sqlalchemy as sa
from alembic import op
revision="0027"; down_revision="0026"; branch_labels=None; depends_on=None
def _triggers():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION validate_code_application_scope() RETURNS trigger AS $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'code application study scope'; END IF;
        IF NOT EXISTS (SELECT 1 FROM analysis_targets WHERE id=NEW.analysis_target_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'code application target scope'; END IF;
        IF NOT EXISTS (SELECT 1 FROM research_codes WHERE id=NEW.research_code_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'code application code scope'; END IF;
        IF NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.applied_by_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'code application researcher scope'; END IF;
        IF TG_OP='INSERT' AND EXISTS (SELECT 1 FROM research_codes WHERE id=NEW.research_code_id AND archived_at IS NOT NULL) THEN RAISE EXCEPTION 'code application code archived'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql; CREATE TRIGGER trg_code_applications_scope BEFORE INSERT OR UPDATE ON code_applications FOR EACH ROW EXECUTE FUNCTION validate_code_application_scope();""")
    else:
        for action in ("INSERT","UPDATE"):
            archived = " AND EXISTS (SELECT 1 FROM research_codes WHERE id=NEW.research_code_id AND archived_at IS NOT NULL)" if action == "INSERT" else " AND 0"
            op.execute(f"""CREATE TRIGGER trg_code_applications_scope_{action.lower()} BEFORE {action} ON code_applications BEGIN
            SELECT RAISE(ABORT,'code application study scope') WHERE NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id);
            SELECT RAISE(ABORT,'code application target scope') WHERE NOT EXISTS (SELECT 1 FROM analysis_targets WHERE id=NEW.analysis_target_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
            SELECT RAISE(ABORT,'code application code scope') WHERE NOT EXISTS (SELECT 1 FROM research_codes WHERE id=NEW.research_code_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
            SELECT RAISE(ABORT,'code application researcher scope') WHERE NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.applied_by_id AND organisation_id=NEW.organisation_id);
            SELECT RAISE(ABORT,'code application code archived') WHERE 1=1 {archived}; END""")
def upgrade():
    b=op.get_bind()
    if "code_applications" in sa.inspect(b).get_table_names():
        if b.dialect.name == "postgresql": op.execute("DROP TRIGGER IF EXISTS trg_code_applications_scope ON code_applications"); op.execute("DROP FUNCTION IF EXISTS validate_code_application_scope()")
        else: op.execute("DROP TRIGGER IF EXISTS trg_code_applications_scope_insert"); op.execute("DROP TRIGGER IF EXISTS trg_code_applications_scope_update")
        _triggers(); return
    op.create_table("code_applications", sa.Column("id",sa.Integer(),primary_key=True),sa.Column("organisation_id",sa.Integer(),sa.ForeignKey("organisations.id"),nullable=False),sa.Column("study_id",sa.Integer(),sa.ForeignKey("studies.id"),nullable=False),sa.Column("analysis_target_id",sa.Integer(),sa.ForeignKey("analysis_targets.id"),nullable=False),sa.Column("research_code_id",sa.Integer(),sa.ForeignKey("research_codes.id"),nullable=False),sa.Column("applied_by_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=False),sa.Column("anchor_json",sa.Text(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")),sa.UniqueConstraint("analysis_target_id","research_code_id","applied_by_id","anchor_json",name="uq_code_application_exact"))
    op.create_index("ix_code_applications_scope","code_applications",["organisation_id","study_id","analysis_target_id"])
    for n,c in (("ix_code_applications_organisation_id",["organisation_id"]),("ix_code_applications_study_id",["study_id"]),("ix_code_applications_analysis_target_id",["analysis_target_id"]),("ix_code_applications_research_code_id",["research_code_id"]),("ix_code_applications_applied_by_id",["applied_by_id"])): op.create_index(n,"code_applications",c)
    _triggers()
def downgrade(): op.drop_table("code_applications")
