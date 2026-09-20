"""Add researcher-led theme development and code links."""

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def _drop_guards():
    if op.get_bind().dialect.name == "postgresql":
        for trigger, table in (("trg_research_themes_scope", "research_themes"), ("trg_research_theme_codes_scope", "research_theme_codes")):
            op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
        op.execute("DROP FUNCTION IF EXISTS validate_research_theme_scope()")
        op.execute("DROP FUNCTION IF EXISTS validate_research_theme_code_scope()")
    else:
        for name in ("research_themes", "research_theme_codes"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{name}_scope_insert")
            op.execute(f"DROP TRIGGER IF EXISTS trg_{name}_scope_update")


def _create_guards():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION validate_research_theme_scope() RETURNS trigger AS $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'research theme study scope'; END IF;
        IF NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.created_by_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'research theme creator scope'; END IF;
        IF (NEW.archived_at IS NULL) <> (NEW.archived_by_id IS NULL) THEN RAISE EXCEPTION 'research theme archive pair'; END IF;
        IF NEW.archived_by_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.archived_by_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'research theme archiver scope'; END IF;
        RETURN NEW; END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_research_themes_scope BEFORE INSERT OR UPDATE ON research_themes FOR EACH ROW EXECUTE FUNCTION validate_research_theme_scope();""")
        op.execute("""CREATE FUNCTION validate_research_theme_code_scope() RETURNS trigger AS $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'theme code study scope'; END IF;
        IF NOT EXISTS (SELECT 1 FROM research_themes WHERE id=NEW.research_theme_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'theme code theme scope'; END IF;
        IF NOT EXISTS (SELECT 1 FROM research_codes WHERE id=NEW.research_code_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'theme code code scope'; END IF;
        IF NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.linked_by_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'theme code researcher scope'; END IF;
        RETURN NEW; END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_research_theme_codes_scope BEFORE INSERT OR UPDATE ON research_theme_codes FOR EACH ROW EXECUTE FUNCTION validate_research_theme_code_scope();""")
    else:
        for action in ("INSERT", "UPDATE"):
            op.execute(f"""CREATE TRIGGER trg_research_themes_scope_{action.lower()} BEFORE {action} ON research_themes BEGIN
            SELECT RAISE(ABORT,'research theme study scope') WHERE NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id);
            SELECT RAISE(ABORT,'research theme creator scope') WHERE NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.created_by_id AND organisation_id=NEW.organisation_id);
            SELECT RAISE(ABORT,'research theme archive pair') WHERE (NEW.archived_at IS NULL) <> (NEW.archived_by_id IS NULL);
            SELECT RAISE(ABORT,'research theme archiver scope') WHERE NEW.archived_by_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.archived_by_id AND organisation_id=NEW.organisation_id);
            END""")
            op.execute(f"""CREATE TRIGGER trg_research_theme_codes_scope_{action.lower()} BEFORE {action} ON research_theme_codes BEGIN
            SELECT RAISE(ABORT,'theme code study scope') WHERE NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id);
            SELECT RAISE(ABORT,'theme code theme scope') WHERE NOT EXISTS (SELECT 1 FROM research_themes WHERE id=NEW.research_theme_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
            SELECT RAISE(ABORT,'theme code code scope') WHERE NOT EXISTS (SELECT 1 FROM research_codes WHERE id=NEW.research_code_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
            SELECT RAISE(ABORT,'theme code researcher scope') WHERE NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.linked_by_id AND organisation_id=NEW.organisation_id);
            END""")


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "research_themes" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("research_themes")}
    if "archived_at" not in columns:
        op.add_column("research_themes", sa.Column("archived_at", sa.DateTime(timezone=True)))
    if "archived_by_id" not in columns:
        op.add_column("research_themes", sa.Column("archived_by_id", sa.Integer(), sa.ForeignKey("users.id")))
    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("research_themes")}
    if "ix_research_themes_archived_at" not in indexes:
        op.create_index("ix_research_themes_archived_at", "research_themes", ["archived_at"])
    if "ix_research_themes_scope" not in indexes:
        op.create_index("ix_research_themes_scope", "research_themes", ["organisation_id", "study_id", "archived_at"])
    if "research_theme_codes" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "research_theme_codes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organisation_id", sa.Integer(), sa.ForeignKey("organisations.id"), nullable=False),
            sa.Column("study_id", sa.Integer(), sa.ForeignKey("studies.id"), nullable=False),
            sa.Column("research_theme_id", sa.Integer(), sa.ForeignKey("research_themes.id"), nullable=False),
            sa.Column("research_code_id", sa.Integer(), sa.ForeignKey("research_codes.id"), nullable=False),
            sa.Column("linked_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("research_theme_id", "research_code_id", name="uq_research_theme_code"),
        )
        for name, columns in (
            ("organisation_id", ["organisation_id"]), ("study_id", ["study_id"]),
            ("research_theme_id", ["research_theme_id"]), ("research_code_id", ["research_code_id"]),
            ("linked_by_id", ["linked_by_id"]),
            ("scope", ["organisation_id", "study_id", "research_theme_id"]),
        ):
            op.create_index(f"ix_research_theme_codes_{name}", "research_theme_codes", columns)
    _drop_guards()
    _create_guards()


def downgrade():
    _drop_guards()
    bind = op.get_bind()
    tables = sa.inspect(bind).get_table_names()
    if "research_theme_codes" in tables:
        op.drop_table("research_theme_codes")
    if "research_themes" in tables:
        indexes = {index["name"] for index in sa.inspect(bind).get_indexes("research_themes")}
        if "ix_research_themes_scope" in indexes:
            op.drop_index("ix_research_themes_scope", table_name="research_themes")
        if "ix_research_themes_archived_at" in indexes:
            op.drop_index("ix_research_themes_archived_at", table_name="research_themes")
        columns = {column["name"] for column in sa.inspect(bind).get_columns("research_themes")}
        drop_columns = [name for name in ("archived_by_id", "archived_at") if name in columns]
        if bind.dialect.name == "sqlite" and drop_columns:
            dependent_triggers = bind.execute(sa.text(
                "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name <> 'research_themes' AND sql LIKE '%research_themes%'"
            )).mappings().all()
            for trigger in dependent_triggers:
                op.execute(f"DROP TRIGGER IF EXISTS {trigger['name']}")
            with op.batch_alter_table("research_themes") as batch:
                for name in drop_columns:
                    batch.drop_column(name)
            for trigger in dependent_triggers:
                op.execute(trigger["sql"])
        else:
            for name in drop_columns:
                op.drop_column("research_themes", name)
