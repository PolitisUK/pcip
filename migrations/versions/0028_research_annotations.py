"""Add exact-passage researcher annotations."""

import sqlalchemy as sa
from alembic import op


revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def _drop_guards() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_research_annotations_scope ON research_annotations")
        op.execute("DROP FUNCTION IF EXISTS validate_research_annotation_scope()")
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_research_annotations_scope_insert")
        op.execute("DROP TRIGGER IF EXISTS trg_research_annotations_scope_update")


def _create_guards() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
        CREATE FUNCTION validate_research_annotation_scope() RETURNS trigger AS $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id) THEN
            RAISE EXCEPTION 'research annotation study scope';
          END IF;
          IF NOT EXISTS (SELECT 1 FROM analysis_targets WHERE id=NEW.analysis_target_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN
            RAISE EXCEPTION 'research annotation target scope';
          END IF;
          IF NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.author_id AND organisation_id=NEW.organisation_id) THEN
            RAISE EXCEPTION 'research annotation author scope';
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_research_annotations_scope BEFORE INSERT OR UPDATE ON research_annotations
        FOR EACH ROW EXECUTE FUNCTION validate_research_annotation_scope();
        """)
    else:
        for action in ("INSERT", "UPDATE"):
            op.execute(f"""
            CREATE TRIGGER trg_research_annotations_scope_{action.lower()}
            BEFORE {action} ON research_annotations BEGIN
              SELECT RAISE(ABORT,'research annotation study scope') WHERE NOT EXISTS
                (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id);
              SELECT RAISE(ABORT,'research annotation target scope') WHERE NOT EXISTS
                (SELECT 1 FROM analysis_targets WHERE id=NEW.analysis_target_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);
              SELECT RAISE(ABORT,'research annotation author scope') WHERE NOT EXISTS
                (SELECT 1 FROM users WHERE id=NEW.author_id AND organisation_id=NEW.organisation_id);
            END
            """)


def upgrade() -> None:
    bind = op.get_bind()
    if "research_annotations" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "research_annotations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organisation_id", sa.Integer(), sa.ForeignKey("organisations.id"), nullable=False),
            sa.Column("study_id", sa.Integer(), sa.ForeignKey("studies.id"), nullable=False),
            sa.Column("analysis_target_id", sa.Integer(), sa.ForeignKey("analysis_targets.id"), nullable=False),
            sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("anchor_json", sa.Text(), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_research_annotations_scope", "research_annotations", ["organisation_id", "study_id", "analysis_target_id"])
        for name, columns in (
            ("ix_research_annotations_organisation_id", ["organisation_id"]),
            ("ix_research_annotations_study_id", ["study_id"]),
            ("ix_research_annotations_analysis_target_id", ["analysis_target_id"]),
            ("ix_research_annotations_author_id", ["author_id"]),
        ):
            op.create_index(name, "research_annotations", columns)
    _drop_guards()
    _create_guards()


def downgrade() -> None:
    _drop_guards()
    op.drop_table("research_annotations")
