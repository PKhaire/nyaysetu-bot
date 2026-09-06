"""Scheduled Razorpay reconciliation safety net."""

from __future__ import annotations

import argparse
import json

from db import SessionLocal
from services.document_operations_service import (
    reconcile_recent_document_payments,
)
from services.payment_reconciliation_service import (
    reconcile_recent_payment_links,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile unresolved Razorpay payment links.",
    )
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args(argv)

    db = SessionLocal()
    failures = []
    consultation_stats = None
    document_stats = None
    try:
        try:
            consultation_stats = reconcile_recent_payment_links(
                db, limit=args.limit
            )
        except Exception as exc:
            db.rollback()
            failures.append(
                {"scope": "consultations", "error": type(exc).__name__}
            )
        try:
            document_stats = reconcile_recent_document_payments(
                db, limit=args.limit
            )
        except Exception as exc:
            db.rollback()
            failures.append(
                {"scope": "document_studio", "error": type(exc).__name__}
            )
    finally:
        db.close()

    ok = bool(
        not failures
        and consultation_stats is not None
        and document_stats is not None
        and consultation_stats["provider_errors"] == 0
        and document_stats["provider_errors"] == 0
        and document_stats["release_failed"] == 0
    )
    print(
        json.dumps(
            {
                "consultations": consultation_stats,
                "document_studio": document_stats,
                "failures": failures,
                "ok": ok,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
