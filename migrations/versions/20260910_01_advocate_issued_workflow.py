"""Add the private advocate-issued document workflow foundation.

Revision ID: 20260910_01
Revises: 20260908_01
Create Date: 2026-09-10
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

from models import (
    DocumentAdvocateAssignment,
    DocumentDispatchEvent,
    DocumentEvidenceArtifact,
    DocumentIssueApproval,
    DocumentLegalHold,
    DocumentMatterReview,
    DocumentQuote,
)


revision: str = "20260910_01"
down_revision: str | Sequence[str] | None = "20260908_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_names(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()

    advocate_columns = _column_names(bind, "advocates")
    with op.batch_alter_table("advocates") as batch:
        if "verification_status" not in advocate_columns:
            batch.add_column(
                sa.Column(
                    "verification_status",
                    sa.String(24),
                    nullable=False,
                    server_default="PENDING",
                )
            )
        if "verification_ref" not in advocate_columns:
            batch.add_column(sa.Column("verification_ref", sa.String(160)))
        if "verified_at" not in advocate_columns:
            batch.add_column(sa.Column("verified_at", sa.DateTime()))
        if "authority_scope_json" not in advocate_columns:
            batch.add_column(
                sa.Column(
                    "authority_scope_json",
                    sa.Text(),
                    nullable=False,
                    server_default="{}",
                )
            )

    admin_columns = _column_names(bind, "admin_operators")
    if "advocate_id" not in admin_columns:
        with op.batch_alter_table("admin_operators") as batch:
            batch.add_column(sa.Column("advocate_id", sa.Integer()))
            batch.create_foreign_key(
                "fk_admin_operator_advocate",
                "advocates",
                ["advocate_id"],
                ["id"],
            )
            batch.create_unique_constraint(
                "uq_admin_operator_advocate",
                ["advocate_id"],
            )
            batch.create_index(
                "ix_admin_operators_advocate_id",
                ["advocate_id"],
            )

    DocumentEvidenceArtifact.__table__.create(bind, checkfirst=True)

    access_columns = _column_names(bind, "document_access_events")
    if "document_evidence_artifact_id" not in access_columns:
        with op.batch_alter_table("document_access_events") as batch:
            batch.add_column(
                sa.Column("document_evidence_artifact_id", sa.Integer())
            )
            batch.create_foreign_key(
                "fk_document_access_evidence",
                "document_evidence_artifacts",
                ["document_evidence_artifact_id"],
                ["id"],
            )
            batch.create_index(
                "ix_document_access_events_document_evidence_artifact_id",
                ["document_evidence_artifact_id"],
            )

    DocumentAdvocateAssignment.__table__.create(bind, checkfirst=True)
    DocumentMatterReview.__table__.create(bind, checkfirst=True)
    DocumentQuote.__table__.create(bind, checkfirst=True)
    DocumentIssueApproval.__table__.create(bind, checkfirst=True)
    DocumentDispatchEvent.__table__.create(bind, checkfirst=True)
    DocumentLegalHold.__table__.create(bind, checkfirst=True)


def downgrade() -> None:
    # Preserve legal, payment, identity, dispatch and access evidence.
    pass
