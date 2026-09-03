"""Add global daily Document Studio capacity reservations.

Revision ID: 20260903_01
Revises: 20260827_01
Create Date: 2026-09-03
"""

from __future__ import annotations

from typing import Sequence

from alembic import op

from models import DocumentCapacityReservation


revision: str = "20260903_01"
down_revision: str | Sequence[str] | None = "20260827_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    DocumentCapacityReservation.__table__.create(bind, checkfirst=True)


def downgrade() -> None:
    # Preserve capacity allocation and release evidence during code rollback.
    pass
