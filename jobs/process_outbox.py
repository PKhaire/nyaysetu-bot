"""Run a bounded batch of durable NyaySetu background jobs."""

from services.outbox_service import get_outbox_health, process_pending_jobs


CRITICAL_EXIT_CODE = 2


def main() -> int:
    completed, attempted_not_completed = process_pending_jobs()
    health = get_outbox_health()
    print(
        f"outbox_completed={completed} "
        f"outbox_attempted_not_completed={attempted_not_completed} "
        f"outbox_backlog={health['backlog_count']} "
        f"outbox_ready={health['ready_count']} "
        f"outbox_deferred={health['deferred_count']} "
        f"outbox_running={health['running_count']} "
        f"outbox_dead={health['dead_count']} "
        f"outbox_oldest_age_seconds={health['oldest_age_seconds']}"
    )

    # A future-available PENDING job is a deliberate retry schedule, not a cron
    # failure. Work that is still due after the bounded drain, or any DEAD job,
    # requires operator attention and a non-zero process result.
    if health["ready_count"] or health["dead_count"]:
        print("outbox_status=critical")
        return CRITICAL_EXIT_CODE

    print(
        "outbox_status=deferred"
        if health["backlog_count"]
        else "outbox_status=healthy"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
