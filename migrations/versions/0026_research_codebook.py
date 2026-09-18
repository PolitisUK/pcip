"""Add the researcher-managed qualitative codebook."""

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def _sqlite_triggers():
    for action in ("INSERT", "UPDATE"):
        op.execute(f"""
          CREATE TRIGGER trg_research_codes_scope_{action.lower()}
          BEFORE {action} ON research_codes BEGIN
            SELECT RAISE(ABORT, 'research code study is outside organisation')
            WHERE NOT EXISTS (SELECT 1 FROM studies WHERE id = NEW.study_id AND organisation_id = NEW.organisation_id);
            SELECT RAISE(ABORT, 'research code creator is outside organisation')
            WHERE NOT EXISTS (SELECT 1 FROM users WHERE id = NEW.created_by_id AND organisation_id = NEW.organisation_id);
            SELECT RAISE(ABORT, 'research code parent is outside study scope')
            WHERE NEW.parent_code_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM research_codes WHERE id = NEW.parent_code_id AND organisation_id = NEW.organisation_id AND study_id = NEW.study_id);
            SELECT RAISE(ABORT, 'research code parent is archived')
            WHERE NEW.parent_code_id IS NOT NULL AND EXISTS (SELECT 1 FROM research_codes WHERE id = NEW.parent_code_id AND archived_at IS NOT NULL);
            SELECT RAISE(ABORT, 'research code cannot be its own parent') WHERE NEW.parent_code_id = NEW.id;
            SELECT RAISE(ABORT, 'research code hierarchy is circular')
            WHERE NEW.id IS NOT NULL AND NEW.parent_code_id IS NOT NULL AND EXISTS (
              WITH RECURSIVE ancestors(id, parent_code_id) AS (
                SELECT id, parent_code_id FROM research_codes WHERE id = NEW.parent_code_id
                UNION ALL SELECT c.id, c.parent_code_id FROM research_codes c JOIN ancestors a ON c.id = a.parent_code_id WHERE a.parent_code_id IS NOT NULL
              ) SELECT 1 FROM ancestors WHERE id = NEW.id
            );
          END
        """)


def _postgres_trigger():
    op.execute("""
      CREATE FUNCTION validate_research_code_scope() RETURNS trigger AS $$
      BEGIN
        IF NOT EXISTS (SELECT 1 FROM studies WHERE id = NEW.study_id AND organisation_id = NEW.organisation_id) THEN RAISE EXCEPTION 'research code study is outside organisation'; END IF;
        IF NOT EXISTS (SELECT 1 FROM users WHERE id = NEW.created_by_id AND organisation_id = NEW.organisation_id) THEN RAISE EXCEPTION 'research code creator is outside organisation'; END IF;
        IF NEW.parent_code_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM research_codes WHERE id = NEW.parent_code_id AND organisation_id = NEW.organisation_id AND study_id = NEW.study_id) THEN RAISE EXCEPTION 'research code parent is outside study scope'; END IF;
        IF NEW.parent_code_id IS NOT NULL AND EXISTS (SELECT 1 FROM research_codes WHERE id = NEW.parent_code_id AND archived_at IS NOT NULL) THEN RAISE EXCEPTION 'research code parent is archived'; END IF;
        IF NEW.parent_code_id = NEW.id THEN RAISE EXCEPTION 'research code cannot be its own parent'; END IF;
        IF NEW.parent_code_id IS NOT NULL AND EXISTS (WITH RECURSIVE ancestors(id, parent_code_id) AS (SELECT id, parent_code_id FROM research_codes WHERE id = NEW.parent_code_id UNION ALL SELECT c.id, c.parent_code_id FROM research_codes c JOIN ancestors a ON c.id = a.parent_code_id WHERE a.parent_code_id IS NOT NULL) SELECT 1 FROM ancestors WHERE id = NEW.id) THEN RAISE EXCEPTION 'research code hierarchy is circular'; END IF;
        RETURN NEW;
      END; $$ LANGUAGE plpgsql;
      CREATE TRIGGER trg_research_codes_scope BEFORE INSERT OR UPDATE ON research_codes FOR EACH ROW EXECUTE FUNCTION validate_research_code_scope();
    """)


def _install_triggers():
    if op.get_bind().dialect.name == "postgresql": _postgres_trigger()
    else: _sqlite_triggers()


def upgrade():
    bind = op.get_bind()
    if "research_codes" in sa.inspect(bind).get_table_names():
        if bind.dialect.name == "postgresql":
            op.execute("DROP TRIGGER IF EXISTS trg_research_codes_scope ON research_codes")
            op.execute("DROP FUNCTION IF EXISTS validate_research_code_scope()")
        else:
            op.execute("DROP TRIGGER IF EXISTS trg_research_codes_scope_insert")
            op.execute("DROP TRIGGER IF EXISTS trg_research_codes_scope_update")
        _install_triggers(); return
    op.create_table("research_codes", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organisation_id", sa.Integer(), sa.ForeignKey("organisations.id"), nullable=False), sa.Column("study_id", sa.Integer(), sa.ForeignKey("studies.id"), nullable=False), sa.Column("name", sa.String(200), nullable=False), sa.Column("definition", sa.Text(), nullable=False, server_default=""), sa.Column("parent_code_id", sa.Integer(), sa.ForeignKey("research_codes.id"), nullable=True), sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True), sa.Column("archived_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")), sa.CheckConstraint("name <> ''", name="ck_research_code_name_nonblank"))
    for name, columns in (("ix_research_codes_organisation_id", ["organisation_id"]), ("ix_research_codes_study_id", ["study_id"]), ("ix_research_codes_archived_at", ["archived_at"]), ("ix_research_codes_study_parent", ["organisation_id", "study_id", "parent_code_id"]), ("ix_research_codes_study_archived", ["organisation_id", "study_id", "archived_at"])): op.create_index(name, "research_codes", columns)
    _install_triggers()


def downgrade():
    bind = op.get_bind()
    if "research_codes" not in sa.inspect(bind).get_table_names(): return
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_research_codes_scope ON research_codes"); op.execute("DROP FUNCTION IF EXISTS validate_research_code_scope()")
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_research_codes_scope_insert"); op.execute("DROP TRIGGER IF EXISTS trg_research_codes_scope_update")
    op.drop_table("research_codes")
