"""Enqueue one bounded batch of approved-template consultation reminders."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from services.consultation_reminder_service import (
    DEFAULT_BATCH_SIZE,
    MAX_BATCH_SIZE,
    schedule_consultation_reminders,
)


def _batch_size(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "batch size must be an integer"
        ) from exc
    if not 1 <= parsed <= MAX_BATCH_SIZE:
        raise argparse.ArgumentTypeError(
            f"batch size must be between 1 and {MAX_BATCH_SIZE}"
        )
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Enqueue due consultation reminders only for configured "
            "Meta-approved templates."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report would-be jobs without changing the outbox.",
    )
    parser.add_argument(
        "--batch-size",
        type=_batch_size,
        default=DEFAULT_BATCH_SIZE,
        help=(
            "Maximum new reminder jobs enqueued "
            f"(default: {DEFAULT_BATCH_SIZE}, max: {MAX_BATCH_SIZE})."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = schedule_consultation_reminders(
            dry_run=args.dry_run,
            batch_size=args.batch_size,
        )
    except Exception as exc:
        # Never print exception messages: database/provider details may contain
        # credentials or user data.
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "consultation_reminder_scheduling_failed",
                    "error_type": type(exc).__name__,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 1

    print(json.dumps(report, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
