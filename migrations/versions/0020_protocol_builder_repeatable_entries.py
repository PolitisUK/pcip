"""Add protocol-builder selections and repeatable activity entries.

This is additive for protocol metadata.  Response uniqueness moves from a
single response per activity/participant to a client-entry key, while the
application continues to enforce the legacy single-response rule whenever an
activity has not opted into repeatable entries.
"""

import sqlalchemy as sa
from alembic import op


revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def _drop_legacy_response_unique(bind):
    inspector = sa.inspect(bind)
    constraints = inspector.get_unique_constraints("activity_responses")
    legacy = next(
        (item.get("name") for item in constraints
         if item.get("column_names") == ["activity_id", "participant_id"]),
        None,
    )
    if legacy:
        with op.batch_alter_table("activity_responses") as batch:
            batch.drop_constraint(legacy, type_="unique")
        return
    # PostgreSQL gives unnamed SQLAlchemy constraints this deterministic name.
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE activity_responses DROP CONSTRAINT IF EXISTS activity_responses_activity_id_participant_id_key")


def upgrade():
    bind = op.get_bind()
    activity_columns = {column["name"] for column in sa.inspect(bind).get_columns("activities")}
    with op.batch_alter_table("activities") as batch:
        if "allow_multiple_entries" not in activity_columns:
            batch.add_column(sa.Column("allow_multiple_entries", sa.Boolean(), nullable=False, server_default=sa.false()))

    configuration_columns = {column["name"] for column in sa.inspect(bind).get_columns("study_methodology_configurations")}
    with op.batch_alter_table("study_methodology_configurations") as batch:
        for name in (
            "research_approaches_json", "evidence_methods_json", "analysis_approaches_json",
            "theoretical_orientations_json", "legacy_methodology_json",
        ):
            if name not in configuration_columns:
                batch.add_column(sa.Column(name, sa.Text(), nullable=False, server_default="[]"))

    response_columns = {column["name"] for column in sa.inspect(bind).get_columns("activity_responses")}
    if "client_entry_key_hash" not in response_columns or "repeatable" not in response_columns:
        with op.batch_alter_table("activity_responses") as batch:
            if "client_entry_key_hash" not in response_columns:
                batch.add_column(sa.Column("client_entry_key_hash", sa.String(length=64), nullable=True))
            if "repeatable" not in response_columns:
                batch.add_column(sa.Column("repeatable", sa.Boolean(), nullable=False, server_default=sa.false()))
    _drop_legacy_response_unique(bind)
    constraints = {item.get("name") for item in sa.inspect(bind).get_unique_constraints("activity_responses")}
    if "uq_activity_response_entry_key" not in constraints:
        with op.batch_alter_table("activity_responses") as batch:
            batch.create_unique_constraint(
                "uq_activity_response_entry_key",
                ["activity_id", "participant_id", "client_entry_key_hash"],
            )
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("activity_responses")}
    if "uq_activity_response_single_entry" not in indexes:
        op.create_index(
            "uq_activity_response_single_entry",
            "activity_responses",
            ["activity_id", "participant_id"],
            unique=True,
            postgresql_where=sa.text("repeatable = false"),
            sqlite_where=sa.text("repeatable = 0"),
        )


def downgrade():
    bind = op.get_bind()
    # A downgrade is only safe while no repeatable activity has more than one
    # response for a participant.  Refuse destructive historical data loss.
    duplicates = bind.execute(sa.text("""
        SELECT 1 FROM activity_responses
        GROUP BY activity_id, participant_id HAVING count(*) > 1 LIMIT 1
    """)).first()
    if duplicates:
        raise RuntimeError("Cannot downgrade 0020 while repeatable response history exists.")
    op.drop_index("uq_activity_response_single_entry", table_name="activity_responses")
    with op.batch_alter_table("activity_responses") as batch:
        batch.drop_constraint("uq_activity_response_entry_key", type_="unique")
        batch.drop_column("repeatable")
        batch.drop_column("client_entry_key_hash")
    with op.batch_alter_table("activity_responses") as batch:
        batch.create_unique_constraint("uq_activity_response_single_entry", ["activity_id", "participant_id"])
    with op.batch_alter_table("study_methodology_configurations") as batch:
        for name in (
            "legacy_methodology_json", "theoretical_orientations_json", "analysis_approaches_json",
            "evidence_methods_json", "research_approaches_json",
        ):
            batch.drop_column(name)
    with op.batch_alter_table("activities") as batch:
        batch.drop_column("allow_multiple_entries")
