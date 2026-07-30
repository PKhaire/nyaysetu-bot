"""Scheduled Razorpay reconciliation safety net."""

from __future__ import annotations

import argparse
import json

from db import SessionLocal
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
    try:
        stats = reconcile_recent_payment_links(db, limit=args.limit)
    except Exception as exc:
        db.rollback()
        print(
            json.dumps(
                {
                    "error": type(exc).__name__,
                    "ok": False,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 2
    finally:
        db.close()

    ok = stats["provider_errors"] == 0
    print(
        json.dumps(
            {"ok": ok, **stats},
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
