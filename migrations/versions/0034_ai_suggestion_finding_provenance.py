"""Add explicit AI-suggestion provenance to researcher findings."""

import importlib

import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def _drop_guard() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_research_findings_scope ON research_findings")
        op.execute("DROP FUNCTION IF EXISTS validate_research_finding_scope()")
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_research_findings_scope_insert")
        op.execute("DROP TRIGGER IF EXISTS trg_research_findings_scope_update")


def _create_guard(*, provenance: bool) -> None:
    origin_postgres = ""
    origin_sqlite = ""
    if provenance:
        origin_postgres = """
          IF NEW.originating_suggestion_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM research_analysis_suggestions
            WHERE id=NEW.originating_suggestion_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id
          ) THEN RAISE EXCEPTION 'research finding suggestion scope'; END IF;
        """
        origin_sqlite = """
          SELECT RAISE(ABORT,'research finding suggestion scope')
          WHERE NEW.originating_suggestion_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM research_analysis_suggestions
            WHERE id=NEW.originating_suggestion_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id
          );
        """
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"""
        CREATE FUNCTION validate_research_finding_scope() RETURNS trigger AS $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'research finding study scope'; END IF;
          IF NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.created_by_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'research finding creator scope'; END IF;
          IF NEW.archived_by_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.archived_by_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'research finding archiver scope'; END IF;
          {origin_postgres}
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_research_findings_scope BEFORE INSERT OR UPDATE ON research_findings FOR EACH ROW EXECUTE FUNCTION validate_research_finding_scope();
        """)
    else:
        for action in ("INSERT", "UPDATE"):
            op.execute(f"""
            CREATE TRIGGER trg_research_findings_scope_{action.lower()} BEFORE {action} ON research_findings BEGIN
              SELECT RAISE(ABORT,'research finding study scope') WHERE NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id);
              SELECT RAISE(ABORT,'research finding creator scope') WHERE NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.created_by_id AND organisation_id=NEW.organisation_id);
              SELECT RAISE(ABORT,'research finding archiver scope') WHERE NEW.archived_by_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.archived_by_id AND organisation_id=NEW.organisation_id);
              {origin_sqlite}
            END
            """)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    columns = {column["name"] for column in inspector.get_columns("research_findings")}
    complete_schema = {"organisations", "studies", "users", "research_analysis_suggestions"}.issubset(tables)
    index_created = False
    if "originating_suggestion_id" not in columns and complete_schema and op.get_bind().dialect.name == "sqlite":
        prior = importlib.import_module("migrations.versions.0033_research_findings")
        prior._drop_guards()
        with op.batch_alter_table("research_findings") as batch:
            batch.add_column(sa.Column("originating_suggestion_id", sa.Integer(), nullable=True))
            batch.create_foreign_key(
                "fk_research_findings_originating_suggestion",
                "research_analysis_suggestions",
                ["originating_suggestion_id"],
                ["id"],
            )
            batch.create_index(
                "ix_research_findings_originating_suggestion_id",
                ["originating_suggestion_id"],
                unique=True,
            )
        prior._create_guards()
        index_created = True
    elif "originating_suggestion_id" not in columns:
        op.add_column("research_findings", sa.Column("originating_suggestion_id", sa.Integer(), nullable=True))
        if complete_schema and op.get_bind().dialect.name == "postgresql":
            op.create_foreign_key(
                "fk_research_findings_originating_suggestion",
                "research_findings",
                "research_analysis_suggestions",
                ["originating_suggestion_id"],
                ["id"],
            )
    indexes = {index["name"] for index in inspector.get_indexes("research_findings")}
    if not index_created and "ix_research_findings_originating_suggestion_id" not in indexes:
        op.create_index(
            "ix_research_findings_originating_suggestion_id",
            "research_findings",
            ["originating_suggestion_id"],
            unique=True,
        )
    if complete_schema:
        _drop_guard()
        _create_guard(provenance=True)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    complete_schema = {"organisations", "studies", "users", "research_analysis_suggestions"}.issubset(tables)
    if complete_schema:
        _drop_guard()
    indexes = {index["name"] for index in inspector.get_indexes("research_findings")}
    if "ix_research_findings_originating_suggestion_id" in indexes:
        op.drop_index("ix_research_findings_originating_suggestion_id", table_name="research_findings")
    # Retain the nullable compatibility column. SQLite cannot safely drop it
    # when a fresh schema supplied an inline foreign key; migration 0033 drops
    # the entire findings table on a deeper downgrade.
    if complete_schema:
        _create_guard(provenance=False)
