"""Run one conservative, bounded NyaySetu maintenance batch."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from services.maintenance_service import (
    DEFAULT_BATCH_SIZE,
    MAX_BATCH_SIZE,
    run_maintenance,
)


def _batch_size(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("batch size must be an integer") from exc
    if not 1 <= parsed <= MAX_BATCH_SIZE:
        raise argparse.ArgumentTypeError(
            f"batch size must be between 1 and {MAX_BATCH_SIZE}"
        )
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a bounded, privacy-preserving maintenance batch.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report eligible records without committing any changes.",
    )
    parser.add_argument(
        "--batch-size",
        type=_batch_size,
        default=DEFAULT_BATCH_SIZE,
        help=(
            "Maximum records affected per category "
            f"(default: {DEFAULT_BATCH_SIZE}, max: {MAX_BATCH_SIZE})."
        ),
    )
    parser.add_argument(
        "--fail-on-risk",
        action="store_true",
        help=(
            "Exit 2 after a successful run when overdue/stale operational "
            "risks require attention."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run_maintenance(
            dry_run=args.dry_run,
            batch_size=args.batch_size,
        )
    except Exception as exc:
        # Never print an exception message: provider/database errors can include
        # credentials or user data. The type is enough for operational routing.
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "maintenance_failed",
                    "error_type": type(exc).__name__,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 1

    print(json.dumps(report, separators=(",", ":"), sort_keys=True))
    if (
        args.fail_on_risk
        and report.get("operational_risks", {})
        .get("summary", {})
        .get("alert_required")
        is True
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
