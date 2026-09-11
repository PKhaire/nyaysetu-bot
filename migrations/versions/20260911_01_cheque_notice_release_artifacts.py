"""Add classification-specific Draft Studio release artifact evidence.

Revision ID: 20260911_01
Revises: 20260910_01
Create Date: 2026-09-11
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260911_01"
down_revision: str | Sequence[str] | None = "20260910_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_names(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    columns = _column_names(bind, "document_template_approvals")
    with op.batch_alter_table("document_template_approvals") as batch:
        if "golden_artifact_hashes_json" not in columns:
            batch.add_column(sa.Column("golden_artifact_hashes_json", sa.Text()))
        batch.alter_column(
            "golden_pdf_hash",
            existing_type=sa.String(64),
            nullable=True,
        )
        batch.alter_column(
            "golden_docx_hash",
            existing_type=sa.String(64),
            nullable=True,
        )


def downgrade() -> None:
    # Preserve approval evidence. Restoring the old non-null pair could discard
    # valid classification-specific package records, so rollback is manual.
    pass
