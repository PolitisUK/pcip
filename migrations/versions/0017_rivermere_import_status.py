"""Add non-sensitive durable Rivermere import status."""

from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    # 0001 uses the current SQLAlchemy metadata for a clean bootstrap.  In
    # that case this table already exists when Alembic reaches this revision.
    if "demo_import_statuses" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "demo_import_statuses",
        sa.Column("dataset", sa.String(length=80), primary_key=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("phase", sa.String(length=80), nullable=False),
        sa.Column("content_version", sa.String(length=30), nullable=False),
        sa.Column("error_category", sa.String(length=80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    if "demo_import_statuses" not in sa.inspect(op.get_bind()).get_table_names():
        return
    op.drop_table("demo_import_statuses")
