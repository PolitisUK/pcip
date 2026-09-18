"""Add provenance-preserving, referential analysis targets.

This revision is intentionally additive from the released 0024 baseline.
"""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def _sqlite_scope_triggers() -> None:
    for action in ("INSERT", "UPDATE"):
        suffix = action.lower()
        op.execute(f"""
            CREATE TRIGGER trg_analysis_targets_scope_{suffix}
            BEFORE {action} ON analysis_targets
            BEGIN
              SELECT RAISE(ABORT, 'analysis target study is outside organisation')
              WHERE NOT EXISTS (SELECT 1 FROM studies WHERE id = NEW.study_id AND organisation_id = NEW.organisation_id);
              SELECT RAISE(ABORT, 'analysis target researcher is outside organisation')
              WHERE NEW.authorship = 'researcher' AND NOT EXISTS
                (SELECT 1 FROM users WHERE id = NEW.created_by_id AND organisation_id = NEW.organisation_id);
              SELECT RAISE(ABORT, 'analysis target response is outside study scope')
              WHERE NEW.target_type = 'activity_response' AND NOT EXISTS
                (SELECT 1 FROM activity_responses WHERE id = NEW.activity_response_id AND organisation_id = NEW.organisation_id AND study_id = NEW.study_id);
              SELECT RAISE(ABORT, 'analysis target evidence is outside study scope')
              WHERE NEW.target_type = 'evidence_file' AND NOT EXISTS
                (SELECT 1 FROM evidence_files WHERE id = NEW.evidence_file_id AND organisation_id = NEW.organisation_id AND study_id = NEW.study_id);
              SELECT RAISE(ABORT, 'analysis target participant is outside study scope')
              WHERE NEW.target_type = 'participant_case' AND NOT EXISTS
                (SELECT 1 FROM study_enrolments WHERE organisation_id = NEW.organisation_id AND study_id = NEW.study_id AND participant_id = NEW.participant_id);
            END
        """)


def _postgres_scope_trigger() -> None:
    op.execute("""
        CREATE FUNCTION validate_analysis_target_scope() RETURNS trigger AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM studies WHERE id = NEW.study_id AND organisation_id = NEW.organisation_id) THEN
            RAISE EXCEPTION 'analysis target study is outside organisation';
          END IF;
          IF NEW.authorship = 'researcher' AND NOT EXISTS
            (SELECT 1 FROM users WHERE id = NEW.created_by_id AND organisation_id = NEW.organisation_id) THEN
            RAISE EXCEPTION 'analysis target researcher is outside organisation';
          END IF;
          IF NEW.target_type = 'activity_response' AND NOT EXISTS
            (SELECT 1 FROM activity_responses WHERE id = NEW.activity_response_id AND organisation_id = NEW.organisation_id AND study_id = NEW.study_id) THEN
            RAISE EXCEPTION 'analysis target response is outside study scope';
          END IF;
          IF NEW.target_type = 'evidence_file' AND NOT EXISTS
            (SELECT 1 FROM evidence_files WHERE id = NEW.evidence_file_id AND organisation_id = NEW.organisation_id AND study_id = NEW.study_id) THEN
            RAISE EXCEPTION 'analysis target evidence is outside study scope';
          END IF;
          IF NEW.target_type = 'participant_case' AND NOT EXISTS
            (SELECT 1 FROM study_enrolments WHERE organisation_id = NEW.organisation_id AND study_id = NEW.study_id AND participant_id = NEW.participant_id) THEN
            RAISE EXCEPTION 'analysis target participant is outside study scope';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_analysis_targets_scope
        BEFORE INSERT OR UPDATE ON analysis_targets
        FOR EACH ROW EXECUTE FUNCTION validate_analysis_target_scope();
    """)


def upgrade():
    # Revision 0001 uses current metadata when creating an empty database, so
    # a fresh rehearsal already has this additive table before it reaches
    # 0025.  Install the scope guards in that path too.
    if "analysis_targets" in sa.inspect(op.get_bind()).get_table_names():
        if op.get_bind().dialect.name == "postgresql":
            op.execute("DROP TRIGGER IF EXISTS trg_analysis_targets_scope ON analysis_targets")
            op.execute("DROP FUNCTION IF EXISTS validate_analysis_target_scope()")
            _postgres_scope_trigger()
        else:
            op.execute("DROP TRIGGER IF EXISTS trg_analysis_targets_scope_insert")
            op.execute("DROP TRIGGER IF EXISTS trg_analysis_targets_scope_update")
            _sqlite_scope_triggers()
        return
    op.create_table(
        "analysis_targets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organisation_id", sa.Integer(), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("study_id", sa.Integer(), sa.ForeignKey("studies.id"), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("activity_response_id", sa.Integer(), sa.ForeignKey("activity_responses.id"), nullable=True),
        sa.Column("evidence_file_id", sa.Integer(), sa.ForeignKey("evidence_files.id"), nullable=True),
        sa.Column("participant_id", sa.Integer(), sa.ForeignKey("participants.id"), nullable=True),
        sa.Column("anchor_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("authorship", sa.String(length=30), nullable=False, server_default="researcher"),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("target_type IN ('activity_response', 'evidence_file', 'participant_case')", name="ck_analysis_target_type"),
        sa.CheckConstraint("(target_type = 'activity_response' AND activity_response_id IS NOT NULL AND evidence_file_id IS NULL AND participant_id IS NULL) OR (target_type = 'evidence_file' AND activity_response_id IS NULL AND evidence_file_id IS NOT NULL AND participant_id IS NULL) OR (target_type = 'participant_case' AND activity_response_id IS NULL AND evidence_file_id IS NULL AND participant_id IS NOT NULL)", name="ck_analysis_target_one_source"),
        sa.CheckConstraint("(authorship = 'researcher' AND created_by_id IS NOT NULL) OR authorship IN ('system', 'ai_suggestion')", name="ck_analysis_target_authorship"),
    )
    for name, columns in (
        ("ix_analysis_targets_organisation_id", ["organisation_id"]),
        ("ix_analysis_targets_study_id", ["study_id"]),
        ("ix_analysis_targets_target_type", ["target_type"]),
        ("ix_analysis_targets_authorship", ["authorship"]),
        ("ix_analysis_targets_study_type", ["organisation_id", "study_id", "target_type"]),
        ("ix_analysis_targets_response", ["activity_response_id"]),
        ("ix_analysis_targets_evidence", ["evidence_file_id"]),
        ("ix_analysis_targets_participant", ["participant_id"]),
    ):
        op.create_index(name, "analysis_targets", columns)
    if op.get_bind().dialect.name == "postgresql":
        _postgres_scope_trigger()
    else:
        _sqlite_scope_triggers()


def downgrade():
    bind = op.get_bind()
    if "analysis_targets" not in sa.inspect(bind).get_table_names():
        return
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_analysis_targets_scope ON analysis_targets")
        op.execute("DROP FUNCTION IF EXISTS validate_analysis_target_scope()")
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_analysis_targets_scope_insert")
        op.execute("DROP TRIGGER IF EXISTS trg_analysis_targets_scope_update")
    op.drop_table("analysis_targets")
