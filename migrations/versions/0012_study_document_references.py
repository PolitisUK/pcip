"""Add auditable study document references to consent evidence."""

from alembic import op
import sqlalchemy as sa


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


_DOCUMENT_COLUMNS = (
    ("participant_information_reference", sa.String(500)),
    ("participant_information_version", sa.String(80)),
    ("participant_information_effective_date", sa.String(30)),
    ("privacy_notice_reference", sa.String(500)),
    ("privacy_notice_version", sa.String(80)),
    ("privacy_notice_effective_date", sa.String(30)),
    ("consent_text_reference", sa.String(500)),
    ("consent_text_version", sa.String(80)),
    ("consent_text_effective_date", sa.String(30)),
)


def upgrade():
    bind = op.get_bind()
    for table_name in ("study_governance", "participant_invitations"):
        existing = {column["name"] for column in sa.inspect(bind).get_columns(table_name)}
        with op.batch_alter_table(table_name) as batch:
            for name, column_type in _DOCUMENT_COLUMNS:
                if name not in existing:
                    batch.add_column(sa.Column(name, column_type, nullable=False, server_default=""))


def downgrade():
    bind = op.get_bind()
    for table_name in ("participant_invitations", "study_governance"):
        existing = {column["name"] for column in sa.inspect(bind).get_columns(table_name)}
        with op.batch_alter_table(table_name) as batch:
            for name, _column_type in reversed(_DOCUMENT_COLUMNS):
                if name in existing:
                    batch.drop_column(name)
