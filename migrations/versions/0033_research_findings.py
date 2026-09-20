"""Add researcher findings and canonical finding relationships."""

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

OBJECTS = {
    "analysis_target": "analysis_targets",
    "code_application": "code_applications",
    "annotation": "research_annotations",
    "memo": "research_memos",
    "code": "research_codes",
    "theme": "research_themes",
    "finding": "research_findings",
}
OLD_OBJECT_TYPES = "'analysis_target','code_application','annotation','memo','code','theme'"
NEW_OBJECT_TYPES = OLD_OBJECT_TYPES + ",'finding'"
OLD_RELATIONSHIP_TYPES = "'supports','contradicts','explains','relates_to','precedes','follows','refines'"
NEW_RELATIONSHIP_TYPES = "'supports','contradicts','qualifies','illustrates','derived_from','informed_by','explains','relates_to','precedes','follows','refines'"


def _constraint_contains(table: str, name: str, token: str) -> bool:
    for constraint in sa.inspect(op.get_bind()).get_check_constraints(table):
        if constraint.get("name") == name:
            return token in (constraint.get("sqltext") or "")
    return False


def _replace_check(table: str, name: str, expression: str):
    with op.batch_alter_table(table) as batch:
        batch.drop_constraint(name, type_="check")
        batch.create_check_constraint(name, expression)


def _drop_guards():
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_research_findings_scope ON research_findings"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_analytical_relationships_scope ON analytical_relationships"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_analysis_canvas_nodes_scope ON analysis_canvas_nodes"
        )
        op.execute("DROP FUNCTION IF EXISTS validate_research_finding_scope()")
        op.execute("DROP FUNCTION IF EXISTS validate_analytical_relationship_scope()")
        op.execute("DROP FUNCTION IF EXISTS validate_analysis_canvas_node_scope()")
    else:
        for table in (
            "research_findings",
            "analytical_relationships",
            "analysis_canvas_nodes",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_scope_insert")
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_scope_update")


def _create_guards(include_finding: bool = True):
    objects = OBJECTS if include_finding else {
        key: value for key, value in OBJECTS.items() if key != "finding"
    }
    if op.get_bind().dialect.name == "postgresql":
        if include_finding:
            op.execute("""
            CREATE FUNCTION validate_research_finding_scope() RETURNS trigger AS $$ BEGIN
              IF NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'research finding study scope'; END IF;
              IF NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.created_by_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'research finding creator scope'; END IF;
              IF NEW.archived_by_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.archived_by_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'research finding archiver scope'; END IF;
              RETURN NEW;
            END; $$ LANGUAGE plpgsql;
            CREATE TRIGGER trg_research_findings_scope BEFORE INSERT OR UPDATE ON research_findings FOR EACH ROW EXECUTE FUNCTION validate_research_finding_scope();
            """)
        validations = []
        for side in ("source", "target"):
            for object_type, table in objects.items():
                validations.append(
                    f"IF NEW.{side}_type='{object_type}' AND NOT EXISTS (SELECT 1 FROM {table} WHERE id=NEW.{side}_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'analytical relationship {side} scope'; END IF;"
                )
        op.execute(f"""
        CREATE FUNCTION validate_analytical_relationship_scope() RETURNS trigger AS $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'analytical relationship study scope'; END IF;
          IF NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.created_by_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'analytical relationship author scope'; END IF;
          {' '.join(validations)} RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_analytical_relationships_scope BEFORE INSERT OR UPDATE ON analytical_relationships FOR EACH ROW EXECUTE FUNCTION validate_analytical_relationship_scope();
        """)
        finding_validation = ""
        if include_finding:
            finding_validation = "IF NEW.object_type='finding' AND NOT EXISTS (SELECT 1 FROM research_findings WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'analysis canvas finding scope'; END IF;"
        op.execute(f"""
        CREATE FUNCTION validate_analysis_canvas_node_scope() RETURNS trigger AS $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM analysis_canvases WHERE id=NEW.canvas_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id AND owner_id=NEW.added_by_id) THEN RAISE EXCEPTION 'analysis canvas node canvas scope'; END IF;
          IF NEW.object_type='analysis_target' AND NOT EXISTS (SELECT 1 FROM analysis_targets WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'analysis canvas target scope'; END IF;
          IF NEW.object_type='code_application' AND NOT EXISTS (SELECT 1 FROM code_applications WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'analysis canvas application scope'; END IF;
          IF NEW.object_type='annotation' AND NOT EXISTS (SELECT 1 FROM research_annotations WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'analysis canvas annotation scope'; END IF;
          IF NEW.object_type='memo' AND NOT EXISTS (SELECT 1 FROM research_memos WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'analysis canvas memo scope'; END IF;
          IF NEW.object_type='code' AND NOT EXISTS (SELECT 1 FROM research_codes WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'analysis canvas code scope'; END IF;
          IF NEW.object_type='theme' AND NOT EXISTS (SELECT 1 FROM research_themes WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'analysis canvas theme scope'; END IF;
          {finding_validation} RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_analysis_canvas_nodes_scope BEFORE INSERT OR UPDATE ON analysis_canvas_nodes FOR EACH ROW EXECUTE FUNCTION validate_analysis_canvas_node_scope();
        """)
    else:
        relationship_validations = []
        for side in ("source", "target"):
            for object_type, table in objects.items():
                relationship_validations.append(
                    f"SELECT RAISE(ABORT,'analytical relationship {side} scope') WHERE NEW.{side}_type='{object_type}' AND NOT EXISTS (SELECT 1 FROM {table} WHERE id=NEW.{side}_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);"
                )
        finding_canvas_validation = ""
        if include_finding:
            finding_canvas_validation = "SELECT RAISE(ABORT,'analysis canvas finding scope') WHERE NEW.object_type='finding' AND NOT EXISTS (SELECT 1 FROM research_findings WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);"
        for action in ("INSERT", "UPDATE"):
            suffix = action.lower()
            if include_finding:
                op.execute(f"""
                CREATE TRIGGER trg_research_findings_scope_{suffix} BEFORE {action} ON research_findings BEGIN
                  SELECT RAISE(ABORT,'research finding study scope') WHERE NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id);
                  SELECT RAISE(ABORT,'research finding creator scope') WHERE NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.created_by_id AND organisation_id=NEW.organisation_id);
                  SELECT RAISE(ABORT,'research finding archiver scope') WHERE NEW.archived_by_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.archived_by_id AND organisation_id=NEW.organisation_id);
                END
                """)
            op.execute(f"""
            CREATE TRIGGER trg_analytical_relationships_scope_{suffix} BEFORE {action} ON analytical_relationships BEGIN
              SELECT RAISE(ABORT,'analytical relationship study scope') WHERE NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id);
              SELECT RAISE(ABORT,'analytical relationship author scope') WHERE NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.created_by_id AND organisation_id=NEW.organisation_id);
              {' '.join(relationship_validations)}
            END
            """)
            op.execute(f"""
            CREATE TRIGGER trg_analysis_canvas_nodes_scope_{suffix} BEFORE {action} ON analysis_canvas_nodes BEGIN
              SELECT RAISE(ABORT,'analysis canvas node canvas scope') WHERE NOT EXISTS (SELECT 1 FROM analysis_canvases WHERE id=NEW.canvas_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id AND owner_id=NEW.added_by_id);
              SELECT RAISE(ABORT,'analysis canvas target scope') WHERE NEW.object_type='analysis_target' AND NOT EXISTS (SELECT 1 FROM analysis_targets WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
              SELECT RAISE(ABORT,'analysis canvas application scope') WHERE NEW.object_type='code_application' AND NOT EXISTS (SELECT 1 FROM code_applications WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
              SELECT RAISE(ABORT,'analysis canvas annotation scope') WHERE NEW.object_type='annotation' AND NOT EXISTS (SELECT 1 FROM research_annotations WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
              SELECT RAISE(ABORT,'analysis canvas memo scope') WHERE NEW.object_type='memo' AND NOT EXISTS (SELECT 1 FROM research_memos WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
              SELECT RAISE(ABORT,'analysis canvas code scope') WHERE NEW.object_type='code' AND NOT EXISTS (SELECT 1 FROM research_codes WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
              SELECT RAISE(ABORT,'analysis canvas theme scope') WHERE NEW.object_type='theme' AND NOT EXISTS (SELECT 1 FROM research_themes WHERE id=NEW.object_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
              {finding_canvas_validation}
            END
            """)


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "research_findings" not in tables:
        op.create_table(
            "research_findings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organisation_id", sa.Integer(), sa.ForeignKey("organisations.id"), nullable=False),
            sa.Column("study_id", sa.Integer(), sa.ForeignKey("studies.id"), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("archived_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.CheckConstraint("title <> ''", name="ck_research_finding_title_nonblank"),
            sa.CheckConstraint("body <> ''", name="ck_research_finding_body_nonblank"),
            sa.CheckConstraint("(archived_at IS NULL) = (archived_by_id IS NULL)", name="ck_research_finding_archive_pair"),
        )
        for name, columns in (
            ("organisation_id", ["organisation_id"]),
            ("study_id", ["study_id"]),
            ("created_by_id", ["created_by_id"]),
            ("archived_at", ["archived_at"]),
            ("scope", ["organisation_id", "study_id", "archived_at"]),
        ):
            op.create_index(f"ix_research_findings_{name}", "research_findings", columns)
    complete_schema = "organisations" in tables
    if complete_schema and not _constraint_contains("analytical_relationships", "ck_analytical_relationship_source_type", "finding"):
        _replace_check("analytical_relationships", "ck_analytical_relationship_source_type", f"source_type IN ({NEW_OBJECT_TYPES})")
        _replace_check("analytical_relationships", "ck_analytical_relationship_target_type", f"target_type IN ({NEW_OBJECT_TYPES})")
    if complete_schema and not _constraint_contains("analytical_relationships", "ck_analytical_relationship_type", "qualifies"):
        _replace_check("analytical_relationships", "ck_analytical_relationship_type", f"relationship_type IN ({NEW_RELATIONSHIP_TYPES})")
    if complete_schema and not _constraint_contains("analysis_canvas_nodes", "ck_analysis_canvas_node_type", "finding"):
        _replace_check("analysis_canvas_nodes", "ck_analysis_canvas_node_type", f"object_type IN ({NEW_OBJECT_TYPES})")
    _drop_guards()
    _create_guards()


def downgrade():
    op.execute("DELETE FROM analysis_canvas_nodes WHERE object_type='finding'")
    op.execute("DELETE FROM analytical_relationships WHERE source_type='finding' OR target_type='finding' OR relationship_type IN ('qualifies','illustrates','derived_from','informed_by')")
    _drop_guards()
    _replace_check("analytical_relationships", "ck_analytical_relationship_source_type", f"source_type IN ({OLD_OBJECT_TYPES})")
    _replace_check("analytical_relationships", "ck_analytical_relationship_target_type", f"target_type IN ({OLD_OBJECT_TYPES})")
    _replace_check("analytical_relationships", "ck_analytical_relationship_type", f"relationship_type IN ({OLD_RELATIONSHIP_TYPES})")
    _replace_check("analysis_canvas_nodes", "ck_analysis_canvas_node_type", f"object_type IN ({OLD_OBJECT_TYPES})")
    op.drop_table("research_findings")
    _create_guards(include_finding=False)
