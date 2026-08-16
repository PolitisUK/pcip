"""Separate Politis platform administration from customer organisation roles."""

from alembic import op
import sqlalchemy as sa


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    if "is_platform_admin" not in columns:
        with op.batch_alter_table("users") as batch:
            batch.add_column(
                sa.Column(
                    "is_platform_admin",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )


def downgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    if "is_platform_admin" in columns:
        with op.batch_alter_table("users") as batch:
            batch.drop_column("is_platform_admin")
