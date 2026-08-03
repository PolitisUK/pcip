"""Microsoft Entra identity fields

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("users")}
    with op.batch_alter_table("users") as batch:
        if "external_provider" not in columns:
            batch.add_column(sa.Column("external_provider", sa.String(40), nullable=True))
        if "external_subject" not in columns:
            batch.add_column(sa.Column("external_subject", sa.String(255), nullable=True))
        if "last_login_at" not in columns:
            batch.add_column(sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    indexes = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("users")}
    if "ix_users_external_provider" not in indexes:
        op.create_index("ix_users_external_provider", "users", ["external_provider"], unique=False)
    if "ix_users_external_subject" not in indexes:
        op.create_index("ix_users_external_subject", "users", ["external_subject"], unique=False)

def downgrade():
    op.drop_index("ix_users_external_subject", table_name="users")
    op.drop_index("ix_users_external_provider", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("last_login_at")
        batch.drop_column("external_subject")
        batch.drop_column("external_provider")
