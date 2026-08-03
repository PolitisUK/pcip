"""enterprise foundation
Revision ID: 0001
"""
import sqlalchemy as sa
from alembic import op

from app import models  # noqa: F401
from app.db import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "study_access" not in tables:
        op.create_table("study_access",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organisation_id", sa.Integer(), sa.ForeignKey("organisations.id"), nullable=False),
            sa.Column("study_id", sa.Integer(), sa.ForeignKey("studies.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("permission", sa.String(20), nullable=False, server_default="view"),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("study_id", "user_id"))
    cols = {c["name"] for c in inspector.get_columns("evidence_files")}
    with op.batch_alter_table("evidence_files") as batch:
        if "sha256_hex" not in cols: batch.add_column(sa.Column("sha256_hex", sa.String(64), nullable=False, server_default=""))
        if "scan_status" not in cols: batch.add_column(sa.Column("scan_status", sa.String(30), nullable=False, server_default="pending"))
        if "scan_detail" not in cols: batch.add_column(sa.Column("scan_detail", sa.Text(), nullable=False, server_default=""))

def downgrade():
    op.drop_table("study_access")
