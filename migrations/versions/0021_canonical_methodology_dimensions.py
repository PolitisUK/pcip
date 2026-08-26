"""Add canonical researcher-facing methodology dimensions.

The 0020 protocol-builder values and controlled methodology identifiers remain
untouched as historical provenance.  These columns provide the single normal
researcher-facing philosophy/design record without reclassifying old studies.
"""

import sqlalchemy as sa
from alembic import op


revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("study_methodology_configurations")}
    with op.batch_alter_table("study_methodology_configurations") as batch:
        if "research_philosophy" not in columns:
            batch.add_column(sa.Column("research_philosophy", sa.String(length=80), nullable=False, server_default="not_specified"))
        if "research_design" not in columns:
            batch.add_column(sa.Column("research_design", sa.String(length=80), nullable=False, server_default="not_specified"))
        if "secondary_design" not in columns:
            batch.add_column(sa.Column("secondary_design", sa.String(length=80), nullable=False, server_default=""))


def downgrade():
    with op.batch_alter_table("study_methodology_configurations") as batch:
        batch.drop_column("secondary_design")
        batch.drop_column("research_design")
        batch.drop_column("research_philosophy")
