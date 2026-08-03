"""Azure storage and Defender scan state

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("evidence_files")}
    with op.batch_alter_table("evidence_files") as batch:
        if "storage_provider" not in columns:
            batch.add_column(sa.Column("storage_provider", sa.String(30), nullable=False, server_default="local"))
        if "blob_uri" not in columns:
            batch.add_column(sa.Column("blob_uri", sa.Text(), nullable=False, server_default=""))
        if "scan_completed_at" not in columns:
            batch.add_column(sa.Column("scan_completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table("evidence_files") as batch:
        batch.drop_column("scan_completed_at")
        batch.drop_column("blob_uri")
        batch.drop_column("storage_provider")
