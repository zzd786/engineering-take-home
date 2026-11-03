"""Store diary consent and clinician access evidence.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "diary_shares",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("clinician_id", sa.Integer(), sa.ForeignKey("clinicians.id"), nullable=False),
        sa.Column("from_date", sa.Date(), nullable=False),
        sa.Column("to_date", sa.Date(), nullable=False),
        sa.Column("include_notes", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("consent_version", sa.String(64), nullable=False),
        sa.Column("consent_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("from_date <= to_date", name="share_date_order"),
    )
    op.create_index("ix_diary_shares_patient_id", "diary_shares", ["patient_id"])
    op.create_index("ix_diary_shares_clinician_id", "diary_shares", ["clinician_id"])
    op.create_table(
        "diary_accesses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("clinician_id", sa.Integer(), sa.ForeignKey("clinicians.id"), nullable=False),
        sa.Column(
            "accessed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("entry_ids", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("note_entry_ids", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("share_ids", postgresql.ARRAY(sa.Integer()), nullable=False),
    )
    op.create_index("ix_diary_accesses_patient_id", "diary_accesses", ["patient_id"])


def downgrade() -> None:
    op.drop_index("ix_diary_accesses_patient_id", table_name="diary_accesses")
    op.drop_table("diary_accesses")
    op.drop_index("ix_diary_shares_clinician_id", table_name="diary_shares")
    op.drop_index("ix_diary_shares_patient_id", table_name="diary_shares")
    op.drop_table("diary_shares")
