"""Add structured case briefs and auditable consultation handover.

Revision ID: 20260818_01
Revises: 20260729_01
Create Date: 2026-08-18
"""

from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa

from models import CaseBrief, ManualContactEvent


revision: str = "20260818_01"
down_revision: str | Sequence[str] | None = "20260729_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_names(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    CaseBrief.__table__.create(bind, checkfirst=True)
    ManualContactEvent.__table__.create(bind, checkfirst=True)

    advocate_columns = _column_names(bind, "advocates")
    if advocate_columns:
        with op.batch_alter_table("advocates") as batch:
            if "phone" not in advocate_columns:
                batch.add_column(sa.Column("phone", sa.String(32)))
            if "bar_registration_number" not in advocate_columns:
                batch.add_column(
                    sa.Column("bar_registration_number", sa.String(120))
                )
                batch.create_unique_constraint(
                    "uq_advocates_bar_registration_number",
                    ["bar_registration_number"],
                )
            if "languages" not in advocate_columns:
                batch.add_column(sa.Column("languages", sa.String(255)))
            if "operator_notes" not in advocate_columns:
                batch.add_column(sa.Column("operator_notes", sa.Text()))
            if "created_at" not in advocate_columns:
                batch.add_column(sa.Column("created_at", sa.DateTime()))
            if "updated_at" not in advocate_columns:
                batch.add_column(sa.Column("updated_at", sa.DateTime()))

        advocates = sa.table(
            "advocates",
            sa.column("created_at", sa.DateTime()),
            sa.column("updated_at", sa.DateTime()),
        )
        op.execute(
            advocates.update()
            .where(advocates.c.created_at.is_(None))
            .values(created_at=sa.func.current_timestamp())
        )
        op.execute(
            advocates.update()
            .where(advocates.c.updated_at.is_(None))
            .values(updated_at=sa.func.current_timestamp())
        )
        with op.batch_alter_table("advocates") as batch:
            if "created_at" not in advocate_columns:
                batch.alter_column(
                    "created_at",
                    existing_type=sa.DateTime(),
                    nullable=False,
                )
            if "updated_at" not in advocate_columns:
                batch.alter_column(
                    "updated_at",
                    existing_type=sa.DateTime(),
                    nullable=False,
                )


def downgrade() -> None:
    # Preserve client consent, handover evidence, and advocate records during
    # application rollback. The previous code is schema-compatible.
    pass
