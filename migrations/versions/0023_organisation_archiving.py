"""Add reversible organisation archiving."""

import sqlalchemy as sa
from alembic import op


revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "organisations" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("organisations")}
    if "archived_at" not in columns:
        with op.batch_alter_table("organisations") as batch:
            batch.add_column(
                sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True)
            )
            batch.create_index(
                "ix_organisations_archived_at",
                ["archived_at"],
                unique=False,
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "organisations" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("organisations")}
    if "archived_at" not in columns:
        return
    archived = bind.execute(
        sa.text("SELECT 1 FROM organisations WHERE archived_at IS NOT NULL LIMIT 1")
    ).first()
    if archived:
        raise RuntimeError("Cannot downgrade 0023 while archived organisations exist.")
    with op.batch_alter_table("organisations") as batch:
        batch.drop_index("ix_organisations_archived_at")
        batch.drop_column("archived_at")
