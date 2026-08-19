"""Add the resumable, non-legal Document Studio UAT workflow.

Revision ID: 20260819_01
Revises: 20260818_01
Create Date: 2026-08-19
"""

from __future__ import annotations

from typing import Sequence

from alembic import op

from models import DocumentAnswerRevision, DocumentAuditEvent, DocumentOrder


revision: str = "20260819_01"
down_revision: str | Sequence[str] | None = "20260818_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    DocumentOrder.__table__.create(bind, checkfirst=True)
    DocumentAnswerRevision.__table__.create(bind, checkfirst=True)
    DocumentAuditEvent.__table__.create(bind, checkfirst=True)


def downgrade() -> None:
    # Preserve UAT consent and workflow evidence during application rollback.
    pass
