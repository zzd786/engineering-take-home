"""Reject ordinary changes to access evidence.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION reject_diary_access_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Access records cannot be changed';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER diary_access_no_change
        BEFORE UPDATE OR DELETE ON diary_accesses
        FOR EACH ROW EXECUTE FUNCTION reject_diary_access_change()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER diary_access_no_change ON diary_accesses")
    op.execute("DROP FUNCTION reject_diary_access_change()")
