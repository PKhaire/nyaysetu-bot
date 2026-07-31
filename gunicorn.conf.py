"""Production Gunicorn policy for the NyaySetu webhook service.

Keep process topology here rather than duplicating flags across deployment
surfaces. NyaySetu still has process-local ordering and rate-limit safeguards,
so increasing the worker count is unsafe until those controls move to shared
infrastructure.
"""

from __future__ import annotations

import os


bind = f"0.0.0.0:{os.getenv('PORT', '10000')}"

# One process is an intentional correctness constraint. Threads retain bounded
# I/O concurrency for Meta, Razorpay, and AI provider requests.
workers = 1
worker_class = "gthread"
threads = 8
worker_connections = 64
backlog = 128

timeout = 60
graceful_timeout = 30
keepalive = 5

max_requests = 1_000
max_requests_jitter = 100

preload_app = False
accesslog = "-"
errorlog = "-"
capture_output = True
loglevel = os.getenv("LOG_LEVEL", "INFO").lower()

# Use U (path only), not r or q. Query strings can contain webhook verification
# tokens and must never enter access logs. Referrer is deliberately omitted for
# the same reason.
access_log_format = (
    '%(h)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(b)s '
    '%(M)sms "%(a)s" request_id="%({x-request-id}o)s"'
)


def on_starting(server) -> None:
    """Refuse an accidental multi-process override."""

    configured_workers = server.cfg.workers
    if hasattr(configured_workers, "value"):
        configured_workers = configured_workers.value
    if int(configured_workers) != 1:
        raise RuntimeError(
            "NyaySetu requires exactly one Gunicorn worker until all "
            "process-local coordination is moved to shared infrastructure."
        )
