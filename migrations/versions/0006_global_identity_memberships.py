"""Add global staff identities and organisation memberships.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-28
"""

from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def _index_exists(
    connection: sa.Connection,
    table_name: str,
    index_name: str,
) -> bool:
    if connection.dialect.name == "sqlite":
        return connection.scalar(
            sa.text(
                """
                SELECT count(*)
                FROM sqlite_master
                WHERE type = 'index'
                  AND tbl_name = :table_name
                  AND name = :index_name
                """
            ),
            {
                "table_name": table_name,
                "index_name": index_name,
            },
        ) > 0
    return index_name in {
        index["name"]
        for index in sa.inspect(connection).get_indexes(table_name)
    }


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())

    duplicate_email_groups = connection.scalar(
        sa.text(
            """
            SELECT count(*)
            FROM (
                SELECT lower(trim(email))
                FROM users
                GROUP BY lower(trim(email))
                HAVING count(*) > 1
            ) AS duplicates
            """
        )
    )
    if duplicate_email_groups:
        raise RuntimeError(
            "Cannot establish global staff identities while duplicate "
            "normalised user emails exist."
        )

    if "organisation_memberships" not in tables:
        op.create_table(
            "organisation_memberships",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("organisation_id", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(length=30), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "user_id",
                "organisation_id",
                name="uq_organisation_memberships_user_org",
            ),
        )

    membership_indexes = {
        index["name"]
        for index in sa.inspect(connection).get_indexes(
            "organisation_memberships"
        )
    }
    for index_name, column_name in (
        ("ix_organisation_memberships_user_id", "user_id"),
        ("ix_organisation_memberships_organisation_id", "organisation_id"),
    ):
        if index_name not in membership_indexes:
            op.create_index(
                index_name,
                "organisation_memberships",
                [column_name],
                unique=False,
            )

    connection.execute(
        sa.text(
            """
            INSERT INTO organisation_memberships (
                user_id,
                organisation_id,
                role,
                is_active,
                created_at
            )
            SELECT
                users.id,
                users.organisation_id,
                users.role,
                users.is_active,
                users.created_at
            FROM users
            WHERE NOT EXISTS (
                SELECT 1
                FROM organisation_memberships
                WHERE organisation_memberships.user_id = users.id
                  AND organisation_memberships.organisation_id =
                      users.organisation_id
            )
            """
        )
    )

    if not _index_exists(
        connection,
        "users",
        "ux_users_email_normalized",
    ):
        op.create_index(
            "ux_users_email_normalized",
            "users",
            [sa.text("lower(email)")],
            unique=True,
        )


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if "users" in inspector.get_table_names():
        if _index_exists(
            connection,
            "users",
            "ux_users_email_normalized",
        ):
            op.drop_index(
                "ux_users_email_normalized",
                table_name="users",
            )
    if "organisation_memberships" in inspector.get_table_names():
        op.drop_table("organisation_memberships")
