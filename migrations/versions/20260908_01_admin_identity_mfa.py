"""Add named administrator identities, MFA, and recovery codes.

Revision ID: 20260908_01
Revises: 20260903_01
Create Date: 2026-09-08
"""

from __future__ import annotations

from typing import Sequence

from alembic import op

from models import AdminOperator, AdminRecoveryCode


revision: str = "20260908_01"
down_revision: str | Sequence[str] | None = "20260903_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    AdminOperator.__table__.create(bind, checkfirst=True)
    AdminRecoveryCode.__table__.create(bind, checkfirst=True)


def downgrade() -> None:
    # Preserve administrator identities and access evidence during rollback.
    pass
