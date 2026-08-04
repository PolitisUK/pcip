"""Add structured hashtags to participant activity responses.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-03
"""

from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("activity_responses") as batch:
        batch.add_column(sa.Column("hashtags_json", sa.Text(), nullable=False, server_default="[]"))

    with op.batch_alter_table("activity_responses") as batch:
        batch.alter_column("hashtags_json", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("activity_responses") as batch:
        batch.drop_column("hashtags_json")
