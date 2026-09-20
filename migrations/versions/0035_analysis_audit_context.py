"""Add durable project/study context to the canonical audit trail."""

import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def _drop_guards() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_audit_events_scope ON audit_events")
        op.execute("DROP FUNCTION IF EXISTS validate_audit_event_scope()")
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_audit_events_scope_insert")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_events_scope_update")


def _create_guards() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
        CREATE FUNCTION validate_audit_event_scope() RETURNS trigger AS $$ BEGIN
          IF NEW.project_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM projects WHERE id=NEW.project_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'audit project scope'; END IF;
          IF NEW.study_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id AND (NEW.project_id IS NULL OR project_id=NEW.project_id)) THEN RAISE EXCEPTION 'audit study scope'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_audit_events_scope BEFORE INSERT OR UPDATE ON audit_events FOR EACH ROW EXECUTE FUNCTION validate_audit_event_scope();
        """)
    else:
        for action in ("INSERT", "UPDATE"):
            op.execute(f"""
            CREATE TRIGGER trg_audit_events_scope_{action.lower()} BEFORE {action} ON audit_events BEGIN
              SELECT RAISE(ABORT,'audit project scope') WHERE NEW.project_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM projects WHERE id=NEW.project_id AND organisation_id=NEW.organisation_id);
              SELECT RAISE(ABORT,'audit study scope') WHERE NEW.study_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id AND (NEW.project_id IS NULL OR project_id=NEW.project_id));
            END
            """)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "audit_events" not in tables:
        return
    columns = {column["name"] for column in inspector.get_columns("audit_events")}
    if "project_id" not in columns:
        op.add_column("audit_events", sa.Column("project_id", sa.Integer(), nullable=True))
        op.create_index("ix_audit_events_project_id", "audit_events", ["project_id"])
    if "study_id" not in columns:
        op.add_column("audit_events", sa.Column("study_id", sa.Integer(), nullable=True))
        op.create_index("ix_audit_events_study_id", "audit_events", ["study_id"])
    if {"projects", "studies"}.issubset(tables):
        _drop_guards()
        _create_guards()


def downgrade() -> None:
    # Older application revisions ignore these nullable compatibility columns.
    # Retaining them keeps SQLite deeper downgrade rehearsals safe.
    _drop_guards()
