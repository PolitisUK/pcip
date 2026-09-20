"""Add researcher-scoped visual analysis canvas layouts."""

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def _drop_guards():
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_analysis_canvases_scope ON analysis_canvases"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_analysis_canvas_nodes_scope ON analysis_canvas_nodes"
        )
        op.execute("DROP FUNCTION IF EXISTS validate_analysis_canvas_scope()")
        op.execute("DROP FUNCTION IF EXISTS validate_analysis_canvas_node_scope()")
    else:
        for table in ("analysis_canvases", "analysis_canvas_nodes"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_scope_insert")
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_scope_update")


def _create_guards():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
        CREATE FUNCTION validate_analysis_canvas_scope() RETURNS trigger AS $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'analysis canvas study scope'; END IF;
          IF NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.owner_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'analysis canvas owner scope'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_analysis_canvases_scope BEFORE INSERT OR UPDATE ON analysis_canvases FOR EACH ROW EXECUTE FUNCTION validate_analysis_canvas_scope();
        """)
        op.execute("""
        CREATE FUNCTION validate_analysis_canvas_node_scope() RETURNS trigger AS $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM analysis_canvases WHERE id=NEW.canvas_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id AND owner_id=NEW.added_by_id) THEN RAISE EXCEPTION 'analysis canvas node canvas scope'; END IF;
          IF NEW.object_type='analysis_target' AND NOT EXISTS (SELECT 1 FROM analysis_targets WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'analysis canvas target scope'; END IF;
          IF NEW.object_type='code_application' AND NOT EXISTS (SELECT 1 FROM code_applications WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'analysis canvas application scope'; END IF;
          IF NEW.object_type='annotation' AND NOT EXISTS (SELECT 1 FROM research_annotations WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'analysis canvas annotation scope'; END IF;
          IF NEW.object_type='memo' AND NOT EXISTS (SELECT 1 FROM research_memos WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'analysis canvas memo scope'; END IF;
          IF NEW.object_type='code' AND NOT EXISTS (SELECT 1 FROM research_codes WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'analysis canvas code scope'; END IF;
          IF NEW.object_type='theme' AND NOT EXISTS (SELECT 1 FROM research_themes WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'analysis canvas theme scope'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_analysis_canvas_nodes_scope BEFORE INSERT OR UPDATE ON analysis_canvas_nodes FOR EACH ROW EXECUTE FUNCTION validate_analysis_canvas_node_scope();
        """)
    else:
        object_checks = """
          SELECT RAISE(ABORT,'analysis canvas target scope') WHERE NEW.object_type='analysis_target' AND NOT EXISTS (SELECT 1 FROM analysis_targets WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
          SELECT RAISE(ABORT,'analysis canvas application scope') WHERE NEW.object_type='code_application' AND NOT EXISTS (SELECT 1 FROM code_applications WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
          SELECT RAISE(ABORT,'analysis canvas annotation scope') WHERE NEW.object_type='annotation' AND NOT EXISTS (SELECT 1 FROM research_annotations WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
          SELECT RAISE(ABORT,'analysis canvas memo scope') WHERE NEW.object_type='memo' AND NOT EXISTS (SELECT 1 FROM research_memos WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
          SELECT RAISE(ABORT,'analysis canvas code scope') WHERE NEW.object_type='code' AND NOT EXISTS (SELECT 1 FROM research_codes WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
          SELECT RAISE(ABORT,'analysis canvas theme scope') WHERE NEW.object_type='theme' AND NOT EXISTS (SELECT 1 FROM research_themes WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
        """
        for action in ("INSERT", "UPDATE"):
            suffix = action.lower()
            op.execute(f"""
            CREATE TRIGGER trg_analysis_canvases_scope_{suffix} BEFORE {action} ON analysis_canvases BEGIN
              SELECT RAISE(ABORT,'analysis canvas study scope') WHERE NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id);
              SELECT RAISE(ABORT,'analysis canvas owner scope') WHERE NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.owner_id AND organisation_id=NEW.organisation_id);
            END
            """)
            op.execute(f"""
            CREATE TRIGGER trg_analysis_canvas_nodes_scope_{suffix} BEFORE {action} ON analysis_canvas_nodes BEGIN
              SELECT RAISE(ABORT,'analysis canvas node canvas scope') WHERE NOT EXISTS (SELECT 1 FROM analysis_canvases WHERE id=NEW.canvas_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id AND owner_id=NEW.added_by_id);
              {object_checks}
            END
            """)


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "analysis_canvases" not in tables:
        op.create_table(
            "analysis_canvases",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "organisation_id",
                sa.Integer(),
                sa.ForeignKey("organisations.id"),
                nullable=False,
            ),
            sa.Column(
                "study_id", sa.Integer(), sa.ForeignKey("studies.id"), nullable=False
            ),
            sa.Column(
                "owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
            ),
            sa.Column(
                "view_metadata_json", sa.Text(), nullable=False, server_default="{}"
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.UniqueConstraint(
                "organisation_id",
                "study_id",
                "owner_id",
                name="uq_analysis_canvas_owner_study",
            ),
        )
        for name, columns in (
            ("organisation_id", ["organisation_id"]),
            ("study_id", ["study_id"]),
            ("owner_id", ["owner_id"]),
            ("scope", ["organisation_id", "study_id", "owner_id"]),
        ):
            op.create_index(
                f"ix_analysis_canvases_{name}", "analysis_canvases", columns
            )
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "analysis_canvas_nodes" not in tables:
        op.create_table(
            "analysis_canvas_nodes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "organisation_id",
                sa.Integer(),
                sa.ForeignKey("organisations.id"),
                nullable=False,
            ),
            sa.Column(
                "study_id", sa.Integer(), sa.ForeignKey("studies.id"), nullable=False
            ),
            sa.Column(
                "canvas_id",
                sa.Integer(),
                sa.ForeignKey("analysis_canvases.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("object_type", sa.String(40), nullable=False),
            sa.Column("object_id", sa.Integer(), nullable=False),
            sa.Column("x", sa.Float(), nullable=False),
            sa.Column("y", sa.Float(), nullable=False),
            sa.Column(
                "added_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.CheckConstraint(
                "object_type IN ('analysis_target','code_application','annotation','memo','code','theme')",
                name="ck_analysis_canvas_node_type",
            ),
            sa.CheckConstraint(
                "x >= 0 AND x <= 4000 AND y >= 0 AND y <= 4000",
                name="ck_analysis_canvas_node_coordinates",
            ),
            sa.UniqueConstraint(
                "canvas_id",
                "object_type",
                "object_id",
                name="uq_analysis_canvas_node_object",
            ),
        )
        for name, columns in (
            ("organisation_id", ["organisation_id"]),
            ("study_id", ["study_id"]),
            ("canvas_id", ["canvas_id"]),
            ("added_by_id", ["added_by_id"]),
            ("scope", ["organisation_id", "study_id", "canvas_id"]),
        ):
            op.create_index(
                f"ix_analysis_canvas_nodes_{name}", "analysis_canvas_nodes", columns
            )
    _drop_guards()
    _create_guards()


def downgrade():
    _drop_guards()
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "analysis_canvas_nodes" in tables:
        op.drop_table("analysis_canvas_nodes")
    if "analysis_canvases" in tables:
        op.drop_table("analysis_canvases")
