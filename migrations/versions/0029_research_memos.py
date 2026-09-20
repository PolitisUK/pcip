"""Add scoped researcher analytical memos."""

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

SCOPE_CHECK = "(scope_type = 'study' AND participant_id IS NULL AND activity_response_id IS NULL AND analysis_target_id IS NULL AND research_code_id IS NULL AND research_theme_id IS NULL) OR (scope_type = 'participant' AND participant_id IS NOT NULL AND activity_response_id IS NULL AND analysis_target_id IS NULL AND research_code_id IS NULL AND research_theme_id IS NULL) OR (scope_type = 'response' AND participant_id IS NULL AND activity_response_id IS NOT NULL AND analysis_target_id IS NULL AND research_code_id IS NULL AND research_theme_id IS NULL) OR (scope_type = 'analysis_target' AND participant_id IS NULL AND activity_response_id IS NULL AND analysis_target_id IS NOT NULL AND research_code_id IS NULL AND research_theme_id IS NULL) OR (scope_type = 'code' AND participant_id IS NULL AND activity_response_id IS NULL AND analysis_target_id IS NULL AND research_code_id IS NOT NULL AND research_theme_id IS NULL) OR (scope_type = 'theme' AND participant_id IS NULL AND activity_response_id IS NULL AND analysis_target_id IS NULL AND research_code_id IS NULL AND research_theme_id IS NOT NULL)"


def _drop_guards():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_research_memos_scope ON research_memos")
        op.execute("DROP FUNCTION IF EXISTS validate_research_memo_scope()")
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_research_memos_scope_insert")
        op.execute("DROP TRIGGER IF EXISTS trg_research_memos_scope_update")


def _create_guards():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION validate_research_memo_scope() RETURNS trigger AS $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'research memo study scope'; END IF;
        IF NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.author_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'research memo author scope'; END IF;
        IF NEW.archived_by_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.archived_by_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'research memo archiver scope'; END IF;
        IF NEW.participant_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM participants p JOIN study_enrolments e ON e.participant_id=p.id WHERE p.id=NEW.participant_id AND p.organisation_id=NEW.organisation_id AND e.organisation_id=NEW.organisation_id AND e.study_id=NEW.study_id) THEN RAISE EXCEPTION 'research memo participant scope'; END IF;
        IF NEW.activity_response_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM activity_responses WHERE id=NEW.activity_response_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'research memo response scope'; END IF;
        IF NEW.analysis_target_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM analysis_targets WHERE id=NEW.analysis_target_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'research memo target scope'; END IF;
        IF NEW.research_code_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM research_codes WHERE id=NEW.research_code_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'research memo code scope'; END IF;
        IF NEW.research_theme_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM research_themes WHERE id=NEW.research_theme_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'research memo theme scope'; END IF;
        RETURN NEW; END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_research_memos_scope BEFORE INSERT OR UPDATE ON research_memos FOR EACH ROW EXECUTE FUNCTION validate_research_memo_scope();""")
    else:
        for action in ("INSERT", "UPDATE"):
            op.execute(f"""CREATE TRIGGER trg_research_memos_scope_{action.lower()} BEFORE {action} ON research_memos BEGIN
            SELECT RAISE(ABORT,'research memo study scope') WHERE NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id);
            SELECT RAISE(ABORT,'research memo author scope') WHERE NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.author_id AND organisation_id=NEW.organisation_id);
            SELECT RAISE(ABORT,'research memo archiver scope') WHERE NEW.archived_by_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.archived_by_id AND organisation_id=NEW.organisation_id);
            SELECT RAISE(ABORT,'research memo participant scope') WHERE NEW.participant_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM participants p JOIN study_enrolments e ON e.participant_id=p.id WHERE p.id=NEW.participant_id AND p.organisation_id=NEW.organisation_id AND e.organisation_id=NEW.organisation_id AND e.study_id=NEW.study_id);
            SELECT RAISE(ABORT,'research memo response scope') WHERE NEW.activity_response_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM activity_responses WHERE id=NEW.activity_response_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
            SELECT RAISE(ABORT,'research memo target scope') WHERE NEW.analysis_target_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM analysis_targets WHERE id=NEW.analysis_target_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
            SELECT RAISE(ABORT,'research memo code scope') WHERE NEW.research_code_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM research_codes WHERE id=NEW.research_code_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
            SELECT RAISE(ABORT,'research memo theme scope') WHERE NEW.research_theme_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM research_themes WHERE id=NEW.research_theme_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
            END""")


def upgrade():
    bind = op.get_bind()
    if "research_memos" not in sa.inspect(bind).get_table_names():
        op.create_table("research_memos",
            sa.Column("id",sa.Integer(),primary_key=True), sa.Column("organisation_id",sa.Integer(),sa.ForeignKey("organisations.id"),nullable=False), sa.Column("study_id",sa.Integer(),sa.ForeignKey("studies.id"),nullable=False), sa.Column("scope_type",sa.String(30),nullable=False),
            sa.Column("participant_id",sa.Integer(),sa.ForeignKey("participants.id")), sa.Column("activity_response_id",sa.Integer(),sa.ForeignKey("activity_responses.id")), sa.Column("analysis_target_id",sa.Integer(),sa.ForeignKey("analysis_targets.id")), sa.Column("research_code_id",sa.Integer(),sa.ForeignKey("research_codes.id")), sa.Column("research_theme_id",sa.Integer(),sa.ForeignKey("research_themes.id")),
            sa.Column("title",sa.String(200),nullable=False), sa.Column("body",sa.Text(),nullable=False), sa.Column("author_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=False), sa.Column("archived_at",sa.DateTime(timezone=True)), sa.Column("archived_by_id",sa.Integer(),sa.ForeignKey("users.id")), sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")), sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")), sa.CheckConstraint(SCOPE_CHECK,name="ck_research_memo_one_scope"), sa.CheckConstraint("(archived_at IS NULL) = (archived_by_id IS NULL)",name="ck_research_memo_archive_pair"))
        op.create_index("ix_research_memos_scope","research_memos",["organisation_id","study_id","scope_type"])
        for name,col in (("organisation_id","organisation_id"),("study_id","study_id"),("scope_type","scope_type"),("participant_id","participant_id"),("activity_response_id","activity_response_id"),("analysis_target_id","analysis_target_id"),("research_code_id","research_code_id"),("research_theme_id","research_theme_id"),("author_id","author_id"),("archived_at","archived_at")):
            op.create_index(f"ix_research_memos_{name}","research_memos",[col])
    _drop_guards(); _create_guards()


def downgrade():
    _drop_guards(); op.drop_table("research_memos")
