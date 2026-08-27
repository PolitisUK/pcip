"""Add optional, participant-initiated point locations to activity entries."""

import sqlalchemy as sa
from alembic import op


revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "activities" in tables:
        activity_columns = {column["name"] for column in inspector.get_columns("activities")}
        with op.batch_alter_table("activities") as batch:
            if "allow_participant_location" not in activity_columns:
                batch.add_column(sa.Column("allow_participant_location", sa.Boolean(), nullable=False, server_default=sa.false()))

    if "activity_responses" in tables:
        response_columns = {column["name"] for column in inspector.get_columns("activity_responses")}
        with op.batch_alter_table("activity_responses") as batch:
            for name, column in (
                ("location_latitude", sa.Column("location_latitude", sa.Float(), nullable=True)),
                ("location_longitude", sa.Column("location_longitude", sa.Float(), nullable=True)),
                ("location_accuracy_metres", sa.Column("location_accuracy_metres", sa.Float(), nullable=True)),
                ("location_source", sa.Column("location_source", sa.String(length=20), nullable=True)),
                ("location_captured_at", sa.Column("location_captured_at", sa.DateTime(timezone=True), nullable=True)),
            ):
                if name not in response_columns:
                    batch.add_column(column)


def downgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "activity_responses" not in tables:
        return
    has_location = bind.execute(
        sa.text(
            "SELECT 1 FROM activity_responses WHERE location_latitude IS NOT NULL "
            "OR location_longitude IS NOT NULL OR location_accuracy_metres IS NOT NULL "
            "OR location_source IS NOT NULL OR location_captured_at IS NOT NULL LIMIT 1"
        )
    ).first()
    if has_location:
        raise RuntimeError("Cannot downgrade 0022 while participant location data exists.")
    with op.batch_alter_table("activity_responses") as batch:
        batch.drop_column("location_captured_at")
        batch.drop_column("location_source")
        batch.drop_column("location_accuracy_metres")
        batch.drop_column("location_longitude")
        batch.drop_column("location_latitude")
    if "activities" in tables:
        with op.batch_alter_table("activities") as batch:
            batch.drop_column("allow_participant_location")
