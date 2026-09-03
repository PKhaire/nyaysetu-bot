"""Add the release-gated Document Studio RC9 workflow.

Revision ID: 20260827_01
Revises: 20260819_01
Create Date: 2026-08-27
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

from models import (
    DocumentAccessEvent,
    DocumentArtifact,
    DocumentTemplateApproval,
)


revision: str = "20260827_01"
down_revision: str | Sequence[str] | None = "20260819_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_ORDER_COLUMNS = (
    sa.Column("active_revision_number", sa.Integer(), nullable=True),
    sa.Column("schema_hash", sa.String(length=64), nullable=True),
    sa.Column("template_hash", sa.String(length=64), nullable=True),
    sa.Column("preview_manifest_hash", sa.String(length=64), nullable=True),
    sa.Column("price_minor", sa.Integer(), nullable=True),
    sa.Column(
        "currency",
        sa.String(length=3),
        nullable=False,
        server_default="INR",
    ),
    sa.Column("payment_token", sa.String(length=64), nullable=True),
    sa.Column(
        "razorpay_payment_link_id",
        sa.String(length=128),
        nullable=True,
    ),
    sa.Column(
        "razorpay_payment_id",
        sa.String(length=128),
        nullable=True,
    ),
    sa.Column(
        "payment_processed",
        sa.Boolean(),
        nullable=False,
        server_default=sa.false(),
    ),
    sa.Column("paid_at", sa.DateTime(), nullable=True),
    sa.Column(
        "release_status",
        sa.String(length=32),
        nullable=False,
        server_default="CANDIDATE",
    ),
    sa.Column("exception_code", sa.String(length=64), nullable=True),
    sa.Column("final_available_until", sa.DateTime(), nullable=True),
)


def _column_names(bind, table_name: str) -> set[str]:
    return {
        item["name"]
        for item in sa.inspect(bind).get_columns(table_name)
    }


def _index_names(bind, table_name: str) -> set[str]:
    return {
        item["name"]
        for item in sa.inspect(bind).get_indexes(table_name)
    }


def upgrade() -> None:
    bind = op.get_bind()
    existing = _column_names(bind, "document_orders")
    for column in _ORDER_COLUMNS:
        if column.name not in existing:
            op.add_column("document_orders", column)

    indexes = _index_names(bind, "document_orders")
    for name, columns in (
        ("ix_document_orders_payment_token", ["payment_token"]),
        (
            "ix_document_orders_razorpay_payment_link_id",
            ["razorpay_payment_link_id"],
        ),
        (
            "ix_document_orders_razorpay_payment_id",
            ["razorpay_payment_id"],
        ),
    ):
        if name not in indexes:
            op.create_index(name, "document_orders", columns, unique=True)

    DocumentTemplateApproval.__table__.create(bind, checkfirst=True)
    DocumentArtifact.__table__.create(bind, checkfirst=True)
    DocumentAccessEvent.__table__.create(bind, checkfirst=True)


def downgrade() -> None:
    # Preserve paid entitlements, approval evidence and access audit data.
    pass
