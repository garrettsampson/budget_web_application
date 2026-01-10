"""Add expense history and soft delete fields

Revision ID: 7c1df6657f25
Revises: 7bdbf75fcc04
Create Date: 2026-01-09 17:11:27.541441
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7c1df6657f25"
down_revision = "7bdbf75fcc04"
branch_labels = None
depends_on = None


def _get_existing_columns(table_name: str) -> set[str]:
    """
    SQLite helper:
    PRAGMA table_info(table) returns rows like:
      (cid, name, type, notnull, dflt_value, pk)
    We grab the "name" field and return a set of column names.
    """
    conn = op.get_bind()
    rows = conn.execute(sa.text(f"PRAGMA table_info({table_name})")).fetchall()
    return {r[1] for r in rows}


def upgrade():
    # If upgrade failed halfway before, one of these columns may already exist.
    # This makes the migration "safe to re-run".
    existing = _get_existing_columns("expense")

    with op.batch_alter_table("expense", schema=None) as batch_op:
        # Add deleted_at if missing
        if "deleted_at" not in existing:
            batch_op.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))

        # Add is_active if missing
        #
        # IMPORTANT:
        # - This column is NOT NULL, so we MUST give SQLite a default so existing rows
        #   can be populated during the ALTER TABLE.
        #
        # SQLite uses 1/0 for booleans, so we set server_default="1".
        if "is_active" not in existing:
            batch_op.add_column(
                sa.Column(
                    "is_active",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("1"),
                )
            )

    # Optional: If you want to remove the default afterward:
    # SQLite can't easily drop server_default without a full table rebuild.
    # It's safe to leave it in place.


def downgrade():
    existing = _get_existing_columns("expense")

    with op.batch_alter_table("expense", schema=None) as batch_op:
        # Drop in reverse order, but only if they exist
        if "is_active" in existing:
            batch_op.drop_column("is_active")
        if "deleted_at" in existing:
            batch_op.drop_column("deleted_at")
