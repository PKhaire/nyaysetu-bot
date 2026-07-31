from __future__ import annotations

import atexit
import os
import json
import logging
import time as time_module
import hmac
import hashlib
import re
import unicodedata
import uuid

from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore, Lock
from collections import defaultdict, deque
from datetime import datetime, time as dt_time, timedelta, timezone
from urllib.parse import urlsplit

from flask import Flask, g, jsonify, request
from config import (
    AI_CONSENT_VERSION,
    ALLOW_INSECURE_WEBHOOKS,
    ADMIN_TOKEN,
    AUTO_CREATE_SCHEMA,
    ENV,
    LOG_LEVEL,
    WHATSAPP_APP_SECRET,
    WHATSAPP_APP_SECRET_PREVIOUS,
    WHATSAPP_PHONE_ID,
    WHATSAPP_TOKEN,
    WHATSAPP_VERIFY_TOKEN,
    BOOKING_TERMS_VERSION,
    BOOKING_PRICE,
    CANCELLATION_POLICY_URL,
    RAZORPAY_MODE,
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET,
    RAZORPAY_WEBHOOK_SECRET,
    RAZORPAY_WEBHOOK_SECRET_PREVIOUS,
    REFUND_POLICY_URL,
    MAINTENANCE_MODE,
    MAINTENANCE_ADMIN_BYPASS,
    AUTO_SEND_RECEIPTS,
    BOOKING_NOTIFICATION_EMAILS,
    SUPPORT_NOTIFICATION_EMAILS,
    SUPPORT_SLA_HOURS,
    SUPPORT_EMAIL,
    AI_SAFETY_IDENTIFIER_SECRET,
    AI_CALL_COOLDOWN_SECONDS,
    GLOBAL_REQUEST_LIMIT,
    GLOBAL_REQUEST_WINDOW_SECONDS,
    INBOUND_MESSAGE_LEASE_SECONDS,
    INBOUND_USER_LOCK_TIMEOUT_SECONDS,
    LEGAL_CONTENT_REVIEWED_VERSION,
    LEGAL_CONTENT_REVIEWED_ON,
    LEGAL_CONTENT_VERSION,
    PRIVACY_EMAIL,
    PRIVACY_POLICY_URL,
    PROCESSED_MESSAGE_TTL_DAYS,
    TERMS_OF_SERVICE_URL,
    USER_MESSAGE_LIMIT,
    USER_MESSAGE_WINDOW_SECONDS,
    SENDGRID_API_KEY,
    SENDGRID_FROM_EMAIL,
    WEBHOOK_EVENT_TTL_DAYS,
    WEBHOOK_MAX_PAYLOAD_BYTES,
    WEBHOOK_REPLAY_WINDOW_SECONDS,
)
from location_service import detect_district_and_state
from models import (
    User,
    Booking,
    BookingFulfillment,
    CategoryAnalytics,
    BookingStatus,
    Feedback,
    InboundMessageEvent,
    PaymentReconciliation,
    SupportRequest,
    UserConsent,
    WebhookEvent,
    utc_now,
)
from db import (
    EXPECTED_SCHEMA_REVISION,
    SessionLocal,
    get_db_health,
    get_schema_revision,
    init_db,
)
from sqlalchemy.exc import IntegrityError
from admin import admin_bp
from category_labels import CATEGORY_LABELS
from subcategory_labels import SUBCATEGORY_LABELS
from utils.date_utils import format_date_readable
from utils.i18n import t
from services.whatsapp_service import (
    is_ambiguous_delivery_failure,
    is_retryable_delivery_failure,
    send_text as _wa_send_text,
    send_buttons as _wa_send_buttons,
    send_typing_on as _wa_send_typing_on,
    send_typing_off as _wa_send_typing_off,
    send_list_picker as _wa_send_list_picker,
    send_payment_receipt_pdf as _wa_send_payment_receipt_pdf,
)
from services.receipt_service import generate_pdf_receipt
from services.ai_router import ai_reply_router
from services.booking_service import (
    IST,
    SLOT_START_HOUR,
    generate_dates_calendar,
    generate_slots_calendar,
    create_booking_temp,
    mark_booking_as_paid,
    payment_capacity_conflict,
    SLOT_MAP,
    expire_old_pending_bookings,
)
from services.engagement_service import (
    HOME_BUTTON_IDS,
    MORE_MENU_IDS,
    booking_status_message,
    home_buttons,
    latest_booking,
    latest_booking_with_statuses,
    legal_guide_message,
    legal_guide_rows,
    legal_guide_subcategory_rows,
    more_menu_rows,
    preparation_message,
    privacy_message,
    support_contact_message,
)
from services.legal_knowledge import (
    CATEGORY_SUBCATEGORIES,
    guide_feedback_buttons,
    parse_guide_feedback_id,
    parse_guide_id,
    ui as legal_ui,
)
from services.analytics_service import record_event
from services.fulfillment_service import ensure_booking_fulfillment
from services.outbox_service import (
    CONVERSATION_DELIVERY_KIND,
    enqueue_job,
    process_job,
)
from services.payment_reconciliation_service import (
    fetch_current_razorpay_capture,
    lock_matching_payment_reconciliations,
    validate_current_razorpay_capture,
)

# ===============================
# APP
# ===============================
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO)
)
logger = logging.getLogger("app")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = WEBHOOK_MAX_PAYLOAD_BYTES
if AUTO_CREATE_SCHEMA:
    init_db()

# ===============================
# CONFIG
# ===============================
FREE_AI_LIMIT = 5
FREE_AI_SOFT_PROMPT_AT = 4
# ===============================
# RATE LIMITING CONFIG
# ===============================
USER_MSG_LIMIT = USER_MESSAGE_LIMIT
USER_MSG_WINDOW = USER_MESSAGE_WINDOW_SECONDS
AI_CALL_COOLDOWN = AI_CALL_COOLDOWN_SECONDS
GLOBAL_REQ_LIMIT = GLOBAL_REQUEST_LIMIT
GLOBAL_REQ_WINDOW = GLOBAL_REQUEST_WINDOW_SECONDS

# ===============================
# RATE LIMITING STORES (IN-MEMORY)
# ===============================
user_message_times = defaultdict(lambda: deque())
user_last_ai_call = {}
global_request_times = deque()
_rate_limit_guard = Lock()
_rate_limit_notice_times: dict[tuple[str, str], float] = {}
_rate_limit_last_cleanup = 0.0
_RATE_LIMIT_CLEANUP_INTERVAL_SECONDS = 300.0
_RATE_LIMIT_STATE_MAX_KEYS = 100_000

# The Render topology intentionally uses one Gunicorn worker with threads.
# Serialize messages from the same WhatsApp account inside that process so two
# rapid replies cannot mutate a conversation state out of order.
_user_processing_locks: dict[str, tuple[Lock, int]] = {}
_user_processing_locks_guard = Lock()
_outbox_executor = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="nyaysetu-outbox",
)
_OUTBOX_FAST_PATH_MAX_IN_FLIGHT = 32
_outbox_submission_slots = BoundedSemaphore(
    value=_OUTBOX_FAST_PATH_MAX_IN_FLIGHT
)
atexit.register(
    _outbox_executor.shutdown,
    wait=False,
    cancel_futures=False,
)


def _run_outbox_job(job_id: int) -> None:
    try:
        process_job(job_id)
    finally:
        _outbox_submission_slots.release()


def submit_outbox_job(job_id: int) -> bool:
    """Best-effort low-latency kick; the durable worker remains authoritative."""

    if not _outbox_submission_slots.acquire(blocking=False):
        return False
    try:
        _outbox_executor.submit(_run_outbox_job, job_id)
    except RuntimeError:
        _outbox_submission_slots.release()
        # Interpreter/service shutdown can reject new work. The committed
        # outbox row remains available for the independent worker.
        logger.info("Outbox fast path unavailable during shutdown")
        return False
    except Exception:
        _outbox_submission_slots.release()
        raise
    return True

# ===============================
# MAINTENANCE DEDUPE (IN-MEMORY)
# ===============================
maintenance_last_sent = {}
MAINTENANCE_DEDUPE_SECONDS = 3

WELCOME_KEYWORDS = {"hi", "hii", "hie", "hello", "hey", "start"}

HOME_KEYWORDS = {
    "hi",
    "hii",
    "hie",
    "hello",
    "hey",
    "help",
    "menu",
    "main menu",
    "home",
}

RESTART_KEYWORDS = {
    "restart", "reset", "start over", "begin again",
    "cancel", "stop", "exit"
}

BOOKING_KEYWORDS = {
    "book",
    "book consultation",
    "book appointment",
    "consult",
    "consultation",
    "lawyer",
}

app.register_blueprint(admin_bp)


class WhatsAppDeliveryError(RuntimeError):
    """Raised when Meta did not accept an outbound message."""

    def __init__(
        self,
        error: str,
        *,
        operation: str | None = None,
        payload: dict | None = None,
        retryable: bool = False,
        ambiguous: bool = False,
    ):
        super().__init__(error)
        self.error = error
        self.operation = operation
        self.payload = payload
        self.retryable = retryable
        self.ambiguous = ambiguous


def _require_whatsapp_delivery(
    result,
    *,
    operation: str | None = None,
    payload: dict | None = None,
):
    if not isinstance(result, dict) or not result.get("ok"):
        error = (
            result.get("error", "unknown")
            if isinstance(result, dict)
            else "invalid_result"
        )
        raise WhatsAppDeliveryError(
            str(error)[:120],
            operation=operation,
            payload=payload,
            retryable=is_retryable_delivery_failure(result),
            ambiguous=is_ambiguous_delivery_failure(result),
        )
    return result


def send_text(wa_id: str, body: str):
    return _require_whatsapp_delivery(
        _wa_send_text(wa_id, body),
        operation="text",
        payload={"to": wa_id, "body": body},
    )


def send_buttons(wa_id: str, body: str, buttons: list):
    return _require_whatsapp_delivery(
        _wa_send_buttons(wa_id, body, buttons),
        operation="buttons",
        payload={
            "to": wa_id,
            "body": body,
            "buttons": buttons,
        },
    )


def send_typing_on(*args, **kwargs):
    return _require_whatsapp_delivery(_wa_send_typing_on(*args, **kwargs))


def send_typing_off(*args, **kwargs):
    return _require_whatsapp_delivery(_wa_send_typing_off(*args, **kwargs))


def send_list_picker(
    wa_id: str,
    header: str,
    body: str,
    rows: list,
    section_title: str = "Options",
):
    return _require_whatsapp_delivery(
        _wa_send_list_picker(
            wa_id,
            header=header,
            body=body,
            rows=rows,
            section_title=section_title,
        ),
        operation="list",
        payload={
            "to": wa_id,
            "header": header,
            "body": body,
            "rows": rows,
            "section_title": section_title,
        },
    )


def send_payment_receipt_pdf(*args, **kwargs):
    return _require_whatsapp_delivery(
        _wa_send_payment_receipt_pdf(*args, **kwargs)
    )


@app.before_request
def apply_request_guards():
    request_id = request.headers.get("X-Request-ID", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", request_id):
        request_id = uuid.uuid4().hex
    g.request_id = request_id

    if (
        request.content_length is not None
        and request.content_length > WEBHOOK_MAX_PAYLOAD_BYTES
    ):
        return jsonify({"error": "payload_too_large"}), 413
    return None


@app.after_request
def add_response_headers(response):
    response.headers["X-Request-ID"] = getattr(g, "request_id", uuid.uuid4().hex)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if (
        request.path == "/webhook"
        and request.method == "POST"
        and getattr(g, "inbound_message_claimed", False)
        and response.status_code < 500
    ):
        if not finish_inbound_message(
            getattr(g, "inbound_message_id", None)
        ):
            # Do not acknowledge an event whose durable terminal state could
            # not be recorded. Its lease makes a later Meta retry recoverable.
            response.status_code = 503

    if (
        request.path == "/webhook"
        and request.method == "POST"
        and getattr(g, "whatsapp_batch_has_more", False)
        and response.status_code < 400
    ):
        # Meta retries the complete batch. On the retry we select the next
        # message whose durable ID has not yet been processed.
        response.status_code = 503
    return response

# ===============================
# STATES
# ===============================
NORMAL = "NORMAL"
ASK_LANGUAGE = "ASK_LANGUAGE"
ASK_AI_OR_BOOK = "ASK_AI_OR_BOOK"
ASK_NAME = "ASK_NAME"
ASK_DISTRICT = "ASK_DISTRICT"
CONFIRM_LOCATION = "CONFIRM_LOCATION"
ASK_CATEGORY = "ASK_CATEGORY"
ASK_SUBCATEGORY = "ASK_SUBCATEGORY"
ASK_DATE = "ASK_DATE"
ASK_SLOT = "ASK_SLOT"
WAITING_PAYMENT = "WAITING_PAYMENT"
PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
FLOW_VERIFY_DETAILS = "VERIFY_DETAILS"
ASK_AI_CONSENT = "ASK_AI_CONSENT"
REVIEW_SERVICE = "REVIEW_SERVICE"
REVIEW_BOOKING = "REVIEW_BOOKING"
ASK_SUPPORT_MESSAGE = "ASK_SUPPORT_MESSAGE"
ASK_FEEDBACK_RATING = "ASK_FEEDBACK_RATING"
ASK_FEEDBACK_COMMENT = "ASK_FEEDBACK_COMMENT"
BTN_ASK_AI = "ASK_AI"
BTN_BOOK_CONSULT = "BOOK_CONSULT"
BTN_DETAILS_OK = "DETAILS_OK"
BTN_DETAILS_EDIT = "DETAILS_EDIT"
BTN_AI_CONSENT = "ai_consent_yes"
BTN_AI_DECLINE = "ai_consent_no"
BTN_BOOKING_SCOPE_CONTINUE = "booking_scope_continue"
BTN_BOOKING_SCOPE_CANCEL = "booking_scope_cancel"
BTN_REVIEW_PAY = "review_pay"
BTN_REVIEW_CHANGE_TIME = "review_change_time"
BTN_REVIEW_CANCEL = "review_cancel"
BTN_SUPPORT_CANCEL = "support_cancel"


# ===============================
# HELPERS
# ===============================
# =================================================
# WHATSAPP SIGNATURE VERIFICATION (PRODUCTION)
# =================================================
def verify_whatsapp_signature():
    signature = request.headers.get("X-Hub-Signature-256")
    if not signature:
        return False

    try:
        sha_name, signature_hash = signature.split("=")
        if sha_name != "sha256":
            return False
    except Exception:
        return False

    secrets = tuple(
        secret
        for secret in (
            WHATSAPP_APP_SECRET,
            WHATSAPP_APP_SECRET_PREVIOUS,
        )
        if secret
    )
    if not secrets:
        logger.critical("WHATSAPP_APP_SECRET missing in production")
        return False

    payload = request.data
    return any(
        hmac.compare_digest(
            hmac.new(
                secret.encode("utf-8"),
                payload,
                hashlib.sha256,
            ).hexdigest(),
            signature_hash,
        )
        for secret in secrets
    )

def get_db():
    return SessionLocal()

def get_flow_state(user):
    return user.flow_state

def set_flow_state(db, user, value):
    user.flow_state = value
    db.commit()

def save_state(db, user, state):
    set_flow_state(db, user, state)

def generate_case_id():
    return f"NS-{uuid.uuid4().hex[:8].upper()}"

def get_or_create_user(db, wa_id):
    user = db.query(User).filter_by(whatsapp_id=wa_id).first()

    if not user:
        user = User(
            whatsapp_id=wa_id,
            case_id=generate_case_id(),
            language=None,
            flow_state=NORMAL,
            ai_enabled=False,
            free_ai_count=0,
            welcome_sent=False,     
            created_at=utc_now(),
        )
        db.add(user)
        try:
            db.commit()
            db.refresh(user)
            record_event("user_created", user_id=user.id)
        except IntegrityError:
            # Meta may deliver two first messages concurrently. The unique
            # WhatsApp ID is the source of truth; fetch the winner.
            db.rollback()
            user = db.query(User).filter_by(whatsapp_id=wa_id).first()
            if not user:
                raise

    return user


# ===============================
# RATE LIMIT HELPERS
# ===============================
def _oldest_message_time(wa_id: str) -> float:
    times = user_message_times.get(wa_id)
    return times[-1] if times else 0.0


def _trim_oldest_keys(mapping, timestamp_for_key) -> None:
    overflow = len(mapping) - _RATE_LIMIT_STATE_MAX_KEYS
    if overflow <= 0:
        return
    oldest = sorted(mapping, key=timestamp_for_key)[:overflow]
    for key in oldest:
        mapping.pop(key, None)


def _prune_rate_limit_state(now: float) -> None:
    """Bound idle per-user state; caller must hold ``_rate_limit_guard``."""

    global _rate_limit_last_cleanup

    state_is_bounded = all(
        len(mapping) <= _RATE_LIMIT_STATE_MAX_KEYS
        for mapping in (
            user_message_times,
            user_last_ai_call,
            _rate_limit_notice_times,
        )
    )
    cleanup_elapsed = now - _rate_limit_last_cleanup
    if (
        state_is_bounded
        and 0 <= cleanup_elapsed < _RATE_LIMIT_CLEANUP_INTERVAL_SECONDS
    ):
        return

    for wa_id, times in list(user_message_times.items()):
        if times and times[-1] > now:
            times.clear()
        while times and now - times[0] > USER_MSG_WINDOW:
            times.popleft()
        if not times:
            user_message_times.pop(wa_id, None)

    ai_idle_ttl = max(300.0, float(AI_CALL_COOLDOWN) * 2)
    for wa_id, last_call in list(user_last_ai_call.items()):
        if last_call > now or now - last_call > ai_idle_ttl:
            user_last_ai_call.pop(wa_id, None)

    notice_idle_ttl = max(
        300.0,
        float(USER_MSG_WINDOW),
        float(GLOBAL_REQ_WINDOW),
    )
    for key, last_sent in list(_rate_limit_notice_times.items()):
        if last_sent > now or now - last_sent > notice_idle_ttl:
            _rate_limit_notice_times.pop(key, None)

    _trim_oldest_keys(user_message_times, _oldest_message_time)
    _trim_oldest_keys(
        user_last_ai_call,
        lambda wa_id: user_last_ai_call[wa_id],
    )
    _trim_oldest_keys(
        _rate_limit_notice_times,
        lambda key: _rate_limit_notice_times[key],
    )
    _rate_limit_last_cleanup = now


def is_user_rate_limited(wa_id):
    now = time_module.time()
    with _rate_limit_guard:
        _prune_rate_limit_state(now)
        times = user_message_times[wa_id]

        while times and now - times[0] > USER_MSG_WINDOW:
            times.popleft()

        if len(times) >= USER_MSG_LIMIT:
            return True

        times.append(now)
        _trim_oldest_keys(user_message_times, _oldest_message_time)
        return False


def is_ai_rate_limited(wa_id):
    now = time_module.time()
    with _rate_limit_guard:
        last_call = user_last_ai_call.get(wa_id, 0)

        if now - last_call < AI_CALL_COOLDOWN:
            return True

        user_last_ai_call[wa_id] = now
        _trim_oldest_keys(
            user_last_ai_call,
            lambda key: user_last_ai_call[key],
        )
        return False


def is_global_rate_limited():
    now = time_module.time()
    with _rate_limit_guard:
        if global_request_times and global_request_times[-1] > now:
            global_request_times.clear()
        while (
            global_request_times
            and now - global_request_times[0] > GLOBAL_REQ_WINDOW
        ):
            global_request_times.popleft()

        if len(global_request_times) >= GLOBAL_REQ_LIMIT:
            return True

        global_request_times.append(now)
        return False


def should_send_rate_limit_notice(
    scope: str,
    wa_id: str,
    cooldown_seconds: float,
) -> bool:
    """Allow at most one rate-limit response per user and limit window."""

    now = time_module.time()
    key = (str(scope), str(wa_id))
    with _rate_limit_guard:
        last_sent = _rate_limit_notice_times.get(key, 0)
        if now - last_sent < max(1.0, float(cooldown_seconds)):
            return False
        _rate_limit_notice_times[key] = now
        _trim_oldest_keys(
            _rate_limit_notice_times,
            lambda notice_key: _rate_limit_notice_times[notice_key],
        )
        return True


def should_send_maintenance_notice(wa_id: str, now: float) -> bool:
    """Deduplicate and bound process-local maintenance acknowledgements."""

    with _rate_limit_guard:
        stale_before = now - max(60.0, MAINTENANCE_DEDUPE_SECONDS * 10)
        for key, last_sent in list(maintenance_last_sent.items()):
            if last_sent > now or last_sent < stale_before:
                maintenance_last_sent.pop(key, None)
        last_sent = maintenance_last_sent.get(wa_id, 0)
        if now - last_sent < MAINTENANCE_DEDUPE_SECONDS:
            return False
        maintenance_last_sent[wa_id] = now
        _trim_oldest_keys(
            maintenance_last_sent,
            lambda key: maintenance_last_sent[key],
        )
        return True

def _acquire_user_processing_lock(wa_id: str) -> Lock | None:
    """Acquire a bounded in-process lock for the configured one-worker topology."""

    with _user_processing_locks_guard:
        entry = _user_processing_locks.get(wa_id)
        if entry:
            lock, references = entry
            _user_processing_locks[wa_id] = (lock, references + 1)
        else:
            lock = Lock()
            _user_processing_locks[wa_id] = (lock, 1)

    acquired = lock.acquire(timeout=INBOUND_USER_LOCK_TIMEOUT_SECONDS)
    if acquired:
        return lock

    with _user_processing_locks_guard:
        current_lock, references = _user_processing_locks.get(
            wa_id,
            (lock, 1),
        )
        if references <= 1:
            _user_processing_locks.pop(wa_id, None)
        else:
            _user_processing_locks[wa_id] = (
                current_lock,
                references - 1,
            )
    return None


def _release_user_processing_lock(wa_id: str, lock: Lock | None) -> None:
    if lock is None:
        return

    lock.release()
    with _user_processing_locks_guard:
        current = _user_processing_locks.get(wa_id)
        if not current or current[0] is not lock:
            return
        references = current[1] - 1
        if references <= 0:
            _user_processing_locks.pop(wa_id, None)
        else:
            _user_processing_locks[wa_id] = (lock, references)


def claim_inbound_message(db, message_id: str | None) -> str:
    """Return CLAIMED, DONE, or BUSY for a durable inbound message ID."""

    if not message_id:
        return "CLAIMED"

    now = utc_now()
    lease_expires_at = now + timedelta(
        seconds=INBOUND_MESSAGE_LEASE_SECONDS
    )
    expires_at = now + timedelta(days=PROCESSED_MESSAGE_TTL_DAYS)

    event = (
        db.query(InboundMessageEvent)
        .filter(InboundMessageEvent.message_id == message_id)
        .with_for_update()
        .first()
    )
    if event:
        if event.status == "DONE":
            return "DONE"
        if (
            event.status == "PROCESSING"
            and event.lease_expires_at
            and event.lease_expires_at > now
        ):
            return "BUSY"

        event.status = "PROCESSING"
        event.attempts = (event.attempts or 0) + 1
        event.last_error = None
        event.lease_expires_at = lease_expires_at
        event.expires_at = expires_at
        db.commit()
        return "CLAIMED"

    event = InboundMessageEvent(
        message_id=message_id,
        status="PROCESSING",
        attempts=1,
        lease_expires_at=lease_expires_at,
        expires_at=expires_at,
    )
    db.add(event)
    try:
        db.commit()
        return "CLAIMED"
    except IntegrityError:
        db.rollback()
        concurrent = (
            db.query(InboundMessageEvent)
            .filter(InboundMessageEvent.message_id == message_id)
            .first()
        )
        if concurrent and concurrent.status == "DONE":
            return "DONE"
        return "BUSY"


def finish_inbound_message(message_id: str | None) -> bool:
    if not message_id:
        return True

    db = get_db()
    try:
        event = (
            db.query(InboundMessageEvent)
            .filter(InboundMessageEvent.message_id == message_id)
            .first()
        )
        if not event:
            return False
        now = utc_now()
        event.status = "DONE"
        event.last_error = None
        event.lease_expires_at = None
        event.processed_at = now
        event.expires_at = now + timedelta(days=PROCESSED_MESSAGE_TTL_DAYS)
        db.commit()
        return True
    except Exception:
        db.rollback()
        logger.exception(
            "Unable to complete inbound message claim | request_id=%s",
            getattr(g, "request_id", "unknown"),
        )
        return False
    finally:
        db.close()


def fail_inbound_message(
    message_id: str | None,
    reason: str,
) -> None:
    if not message_id:
        return

    db = get_db()
    try:
        event = (
            db.query(InboundMessageEvent)
            .filter(InboundMessageEvent.message_id == message_id)
            .first()
        )
        if event and event.status != "DONE":
            event.status = "FAILED"
            event.last_error = reason[:500]
            event.lease_expires_at = None
            event.expires_at = utc_now() + timedelta(
                days=PROCESSED_MESSAGE_TTL_DAYS
            )
            db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Unable to fail inbound message claim | request_id=%s",
            getattr(g, "request_id", "unknown"),
        )
    finally:
        db.close()


def complete_inbound_after_delivery_failure(
    db,
    message_id: str | None,
    failure: WhatsAppDeliveryError,
) -> tuple[bool, int | None]:
    """Finish business processing and durably defer only a safe failed send."""

    if not message_id or not failure.operation or not failure.payload:
        return False, None

    try:
        event = (
            db.query(InboundMessageEvent)
            .filter(InboundMessageEvent.message_id == message_id)
            .with_for_update()
            .first()
        )
        if not event:
            return False, None

        job_id = None
        if failure.retryable:
            delivery_payload = dict(failure.payload)
            delivery_payload["operation"] = failure.operation
            message_digest = hashlib.sha256(message_id.encode()).hexdigest()
            job = enqueue_job(
                db,
                CONVERSATION_DELIVERY_KIND,
                delivery_payload,
                dedupe_key=f"inbound-delivery:{message_digest}",
            )
            job_id = job.id

        now = utc_now()
        event.status = "DONE"
        event.lease_expires_at = None
        event.processed_at = now
        event.expires_at = now + timedelta(days=PROCESSED_MESSAGE_TTL_DAYS)
        if failure.retryable:
            outcome = "OutboundDeliveryQueued"
        elif failure.ambiguous:
            outcome = "OutboundDeliveryAmbiguousNotRetried"
        else:
            outcome = "OutboundDeliveryRejected"
        event.last_error = f"{outcome}:{failure.error}"[:500]
        # This single transaction preserves any state mutation made immediately
        # before the failed send, the terminal inbox claim, and its retry job.
        db.commit()
        return True, job_id
    except Exception:
        db.rollback()
        logger.exception(
            "Unable to persist failed outbound delivery | request_id=%s",
            getattr(g, "request_id", "unknown"),
        )
        return False, None


# =================================================
# Name
# =================================================

BUSINESS_KEYWORDS = {"pvt", "ltd", "limited", "company", "llp", "inc", "com", "in", "gov"}

def normalize_name(raw: str):
    if not raw:
        return None

    # Normalize unicode (removes zero-width chars)
    name = unicodedata.normalize("NFKC", raw)

    # Remove leading/trailing spaces & punctuation
    name = name.strip(" .,-")

    # Collapse multiple spaces
    name = re.sub(r"\s+", " ", name)

    # Reject digits
    if re.search(r"\d", name):
        return None

    # Reject forbidden symbols
    if re.search(r"[\/@#!$%^&*_=+<>?{}[\]|\\]", name):
        return None

    # Allow only letters, spaces and dot
    if not re.fullmatch(r"[^\W\d_][\w\s.'-]*", name, re.UNICODE):
        return None

    # Reject business names
    lowered = name.lower()
    for word in BUSINESS_KEYWORDS:
        if word in lowered.split():
            return None

    # Optional: Title Case
    name = name.title()

    # Minimum length after cleanup
    if len(name) < 2:
        return None

    return name


def is_booking_intent(text: str) -> bool:
    """Match an explicit booking command without hijacking normal AI questions."""

    normalized = re.sub(r"[^a-z\s]", " ", (text or "").lower())
    normalized = " ".join(normalized.split())
    return normalized in BOOKING_KEYWORDS


def masked_identifier(value: str) -> str:
    value = str(value or "")
    if len(value) <= 6:
        return "***"
    return f"{value[:3]}***{value[-2:]}"


def _valid_whatsapp_message_id(value) -> bool:
    return bool(
        isinstance(value, str)
        and 1 <= len(value) <= 255
        and value == value.strip()
        and not any(character.isspace() for character in value)
        and all(ord(character) >= 32 for character in value)
    )


def _valid_whatsapp_sender(value: str) -> bool:
    return bool(re.fullmatch(r"\+?[0-9]{6,32}", str(value or "")))


def extract_whatsapp_messages(payload: dict) -> list[tuple[dict, dict, str]]:
    """Flatten Meta's batched entry/change/message envelope safely."""

    envelopes: list[tuple[dict, dict, str]] = []
    for entry in payload.get("entry", []) if isinstance(payload, dict) else []:
        for change in entry.get("changes", []) if isinstance(entry, dict) else []:
            value = change.get("value", {}) if isinstance(change, dict) else {}
            if not isinstance(value, dict):
                continue
            contacts = value.get("contacts") or []
            contact_wa_id = ""
            if contacts and isinstance(contacts[0], dict):
                contact_wa_id = str(contacts[0].get("wa_id") or "")
            for message in value.get("messages") or []:
                if not isinstance(message, dict):
                    continue
                wa_id = str(message.get("from") or contact_wa_id)
                if wa_id:
                    envelopes.append((value, message, wa_id))
    return envelopes


def clear_booking_draft(user) -> None:
    user.temp_date = None
    user.temp_slot = None
    user.last_payment_link = None


def send_home(wa_id, user) -> None:
    send_buttons(
        wa_id,
        t(user, "home_menu"),
        home_buttons(user),
    )


def send_more_options(wa_id, user) -> None:
    send_list_picker(
        wa_id,
        header=t(user, "more_menu_header"),
        body=t(user, "more_menu_body"),
        section_title=t(user, "more_menu_section"),
        rows=more_menu_rows(user),
    )


def send_language_picker(wa_id, user) -> None:
    send_buttons(
        wa_id,
        t(user, "welcome", case_id=user.case_id),
        [
            {"id": "lang_en", "title": "English"},
            {"id": "lang_hi", "title": "Hindi / Hinglish"},
            {"id": "lang_mr", "title": "मराठी"},
        ],
    )


def begin_ai_consent(db, user, wa_id) -> None:
    user.ai_enabled = False
    user.flow_state = ASK_AI_CONSENT
    db.commit()
    send_buttons(
        wa_id,
        t(
            user,
            "ai_consent_prompt",
            policy_version=AI_CONSENT_VERSION,
            privacy_url=PRIVACY_POLICY_URL or "N/A",
        ),
        [
            {"id": BTN_AI_CONSENT, "title": t(user, "ai_consent_accept")},
            {"id": BTN_AI_DECLINE, "title": t(user, "ai_consent_decline")},
        ],
    )


def record_user_consent(
    db,
    user,
    *,
    purpose: str,
    policy_version: str,
) -> UserConsent:
    consent = (
        db.query(UserConsent)
        .filter(
            UserConsent.user_id == user.id,
            UserConsent.purpose == purpose,
            UserConsent.policy_version == policy_version,
        )
        .first()
    )
    if not consent:
        consent = UserConsent(
            user_id=user.id,
            purpose=purpose,
            policy_version=policy_version,
            source="whatsapp",
        )
        db.add(consent)
    consent.granted = True
    consent.consented_at = utc_now()
    consent.revoked_at = None
    db.flush()
    return consent


def begin_booking_scope_review(db, user, wa_id) -> None:
    user.ai_enabled = False
    clear_booking_draft(user)
    user.flow_state = REVIEW_SERVICE
    db.commit()
    send_buttons(
        wa_id,
        t(user, "booking_scope", amount=BOOKING_PRICE),
        [
            {
                "id": BTN_BOOKING_SCOPE_CONTINUE,
                "title": t(user, "continue_booking"),
            },
            {
                "id": BTN_BOOKING_SCOPE_CANCEL,
                "title": t(user, "back_to_home"),
            },
        ],
    )


def send_booking_review(db, user, wa_id) -> None:
    user.flow_state = REVIEW_BOOKING
    db.commit()
    send_buttons(
        wa_id,
        t(
            user,
            "review_before_payment",
            name=user.name or "N/A",
            category=get_category_label(user.category, user),
            district=user.district_name or "N/A",
            state=user.state_name or "N/A",
            date=format_date_readable(user.temp_date),
            slot=SLOT_MAP.get(user.temp_slot, "N/A"),
            amount=BOOKING_PRICE,
            terms_url=TERMS_OF_SERVICE_URL or "N/A",
            refund_url=REFUND_POLICY_URL or "N/A",
            cancellation_url=CANCELLATION_POLICY_URL or "N/A",
            privacy_url=PRIVACY_POLICY_URL or "N/A",
            policy_version=BOOKING_TERMS_VERSION,
        ),
        [
            {"id": BTN_REVIEW_PAY, "title": t(user, "pay_now")},
            {
                "id": BTN_REVIEW_CHANGE_TIME,
                "title": t(user, "change_time"),
            },
            {"id": BTN_REVIEW_CANCEL, "title": t(user, "cancel_booking")},
        ],
    )


def send_pending_payment_options(user, wa_id, booking=None) -> None:
    """Keep a pending payer oriented without discarding their payment link."""

    payment_link = user.last_payment_link
    if not payment_link and booking is not None:
        # The provider short URL is intentionally stored only on the user.
        # A missing URL therefore routes the user to support instead of
        # creating a second booking/payment request.
        send_buttons(
            wa_id,
            t(user, "payment_link_error"),
            [
                {
                    "id": MORE_MENU_IDS["status"],
                    "title": t(user, "check_payment_status"),
                },
                {
                    "id": "payment_help",
                    "title": t(user, "payment_help"),
                },
            ],
        )
        return

    send_buttons(
        wa_id,
        t(user, "payment_waiting_help"),
        [
            {
                "id": MORE_MENU_IDS["status"],
                "title": t(user, "check_payment_status"),
            },
            {
                "id": "payment_help",
                "title": t(user, "payment_help"),
            },
        ],
    )
    if payment_link:
        send_text(
            wa_id,
            f"💳 {t(user, 'payment_link_text')}\n{payment_link}",
        )


def send_available_dates(db, user, wa_id) -> bool:
    rows = generate_dates_calendar(skip_today=False, db=db)
    if not rows:
        send_text(wa_id, t(user, "no_slots"))
        return False
    send_list_picker(
        wa_id,
        header=t(user, "select_date"),
        body=t(user, "available_dates"),
        rows=rows,
        section_title=t(user, "next_7_days"),
    )
    return True


def send_available_slots(db, user, wa_id, date_str: str) -> bool:
    rows = generate_slots_calendar(date_str, db=db)
    if not rows:
        send_text(wa_id, t(user, "no_slots"))
        return False
    readable_date = format_date_readable(date_str)
    for row in rows:
        row["description"] = t(user, "available_on", date=readable_date)
    send_list_picker(
        wa_id,
        header=f"{t(user, 'select_slot')} {readable_date}",
        body=t(user, "available_slots"),
        rows=rows,
        section_title=t(user, "time_slots"),
    )
    return True


def feedback_rows(user) -> list[dict[str, str]]:
    labels = {
        5: "5 ⭐ Excellent",
        4: "4 ⭐ Good",
        3: "3 ⭐ Okay",
        2: "2 ⭐ Needs work",
        1: "1 ⭐ Poor",
    }
    return [
        {
            "id": f"feedback::{rating}",
            "title": label,
            "description": t(user, "feedback_row_desc"),
        }
        for rating, label in labels.items()
    ]

# =================================================
# CATEGORY & SUB-CATEGORY HELPERS
# =================================================

def send_category_list(wa_id, user):
    rows = [
        {
            "id": f"cat_{category.lower().replace(' ', '_').replace('&', 'and')}",
            "title": get_category_label(category, user),
        }
        for category in CATEGORY_SUBCATEGORIES.keys()
    ]

    send_list_picker(
        wa_id,
        header=t(user, "select_category"),
        body=t(user, "choose_category"),
        section_title=t(user, "select_category"),
        rows=rows,
    )

def send_subcategory_list(db, wa_id, user, category):
    """
    Sends sub-categories strictly from CATEGORY_SUBCATEGORIES.
    Ensures 'General Legal Query' is always present.
    Category MUST be canonical key like: banking_and_finance
    """

    # ===============================
    # SAFETY GUARD — NEVER CRASH
    # ===============================
    if not category:
        logger.error(
            "send_subcategory_list called with category=None | wa_id=%s | state=%s",
            masked_identifier(wa_id),
            user.flow_state,
        )
        save_state(db, user, ASK_CATEGORY)
        send_category_list(wa_id, user)
        return

    # ===============================
    # NORMALIZE CATEGORY (DEFENSIVE)
    # ===============================
    # Handle accidental prefixes like "cat_banking_and_finance"
    if category.startswith("cat_"):
        category = category.replace("cat_", "", 1)

    # Display label (safe now)
    category_key = category.replace("_", " ").title()

    # ===============================
    # FETCH SUB-CATEGORIES
    # ===============================
    subcats = CATEGORY_SUBCATEGORIES.get(category_key, []).copy()

    # ✅ Ensure "General Legal Query" always exists
    if "General Legal Query" not in subcats:
        subcats.append("General Legal Query")

    # ===============================
    # BUILD WHATSAPP ROWS
    # ===============================
    rows = [
        {
            # ID FORMAT: subcat::<category_key>::<subcategory_key>
            "id": (
                "subcat::"
                f"{category}::"
                f"{sub.lower().replace(' ', '_').replace('/', '').replace('(', '').replace(')', '')}"
            ),
            # WhatsApp title limit = 24 chars
            "title": get_subcategory_label(sub, user)[:24],
        }
        for sub in subcats
    ]

    # ===============================
    # SEND LIST PICKER
    # ===============================
    send_list_picker(
        wa_id,
        header=t(user, "select_subcategory"),
        body=t(user, "choose_subcategory"),
        section_title=t(user, "select_subcategory"),
        rows=rows,
    )

def parse_subcategory_id(interactive_id: str):
    """
    Expected format:
    subcat::<category_key>::<subcategory_key>
    Example:
    subcat::banking_and_finance::not_sure_need_guidance
    """
    if not interactive_id.startswith("subcat::"):
        return None, None

    parts = interactive_id.split("::")
    if len(parts) != 3:
        return None, None

    _, category, subcategory = parts
    return category, subcategory

def get_category_label(category_key, user):
    """
    category_key: canonical key (e.g. banking_and_finance)
    """
    lang = user.language or "en"

    display_key = (
        category_key
        .replace("_and_", " & ")
        .replace("_", " ")
        .title()
    )

    return CATEGORY_LABELS.get(display_key, {}).get(lang, display_key)

def get_subcategory_label(subcategory, user):
    lang = user.language or "en"
    return SUBCATEGORY_LABELS.get(subcategory, {}).get(lang, subcategory)
    
def send_payment_receipt_again(db, wa_id):
    booking = (
        db.query(Booking)
        .filter(
            Booking.whatsapp_id == wa_id,
            Booking.status.in_(
                (BookingStatus.PAID, BookingStatus.COMPLETED)
            ),
        )
        .order_by(Booking.id.desc())
        .first()
    )

    if not booking:
        send_text(wa_id, "❌ No completed payment found.")
        return

    pdf_path = None
    try:
        pdf_path = generate_pdf_receipt(booking)
        send_payment_receipt_pdf(
            booking.whatsapp_id,
            pdf_path,
            booking_id=booking.id,
        )

        booking.receipt_sent = True
        db.commit()

    except Exception:
        db.rollback()
        logger.exception("Receipt resend failed | booking_id=%s", booking.id)
        send_text(
            wa_id,
            "⚠️ Unable to resend receipt right now. Please try later."
        )
    finally:
        if pdf_path and os.path.isfile(pdf_path):
            try:
                os.remove(pdf_path)
            except OSError:
                logger.warning(
                    "Temporary receipt cleanup failed | booking_id=%s",
                    booking.id,
                )

def send_verification_screen(db, user, wa_id):
    save_state(db, user, FLOW_VERIFY_DETAILS)
    send_buttons(
        wa_id,
        (
            f"{t(user, 'verify_details')}\n\n"
            f"👤 {user.name}\n"
            f"📍 {user.state_name}\n"
            f"🏙 {user.district_name}"
        ),
        [
            {"id": BTN_DETAILS_OK, "title": t(user, "verified_button")},
            {"id": BTN_DETAILS_EDIT, "title": t(user, "edit_details_button")},
        ],
    )
    
def get_booking_window(booking):
    """
    Returns timezone-aware (booking_start, booking_end) in Asia/Kolkata.
    or (None, None) if booking is invalid
    """

    # 1️⃣ Booking object must exist
    if not booking or not booking.date or not booking.slot_code:
        return None, None

    # 2️⃣ Normalize date
    booking_date = booking.date
    if isinstance(booking_date, str):
        try:
            booking_date = datetime.strptime(
                booking_date, "%Y-%m-%d"
            ).date()
        except ValueError:
            return None, None

    # 3️⃣ Resolve the 24-hour value from the canonical slot map. Parsing
    # "3_4" as an integer would incorrectly produce 03:00 instead of 15:00.
    start_hour = SLOT_START_HOUR.get(booking.slot_code)
    if start_hour is None:
        return None, None

    # 4️⃣ Compute window
    booking_start = datetime.combine(
        booking_date,
        dt_time(start_hour, 0),
        tzinfo=IST,
    )
    booking_end = booking_start + timedelta(hours=1)

    logger.debug(
        "BOOKING_WINDOW | booking_id=%s | date=%s | slot=%s | start=%s | end=%s",
        getattr(booking, "id", None),
        booking.date if booking else None,
        booking.slot_code if booking else None,
        booking_start,
        booking_end,
    )
    
    return booking_start, booking_end


def close_completed_consultation(db, user, wa_id) -> bool:
    """Request feedback only after an operator records actual fulfilment."""

    result = (
        db.query(BookingFulfillment, Booking)
        .join(Booking, Booking.id == BookingFulfillment.booking_id)
        .filter(
            Booking.whatsapp_id == wa_id,
            BookingFulfillment.status == "COMPLETED",
            BookingFulfillment.feedback_requested_at.is_(None),
        )
        .order_by(Booking.id.desc())
        .first()
    )
    if not result:
        return False
    fulfillment, completed_booking = result

    fulfillment.feedback_requested_at = utc_now()
    user.flow_state = ASK_FEEDBACK_RATING
    user.ai_enabled = False
    clear_booking_draft(user)
    db.commit()

    record_event(
        "consultation_completed",
        {
            "booking_id": completed_booking.id,
            "category": completed_booking.category,
        },
        user_id=user.id,
    )
    send_list_picker(
        wa_id,
        header=t(user, "feedback_header"),
        body=t(user, "feedback_prompt"),
        section_title=t(user, "feedback_section"),
        rows=feedback_rows(user),
    )
    return True

def has_completed_consultation(db, wa_id):
    booking = (
        db.query(Booking)
        .filter(
            Booking.whatsapp_id == wa_id,
            Booking.status.in_(
                (BookingStatus.PAID, BookingStatus.COMPLETED)
            ),
        )
        .order_by(Booking.id.desc())
        .first()
    )

    booking_start, booking_end = get_booking_window(booking)

    # 🔒 HARD SAFETY CHECK — NEVER COMPARE None
    if not booking_start or not booking_end:
        logger.warning(
            "CONSULTATION_CHECK_INVALID | wa_id=%s | booking_id=%s | start=%s | end=%s",
            masked_identifier(wa_id),
            getattr(booking, "id", None),
            booking_start,
            booking_end,
        )
        return False

    now = datetime.now(IST)

    logger.debug(
        "CONSULTATION_CHECK | wa_id=%s | now=%s | booking_end=%s | completed=%s",
        masked_identifier(wa_id),
        now,
        booking_end,
        now > booking_end,
    )

    return now > booking_end

def safe_header(text: str) -> str:
    # WhatsApp list headers do NOT allow markdown
    return (
        text
        .replace("*", "")
        .replace("_", "")
        .replace("~", "")
    )


_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _valid_email(value: str) -> bool:
    return bool(_EMAIL_PATTERN.fullmatch(str(value or "").strip()))


def _valid_https_url(value: str) -> bool:
    try:
        parsed = urlsplit(str(value or "").strip())
    except ValueError:
        return False
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
    )


def _valid_legal_review_date(value: str) -> bool:
    normalized = str(value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        return False
    try:
        reviewed_on = datetime.strptime(normalized, "%Y-%m-%d").date()
    except ValueError:
        return False
    return reviewed_on <= datetime.now(IST).date()


def _deployment_configuration_is_valid(
    *,
    payment_mode: str,
    payment_key_prefix: str,
    require_legal_review: bool,
) -> bool:
    required_configuration = (
        ADMIN_TOKEN,
        WHATSAPP_APP_SECRET,
        WHATSAPP_PHONE_ID,
        WHATSAPP_TOKEN,
        WHATSAPP_VERIFY_TOKEN,
        RAZORPAY_KEY_ID,
        RAZORPAY_KEY_SECRET,
        RAZORPAY_WEBHOOK_SECRET,
        AI_SAFETY_IDENTIFIER_SECRET,
        SENDGRID_API_KEY,
        SENDGRID_FROM_EMAIL,
        BOOKING_NOTIFICATION_EMAILS,
        SUPPORT_NOTIFICATION_EMAILS,
        SUPPORT_EMAIL,
        PRIVACY_EMAIL,
        PRIVACY_POLICY_URL,
        TERMS_OF_SERVICE_URL,
        REFUND_POLICY_URL,
        CANCELLATION_POLICY_URL,
        AI_CONSENT_VERSION,
        BOOKING_TERMS_VERSION,
        LEGAL_CONTENT_VERSION,
    )
    email_values = (
        SENDGRID_FROM_EMAIL,
        SUPPORT_EMAIL,
        PRIVACY_EMAIL,
        *BOOKING_NOTIFICATION_EMAILS,
        *SUPPORT_NOTIFICATION_EMAILS,
    )
    policy_urls = (
        PRIVACY_POLICY_URL,
        TERMS_OF_SERVICE_URL,
        REFUND_POLICY_URL,
        CANCELLATION_POLICY_URL,
    )
    reviewed_version_is_current = bool(
        LEGAL_CONTENT_REVIEWED_VERSION
        and LEGAL_CONTENT_REVIEWED_VERSION == LEGAL_CONTENT_VERSION
        and _valid_legal_review_date(LEGAL_CONTENT_REVIEWED_ON)
    )
    if require_legal_review:
        legal_review_ok = reviewed_version_is_current
    else:
        legal_review_ok = (
            (
                not LEGAL_CONTENT_REVIEWED_VERSION
                and not LEGAL_CONTENT_REVIEWED_ON
            )
            or reviewed_version_is_current
        )
    return bool(
        all(required_configuration)
        and RAZORPAY_MODE == payment_mode
        and RAZORPAY_KEY_ID.startswith(payment_key_prefix)
        and len(RAZORPAY_KEY_ID) >= 16
        and not AUTO_CREATE_SCHEMA
        and not ALLOW_INSECURE_WEBHOOKS
        and len(ADMIN_TOKEN) >= 32
        and len(AI_SAFETY_IDENTIFIER_SECRET) >= 32
        and len(WHATSAPP_APP_SECRET) >= 32
        and (
            not WHATSAPP_APP_SECRET_PREVIOUS
            or len(WHATSAPP_APP_SECRET_PREVIOUS) >= 32
        )
        and len(WHATSAPP_TOKEN) >= 32
        and len(WHATSAPP_VERIFY_TOKEN) >= 16
        and len(RAZORPAY_KEY_SECRET) >= 16
        and len(RAZORPAY_WEBHOOK_SECRET) >= 16
        and (
            not RAZORPAY_WEBHOOK_SECRET_PREVIOUS
            or len(RAZORPAY_WEBHOOK_SECRET_PREVIOUS) >= 16
        )
        and SENDGRID_API_KEY.startswith("SG.")
        and len(SENDGRID_API_KEY) >= 16
        and WHATSAPP_PHONE_ID.isdigit()
        and all(_valid_email(value) for value in email_values)
        and all(_valid_https_url(value) for value in policy_urls)
        and legal_review_ok
    )


def _production_configuration_is_valid() -> bool:
    return _deployment_configuration_is_valid(
        payment_mode="live",
        payment_key_prefix="rzp_live_",
        require_legal_review=True,
    )


def _staging_configuration_is_valid() -> bool:
    return _deployment_configuration_is_valid(
        payment_mode="test",
        payment_key_prefix="rzp_test_",
        require_legal_review=False,
    )


# ===============================
# ROUTES
# ===============================
@app.get("/")
def service_info():
    return jsonify(
        {
            "service": "nyaysetu-bot",
            "status": "running",
            "health": "/health/ready",
        }
    )


@app.get("/health/live")
def health_live():
    return jsonify({"ok": True, "service": "nyaysetu-bot"}), 200


@app.get("/health/ready")
def health_ready():
    database = get_db_health()
    strict_deployment = ENV in {"staging", "production"}
    database_compatible = bool(
        not strict_deployment or database.get("backend") == "postgresql"
    )
    database["deployment_compatible"] = database_compatible
    database["production_compatible"] = bool(
        ENV != "production" or database.get("backend") == "postgresql"
    )
    applied_schema_revision = (
        get_schema_revision() if strict_deployment else None
    )
    schema_ok = (
        applied_schema_revision == EXPECTED_SCHEMA_REVISION
        if strict_deployment
        else True
    )
    if ENV == "production":
        configuration_ok = _production_configuration_is_valid()
    elif ENV == "staging":
        configuration_ok = _staging_configuration_is_valid()
    else:
        configuration_ok = True
    ready = bool(
        database["ok"]
        and database_compatible
        and schema_ok
        and configuration_ok
    )
    return (
        jsonify(
            {
                "ok": ready,
                "environment": ENV,
                "database": database,
                "schema": {
                    "ok": schema_ok,
                    "applied": applied_schema_revision,
                    "expected": EXPECTED_SCHEMA_REVISION,
                },
                "configuration": "ok" if configuration_ok else "incomplete",
            }
        ),
        200 if ready else 503,
    )


@app.route("/webhook", methods=["GET"])
def verify():
    supplied_token = request.args.get("hub.verify_token", "")
    if (
        WHATSAPP_VERIFY_TOKEN
        and supplied_token
        and hmac.compare_digest(supplied_token, WHATSAPP_VERIFY_TOKEN)
    ):
        return request.args.get("hub.challenge"), 200
    return "Invalid token", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    # -------------------------------------------------
    # SECURITY: verify signatures by default. Local development must opt out.
    # -------------------------------------------------
    signature_required = not (
        ALLOW_INSECURE_WEBHOOKS and ENV in {"development", "test"}
    )
    if signature_required and not verify_whatsapp_signature():
        logger.warning("Invalid WhatsApp signature | request_id=%s", g.request_id)
        return "Forbidden", 403

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "invalid_json"}), 400

    envelopes = extract_whatsapp_messages(payload)
    if not envelopes:
        # Delivery/read status notifications are intentionally acknowledged.
        return jsonify({"status": "ignored"}), 200
    if any(
        not _valid_whatsapp_message_id(message.get("id"))
        or not _valid_whatsapp_sender(wa_id)
        for _, message, wa_id in envelopes
    ):
        # Every user message must have a bounded durable identity and a valid
        # sender before it can create inbox/user rows or trigger a reply.
        return jsonify({"error": "invalid_message_envelope"}), 400

    db = get_db()
    wa_id = "UNKNOWN"
    message_id = None
    processing_lock = None
    try:
        # Expiration uses the same caller-owned session and is bounded to one
        # indexed UPDATE.
        expire_old_pending_bookings(db)

        candidate_ids = [
            message["id"]
            for _, message, _ in envelopes
        ]
        processed_ids = set()
        if candidate_ids:
            processed_ids = {
                row[0]
                for row in (
                    db.query(InboundMessageEvent.message_id)
                    .filter(
                        InboundMessageEvent.message_id.in_(candidate_ids),
                        InboundMessageEvent.status == "DONE",
                    )
                    .all()
                )
            }

        pending_envelopes = [
            envelope
            for envelope in envelopes
            if envelope[1]["id"] not in processed_ids
        ]
        if not pending_envelopes:
            return jsonify({"status": "duplicate_ignored"}), 200

        value, message, wa_id = pending_envelopes[0]
        message_id = message.get("id")
        g.whatsapp_batch_has_more = len(pending_envelopes) > 1

        claim_result = claim_inbound_message(db, message_id)
        if claim_result == "DONE":
            return jsonify({"status": "duplicate_ignored"}), 200
        if claim_result == "BUSY":
            return jsonify({"status": "message_in_progress"}), 503
        g.inbound_message_id = message_id
        g.inbound_message_claimed = bool(message_id)

        processing_lock = _acquire_user_processing_lock(wa_id)
        if processing_lock is None:
            fail_inbound_message(message_id, "UserProcessingLockTimeout")
            return jsonify({"status": "user_processing_busy"}), 503

        # =================================================
        # GLOBAL MAINTENANCE MODE (SAFE & EARLY EXIT)
        # =================================================
        if MAINTENANCE_MODE and message.get("type") in ("text", "interactive"):
            if MAINTENANCE_ADMIN_BYPASS and wa_id == MAINTENANCE_ADMIN_BYPASS:
                logger.info(
                    "Maintenance bypass used | user=%s",
                    masked_identifier(wa_id),
                )
            else:
                now_ts = time_module.time()
                if not should_send_maintenance_notice(wa_id, now_ts):
                    return jsonify({"status": "maintenance_duplicate"}), 200

                send_text(
                    wa_id,
                    (
                        "⚙️ *NyaySetu is temporarily under maintenance.*\n\n"
                        "We are upgrading the service. Please try again later. "
                        "If anyone is in immediate danger, contact the appropriate "
                        "local emergency service."
                    ),
                )
                return jsonify({"status": "maintenance"}), 200

        user = get_or_create_user(db, wa_id)

        # Apply abuse controls before any menu, support, paid-session, or media
        # branch can trigger database or external-message work. Check the
        # per-user budget first so one sender cannot consume the global budget
        # with traffic that should already have been rejected locally.
        if is_user_rate_limited(wa_id):
            if should_send_rate_limit_notice(
                "user",
                wa_id,
                USER_MSG_WINDOW,
            ):
                send_text(wa_id, t(user, "rate_limit_exceeded"))
            return jsonify({"status": "rate_limited"}), 200
        if is_global_rate_limited():
            if should_send_rate_limit_notice(
                "global",
                wa_id,
                GLOBAL_REQ_WINDOW,
            ):
                send_text(wa_id, t(user, "service_busy"))
            return jsonify({"status": "rate_limited"}), 200

        text_body = ""
        interactive_id = None

        if message.get("type") == "text":
            text_body = str((message.get("text") or {}).get("body") or "")
        elif message.get("type") == "interactive":
            interactive = message.get("interactive") or {}
            itype = interactive.get("type")
            selected = interactive.get(itype) if itype else None
            interactive_id = (
                str(selected.get("id"))
                if isinstance(selected, dict) and selected.get("id")
                else None
            )
            text_body = interactive_id
        else:
            send_text(wa_id, t(user, "unsupported_message_type"))
            return jsonify({"status": "unsupported_message_type"}), 200

        text_body = text_body or ""
        lower_text = text_body.lower().strip()

        if close_completed_consultation(db, user, wa_id):
            return jsonify({"status": "ok"}), 200

        # =================================================
        # PERSISTENT HOME & SELF-SERVICE NAVIGATION
        # =================================================
        if user.welcome_sent and lower_text in HOME_KEYWORDS:
            send_home(wa_id, user)
            return jsonify({"status": "ok"}), 200

        if interactive_id in {
            HOME_BUTTON_IDS["more"],
            "home_more",
        }:
            send_more_options(wa_id, user)
            record_event("more_menu_opened", user_id=user.id)
            return jsonify({"status": "ok"}), 200

        if interactive_id == MORE_MENU_IDS["status"]:
            booking = latest_booking(db, wa_id)
            send_text(wa_id, booking_status_message(user, booking))
            if (
                booking
                and booking.status == BookingStatus.PENDING
                and user.last_payment_link
            ):
                send_text(
                    wa_id,
                    f"💳 {t(user, 'payment_link_text')}\n{user.last_payment_link}",
                )
            record_event(
                "appointment_status_viewed",
                {"booking_status": getattr(booking, "status", None)},
                user_id=user.id,
            )
            return jsonify({"status": "ok"}), 200

        if interactive_id == MORE_MENU_IDS["prepare"]:
            booking = latest_booking(db, wa_id)
            send_text(wa_id, preparation_message(user, booking))
            record_event(
                "consultation_checklist_viewed",
                {"category": getattr(booking, "category", user.category)},
                user_id=user.id,
            )
            return jsonify({"status": "ok"}), 200

        if interactive_id == MORE_MENU_IDS["guides"]:
            send_list_picker(
                wa_id,
                header=legal_ui(user, "guide_categories"),
                body=legal_ui(user, "guide_categories_body"),
                section_title=legal_ui(user, "guide_categories"),
                rows=legal_guide_rows(user),
            )
            record_event("legal_guides_opened", user_id=user.id)
            return jsonify({"status": "ok"}), 200

        if interactive_id and interactive_id.startswith("guidecat::"):
            category_key = interactive_id.split("::", 1)[1]
            rows = legal_guide_subcategory_rows(user, category_key)
            if not rows:
                send_text(wa_id, t(user, "invalid_selection"))
                return jsonify({"status": "ok"}), 200
            send_list_picker(
                wa_id,
                header=legal_ui(user, "guide_issues"),
                body=legal_ui(user, "guide_issues_body"),
                section_title=legal_ui(user, "guide_issues"),
                rows=rows,
            )
            record_event(
                "legal_guide_category_viewed",
                {"category": category_key},
                user_id=user.id,
            )
            return jsonify({"status": "ok"}), 200

        if interactive_id and interactive_id.startswith("guide::"):
            guide_category, guide_subcategory = parse_guide_id(interactive_id)
            if guide_category and guide_subcategory:
                send_text(
                    wa_id,
                    legal_guide_message(
                        user,
                        guide_category,
                        guide_subcategory,
                    ),
                )
                send_buttons(
                    wa_id,
                    legal_ui(user, "helpful"),
                    guide_feedback_buttons(
                        user,
                        guide_category,
                        guide_subcategory,
                    ),
                )
                record_event(
                    "legal_guide_viewed",
                    {
                        "category": guide_category,
                        "subcategory": guide_subcategory,
                    },
                    user_id=user.id,
                )
            else:
                send_text(wa_id, t(user, "invalid_selection"))
            return jsonify({"status": "ok"}), 200

        if interactive_id and interactive_id.startswith("guidefb::"):
            helpful, guide_category, guide_subcategory = (
                parse_guide_feedback_id(interactive_id)
            )
            if not helpful:
                send_text(wa_id, t(user, "invalid_selection"))
                return jsonify({"status": "ok"}), 200

            record_event(
                "legal_guide_feedback",
                {
                    "helpful": helpful == "yes",
                    "category": guide_category,
                    "subcategory": guide_subcategory,
                },
                user_id=user.id,
            )
            if helpful == "yes":
                send_buttons(
                    wa_id,
                    legal_ui(user, "thanks"),
                    [
                        {
                            "id": MORE_MENU_IDS["guides"],
                            "title": legal_ui(user, "guide_categories")[:20],
                        },
                        {
                            "id": "book_now",
                            "title": legal_ui(user, "book")[:20],
                        },
                    ],
                )
            else:
                send_buttons(
                    wa_id,
                    legal_ui(user, "more_help"),
                    [
                        {
                            "id": MORE_MENU_IDS["guides"],
                            "title": legal_ui(user, "guide_categories")[:20],
                        },
                        {
                            "id": MORE_MENU_IDS["support"],
                            "title": legal_ui(user, "support")[:20],
                        },
                        {
                            "id": "book_now",
                            "title": legal_ui(user, "book")[:20],
                        },
                    ],
                )
            return jsonify({"status": "ok"}), 200

        if interactive_id == MORE_MENU_IDS["privacy"]:
            send_text(wa_id, privacy_message(user))
            record_event("privacy_notice_viewed", user_id=user.id)
            return jsonify({"status": "ok"}), 200

        if interactive_id == MORE_MENU_IDS["language"]:
            user.flow_state = ASK_LANGUAGE
            db.commit()
            send_language_picker(wa_id, user)
            return jsonify({"status": "ok"}), 200

        if interactive_id in {
            MORE_MENU_IDS["support"],
            "payment_help",
        }:
            user.flow_state = ASK_SUPPORT_MESSAGE
            db.commit()
            latest_support = (
                db.query(SupportRequest)
                .filter(SupportRequest.user_id == user.id)
                .order_by(SupportRequest.id.desc())
                .first()
            )
            if latest_support:
                send_text(
                    wa_id,
                    t(
                        user,
                        "support_latest_status",
                        ticket_id=f"NSH-{latest_support.id:06d}",
                        status=latest_support.status,
                    ),
                )
            send_buttons(
                wa_id,
                support_contact_message(user),
                [
                    {
                        "id": BTN_SUPPORT_CANCEL,
                        "title": t(user, "support_cancel"),
                    }
                ],
            )
            return jsonify({"status": "ok"}), 200

        if user.flow_state == ASK_SUPPORT_MESSAGE:
            if (
                interactive_id == BTN_SUPPORT_CANCEL
                or lower_text in RESTART_KEYWORDS
            ):
                user.flow_state = NORMAL
                db.commit()
                send_home(wa_id, user)
                return jsonify({"status": "ok"}), 200

            support_message = text_body.strip()
            if (
                interactive_id
                or len(support_message) < 5
                or len(support_message) > 2_000
            ):
                send_text(wa_id, t(user, "support_request_retry"))
                return jsonify({"status": "ok"}), 200

            support_request = SupportRequest(
                user_id=user.id,
                case_id=user.case_id,
                request_type="PAYMENT" if "payment" in lower_text else "GENERAL",
                subject=support_message[:120],
                message=support_message,
                sla_due_at=utc_now() + timedelta(hours=SUPPORT_SLA_HOURS),
            )
            db.add(support_request)
            db.flush()
            job = None
            if SUPPORT_NOTIFICATION_EMAILS:
                job = enqueue_job(
                    db,
                    "support_notification",
                    {"support_request_id": support_request.id},
                    dedupe_key=(
                        f"support:{support_request.id}:notification"
                    ),
                )
            user.flow_state = NORMAL
            db.commit()
            send_text(
                wa_id,
                t(
                    user,
                    "support_request_saved",
                    ticket_id=f"NSH-{support_request.id:06d}",
                ),
            )
            record_event(
                "support_request_created",
                {"request_type": support_request.request_type},
                user_id=user.id,
            )
            if job:
                submit_outbox_job(job.id)
            send_home(wa_id, user)
            return jsonify({"status": "ok"}), 200

        # =================================================
        # PRIVATE POST-CONSULTATION FEEDBACK
        # =================================================
        if user.flow_state == ASK_FEEDBACK_RATING:
            if interactive_id and interactive_id.startswith("feedback::"):
                try:
                    rating = int(interactive_id.split("::", 1)[1])
                except (TypeError, ValueError):
                    rating = 0
                if rating not in range(1, 6):
                    send_text(wa_id, t(user, "invalid_selection"))
                    return jsonify({"status": "ok"}), 200

                booking = latest_booking_with_statuses(
                    db,
                    wa_id,
                    (BookingStatus.COMPLETED,),
                )
                feedback = Feedback(
                    user_id=user.id,
                    rating=rating,
                    context_json=json.dumps(
                        {"booking_id": getattr(booking, "id", None)},
                        separators=(",", ":"),
                    ),
                )
                db.add(feedback)
                user.flow_state = ASK_FEEDBACK_COMMENT
                db.commit()
                send_buttons(
                    wa_id,
                    t(user, "feedback_comment_prompt"),
                    [
                        {
                            "id": "feedback_skip",
                            "title": t(user, "feedback_skip"),
                        }
                    ],
                )
                return jsonify({"status": "ok"}), 200

            send_list_picker(
                wa_id,
                header=t(user, "feedback_header"),
                body=t(user, "feedback_body"),
                section_title=t(user, "feedback_section"),
                rows=feedback_rows(user),
            )
            return jsonify({"status": "ok"}), 200

        if user.flow_state == ASK_FEEDBACK_COMMENT:
            feedback = (
                db.query(Feedback)
                .filter(Feedback.user_id == user.id)
                .order_by(Feedback.id.desc())
                .first()
            )
            if feedback and interactive_id != "feedback_skip":
                comment = text_body.strip()
                if comment:
                    feedback.comment = comment[:1_000]
            if feedback:
                feedback.status = "COMPLETED"
            user.flow_state = NORMAL
            db.commit()
            send_text(wa_id, t(user, "feedback_thanks"))
            record_event(
                "consultation_feedback_submitted",
                {"rating": getattr(feedback, "rating", None)},
                user_id=user.id,
            )
            send_home(wa_id, user)
            return jsonify({"status": "ok"}), 200

        if interactive_id in {
            HOME_BUTTON_IDS["ask_ai"],
            BTN_ASK_AI,
        }:
            pending_booking = latest_booking_with_statuses(
                db,
                wa_id,
                (BookingStatus.PENDING,),
            )
            if pending_booking:
                user.flow_state = WAITING_PAYMENT
                db.commit()
                send_pending_payment_options(user, wa_id, pending_booking)
                return jsonify({"status": "ok"}), 200
            begin_ai_consent(db, user, wa_id)
            return jsonify({"status": "ok"}), 200

        if interactive_id in {
            HOME_BUTTON_IDS["book"],
            BTN_BOOK_CONSULT,
            "book_now",
        }:
            active_paid_booking = latest_booking_with_statuses(
                db,
                wa_id,
                (BookingStatus.PAID,),
            )
            _, paid_booking_end = get_booking_window(active_paid_booking)
            if paid_booking_end and datetime.now(IST) <= paid_booking_end:
                user.flow_state = PAYMENT_CONFIRMED
                db.commit()
                send_text(
                    wa_id,
                    booking_status_message(user, active_paid_booking),
                )
                send_text(wa_id, t(user, "post_payment_ai_start"))
                return jsonify({"status": "ok"}), 200

            pending_booking = latest_booking_with_statuses(
                db,
                wa_id,
                (BookingStatus.PENDING,),
            )
            if pending_booking:
                user.flow_state = WAITING_PAYMENT
                db.commit()
                send_pending_payment_options(user, wa_id, pending_booking)
                return jsonify({"status": "ok"}), 200
            begin_booking_scope_review(db, user, wa_id)
            return jsonify({"status": "ok"}), 200

        if user.flow_state == ASK_AI_CONSENT:
            if interactive_id == BTN_AI_CONSENT:
                paid_booking = latest_booking_with_statuses(
                    db,
                    wa_id,
                    (BookingStatus.PAID,),
                )
                _, paid_booking_end = get_booking_window(paid_booking)
                paid_session_active = bool(
                    paid_booking_end
                    and datetime.now(IST) <= paid_booking_end
                )
                user.ai_enabled = True
                user.flow_state = (
                    PAYMENT_CONFIRMED if paid_session_active else NORMAL
                )
                record_user_consent(
                    db,
                    user,
                    purpose="AI_PROCESSING",
                    policy_version=AI_CONSENT_VERSION,
                )
                db.commit()
                record_event(
                    "ai_consent_granted",
                    {"context": "paid" if paid_session_active else "free"},
                    user_id=user.id,
                )
                send_text(
                    wa_id,
                    t(
                        user,
                        (
                            "post_payment_ai_start"
                            if paid_session_active
                            else "ask_ai_prompt"
                        ),
                    ),
                )
                return jsonify({"status": "ok"}), 200

            if interactive_id == BTN_AI_DECLINE:
                user.ai_enabled = False
                user.flow_state = NORMAL
                db.commit()
                record_event("ai_consent_declined", user_id=user.id)
                send_home(wa_id, user)
                return jsonify({"status": "ok"}), 200

            begin_ai_consent(db, user, wa_id)
            return jsonify({"status": "ok"}), 200

        if user.flow_state == REVIEW_SERVICE:
            if interactive_id == BTN_BOOKING_SCOPE_CONTINUE:
                record_event("booking_started", user_id=user.id)
                if user.name and user.state_name and user.district_name:
                    send_verification_screen(db, user, wa_id)
                else:
                    user.flow_state = ASK_NAME
                    db.commit()
                    send_text(wa_id, t(user, "ask_name"))
                return jsonify({"status": "ok"}), 200

            if interactive_id == BTN_BOOKING_SCOPE_CANCEL:
                user.flow_state = NORMAL
                db.commit()
                send_home(wa_id, user)
                return jsonify({"status": "ok"}), 200

            begin_booking_scope_review(db, user, wa_id)
            return jsonify({"status": "ok"}), 200

        # =================================================
        # POST-PAYMENT SESSION CONTROL (CRITICAL)
        # =================================================
        paid_booking = None

        if user.flow_state in (WAITING_PAYMENT, PAYMENT_CONFIRMED):
            current_booking = latest_booking(db, wa_id)
            if (
                current_booking
                and current_booking.status == BookingStatus.PAID
            ):
                paid_booking = current_booking

        if paid_booking:
            logger.debug(
                "POST_PAYMENT_BLOCK_ENTER | wa_id=%s | booking_id=%s | state=%s",
                masked_identifier(wa_id),
                paid_booking.id,
                user.flow_state,
            )
            # -------------------------------
            # DEFENSIVE GUARD — NEVER CRASH
            # -------------------------------
            if not paid_booking.date or not paid_booking.slot_code:
                logger.warning(
                    "Incomplete paid booking | booking_id=%s | date=%s | slot=%s",
                    paid_booking.id,
                    paid_booking.date,
                    paid_booking.slot_code,
                )
                return jsonify({"status": "ignored"}), 200

            # -------------------------------
            # SAFE booking window (single source of truth)
            # -------------------------------
            booking_start, booking_end = get_booking_window(paid_booking)
            
            if not booking_start or not booking_end:
                logger.error(
                    "Invalid booking window | booking_id=%s | date=%s | slot=%s",
                    paid_booking.id,
                    paid_booking.date,
                    paid_booking.slot_code,
                )
                return jsonify({"status": "ignored"}), 200
            
            now = datetime.now(IST)

            # =================================================
            # 🔒 HARD GUARD: POST-PAYMENT SESSION (TIME-BOUND)
            # =================================================
            if now <= booking_end:
                logger.debug(
                    "POST_PAYMENT_ACTIVE | wa_id=%s | now=%s | booking_end=%s | state_before=%s",
                    masked_identifier(wa_id),
                    now,
                    booking_end,
                    user.flow_state,
                )
                
                # 🔒 Ensure state is aligned (webhook race-safe)
                if user.flow_state != PAYMENT_CONFIRMED:
                    set_flow_state(db, user, PAYMENT_CONFIRMED)

                message = (text_body or "").strip().lower()
            
                if message == "receipt":
                    send_payment_receipt_again(db, wa_id)
                    return jsonify({"status": "ok"}), 200

                if not user.ai_enabled:
                    begin_ai_consent(db, user, wa_id)
                    return jsonify({"status": "ok"}), 200

               
                # -------------------------------------------------
                # AI RATE LIMITING (POST-PAYMENT PROTECTION)
                # -------------------------------------------------
                if is_ai_rate_limited(wa_id):
                    send_text(
                        wa_id,
                        t(user, "ai_post_payment_cooldown")
                    )
                    return jsonify({"status": "ok"}), 200
                
                send_typing_on(wa_id)
                
                try:
                    reply = ai_reply_router(
                        message,
                        user,
                        context="post_payment"
                    )
                finally:
                    send_typing_off(wa_id)
                
                send_text(
                    wa_id,
                    f"🤖 {t(user, 'consultation_assistant_header')}\n\n{reply}"
                )
                
                return jsonify({"status": "ok"}), 200
            
        # ===============================
        # RESTART (BLOCKED AFTER PAYMENT)
        # ===============================
        if lower_text in RESTART_KEYWORDS:
            logger.debug(
                "RESTART_ATTEMPT | wa_id=%s | state=%s",
                masked_identifier(wa_id),
                user.flow_state,
            )
            # 🔒 Never allow restart after payment
            if user.flow_state == PAYMENT_CONFIRMED:
                send_text(
                    wa_id,
                    t(user, "consultation_already_confirmed")
                )
                return jsonify({"status": "ok"}), 200
        
            if user.flow_state == WAITING_PAYMENT:
                send_text(wa_id, t(user, "payment_in_progress"))
                return jsonify({"status": "ok"}), 200
        
            set_flow_state(db, user, NORMAL)
            user.ai_enabled = False
            user.temp_date = None
            user.temp_slot = None
            user.last_payment_link = None
            db.commit()
        
            send_text(wa_id, t(user, "restart"))
            return jsonify({"status": "ok"}), 200
            
        # ===============================
        # RETURNING USER HOME
        # ===============================
        if (
            user.flow_state == NORMAL
            and user.welcome_sent
            and has_completed_consultation(db, wa_id)
            and not user.ai_enabled
            and user.free_ai_count == 0
            and lower_text in WELCOME_KEYWORDS
        ):
            send_buttons(
                wa_id,
                t(user, "welcome_back", name=user.name),
                [
                    {"id": BTN_ASK_AI, "title": f"🤖 {t(user, 'ask_ai')}"},
                    {"id": BTN_BOOK_CONSULT, "title": f"📅 {t(user, 'book_consult')}"},
                ],
            )
            return jsonify({"status": "ok"}), 200

        # ===============================
        # WELCOME (ONE-TIME ONLY)
        # ===============================
        logger.debug(
            "WELCOME_CHECK | wa_id=%s | state=%s | welcome_sent=%s",
            masked_identifier(wa_id),
            user.flow_state,
            user.welcome_sent,
        )
        # ===============================
        # WELCOME (ONE-TIME ONLY — RACE SAFE)
        # ===============================
        if (
            user.flow_state == NORMAL
            and not user.welcome_sent
        ):
        
            # 🔒 LOCK FIRST (atomic update before sending)
            user.welcome_sent = True
            user.flow_state = ASK_LANGUAGE
            db.commit()
        
            send_language_picker(wa_id, user)
            record_event("onboarding_started", user_id=user.id)
        
            return jsonify({"status": "ok"}), 200
            
        # ===============================
        # LANGUAGE SELECTION
        # ===============================
        if user.flow_state == ASK_LANGUAGE:
            if interactive_id in ("lang_en", "lang_hi", "lang_mr"):
                user.language = interactive_id.replace("lang_", "")
                db.commit()
        
                # ✅ Marathi (Greetings)
                #if user.language == "mr":
                
                #    if not getattr(user, "marathi_greeted", False):
                #        send_text(
                #            wa_id,
                #           "🙏 जय महाराष्ट्र! 🇮🇳\nआपण NyaySetu मध्ये स्वागत आहे ⚖️"
                #        )
                #        user.marathi_greeted = True
                
                #    db.commit()
                        
                save_state(db, user, ASK_AI_OR_BOOK)
        
                send_buttons(
                    wa_id,
                    t(user, "ask_ai_or_book"),
                    [
                        {"id": "opt_ai", "title": t(user, "ask_ai")},
                        {"id": "opt_book", "title": t(user, "book_consult")},
                    ],
                )
            else:
                send_language_picker(wa_id, user)

            return jsonify({"status": "ok"}), 200       

        # ===============================
        # AI OR BOOK
        # ===============================
        if user.flow_state == ASK_AI_OR_BOOK:
            if interactive_id == "opt_ai":
                begin_ai_consent(db, user, wa_id)
                return jsonify({"status": "ok"}), 200

            if interactive_id == "opt_book":
                begin_booking_scope_review(db, user, wa_id)
                return jsonify({"status": "ok"}), 200

        # ===============================
        # BOOKING KEYWORD (GLOBAL)
        # ===============================
        if (
            is_booking_intent(lower_text)
            or interactive_id == "book_now"
        ) and user.flow_state == NORMAL:    
            begin_booking_scope_review(db, user, wa_id)
            return jsonify({"status": "ok"}), 200

        # ===============================
        # FREE AI CHAT
        # ===============================
        if user.flow_state == NORMAL and user.ai_enabled:
        
            if not text_body:
                return jsonify({"status": "ignored"}), 200
        
            # -------------------------------------------------
            # FREE LIMIT CHECK
            # -------------------------------------------------
            if user.free_ai_count >= FREE_AI_LIMIT:
                send_buttons(
                    wa_id,
                    t(user, "free_limit_reached"),
                    [{"id": "book_now", "title": t(user, "book_consult")}],
                )
                return jsonify({"status": "ok"}), 200
        
            # -------------------------------------------------
            # AI RATE LIMITING
            # -------------------------------------------------
            if is_ai_rate_limited(wa_id):
                send_text(wa_id, t(user, "ai_cooldown"))
                return jsonify({"status": "ok"}), 200
        
            send_typing_on(wa_id)
        
            try:
                reply = ai_reply_router(text_body, user)
            finally:
                send_typing_off(wa_id)
        
            user.free_ai_count += 1
            db.commit()
        
            # -------------------------------------------------
            # SOFT BOOKING PROMPT (WITH BUTTON)
            # -------------------------------------------------
            if user.free_ai_count == FREE_AI_SOFT_PROMPT_AT:
            
                send_text(wa_id, reply)            
                send_buttons(
                    wa_id,
                    t(user, "soft_booking_prompt"),
                    [
                        {"id": "book_now", "title": t(user, "book_consult")}
                    ],
                )
            
                return jsonify({"status": "ok"}), 200
            
            # Normal reply
            send_text(wa_id, reply)
            return jsonify({"status": "ok"}), 200

        # =================================================
        # BOOKING FLOW CONTINUATION
        # =================================================     
        if (
            user.flow_state == FLOW_VERIFY_DETAILS
            and interactive_id == BTN_DETAILS_OK
        ):
            save_state(db, user, ASK_CATEGORY)
            send_category_list(wa_id, user)
            return jsonify({"status": "ok"}), 200
        if (
            user.flow_state == FLOW_VERIFY_DETAILS
            and interactive_id == BTN_DETAILS_EDIT
        ):
            save_state(db, user, ASK_NAME)
            send_text(wa_id, t(user, "ask_name"))
            return jsonify({"status": "ok"}), 200

        # -------------------------------
        # Ask Name
        # -------------------------------
        if user.flow_state == ASK_NAME:
            if not text_body or len(text_body.strip()) < 2:
                send_text(wa_id, t(user, "ask_name_retry"))
                return jsonify({"status": "ok"}), 200
        
            clean_name = normalize_name(text_body)
            
            if not clean_name:
                send_text(
                    wa_id,
                    t(user, "name_invalid")
                )
                return jsonify({"status": "ok"}), 200
            
            user.name = clean_name
            db.commit()        
        
            # ✅ ALL users → ask DISTRICT directly
            save_state(db, user, ASK_DISTRICT)
        
            send_text(
                wa_id,
                t(user, "ask_district_text")            
            )
        
            return jsonify({"status": "ok"}), 200

        # -------------------------------
        # Ask District (SMART FLOW)
        # -------------------------------
        if user.flow_state == ASK_DISTRICT:
            if interactive_id and interactive_id.startswith("loc::"):
                parts = interactive_id.split("::", 2)
                if len(parts) == 3 and all(parts[1:]):
                    user.temp_district = parts[1]
                    user.temp_state = parts[2]
                    user.flow_state = CONFIRM_LOCATION
                    db.commit()
                    send_buttons(
                        wa_id,
                        (
                            f"{t(user, 'location_found')}\n"
                            f"*{parts[1]}, {parts[2]}*\n\n"
                            f"{t(user, 'confirm_location')}"
                        ),
                        [
                            {
                                "id": "loc_yes",
                                "title": f"✅ {t(user, 'confirm_yes')}",
                            },
                            {
                                "id": "loc_change",
                                "title": f"✏️ {t(user, 'confirm_change')}",
                            },
                        ],
                    )
                    return jsonify({"status": "ok"}), 200

            if not text_body:
                send_text(
                    wa_id,
                    t(user, "ask_district_text")            
                )
                return jsonify({"status": "ok"}), 200
        
            district, state, confidence = detect_district_and_state(text_body)
        
            # -------------------------------
            # HIGH CONFIDENCE
            # -------------------------------
            if confidence == "HIGH":
                user.temp_district = district
                user.temp_state = state
                db.commit()
        
                save_state(db, user, CONFIRM_LOCATION)
        
                msg = (
                    f"{t(user, 'location_found')}\n"
                    f"*{district}, {state}*\n\n"
                    f"{t(user, 'confirm_location')}"
                )
                
                send_buttons(
                    wa_id,
                    msg,
                    [
                        {"id": "loc_yes", "title": f"✅ {t(user, 'confirm_yes')}"},
                        {"id": "loc_change", "title": f"✏️ {t(user, 'confirm_change')}"},
                    ],
                )

                return jsonify({"status": "ok"}), 200
        
            # -------------------------------
            # MULTIPLE MATCHES
            # -------------------------------
            if confidence == "MULTIPLE":
                rows = [
                    {
                        "id": f"loc::{match_district}::{match_state}",
                        "title": match_district,
                        "description": match_state,
                    }
                    for _, match_district, match_state in district[:10]
                ]
                send_list_picker(
                    wa_id,
                    header=t(user, "choose_district"),
                    body=t(user, "district_multiple_matches"),
                    section_title=t(user, "choose_district"),
                    rows=rows,
                )
                return jsonify({"status": "ok"}), 200
        
            # -------------------------------
            # LOW CONFIDENCE
            # -------------------------------
            send_text(
                wa_id,
                t(user, "district_not_identified")
            )
            return jsonify({"status": "ok"}), 200

        # -------------------------------
        # Confirm Location
        # -------------------------------
        if user.flow_state == CONFIRM_LOCATION:
        
            if interactive_id == "loc_yes":
                user.district_name = user.temp_district
                user.state_name = user.temp_state
        
                user.temp_district = None
                user.temp_state = None
                db.commit()
        
                save_state(db, user, ASK_CATEGORY)
                send_category_list(wa_id, user)
                return jsonify({"status": "ok"}), 200
        
            if interactive_id == "loc_change":
                user.temp_district = None
                user.temp_state = None
                db.commit()
        
                save_state(db, user, ASK_DISTRICT)
                send_text(
                    wa_id,
                    t(user, "district_retry")
                )
                return jsonify({"status": "ok"}), 200        

            if user.temp_district and user.temp_state:
                send_buttons(
                    wa_id,
                    (
                        f"{t(user, 'location_found')}\n"
                        f"*{user.temp_district}, {user.temp_state}*\n\n"
                        f"{t(user, 'confirm_location')}"
                    ),
                    [
                        {"id": "loc_yes", "title": f"✅ {t(user, 'confirm_yes')}"},
                        {
                            "id": "loc_change",
                            "title": f"✏️ {t(user, 'confirm_change')}",
                        },
                    ],
                )
            else:
                user.flow_state = ASK_DISTRICT
                db.commit()
                send_text(wa_id, t(user, "district_retry"))
            return jsonify({"status": "ok"}), 200
        
        # -------------------------------
        # Category (STRICT & SAFE)
        # -------------------------------
        if user.flow_state == ASK_CATEGORY:
            category = None
        
            # ---------------------------------
            # Category selected from list
            # ---------------------------------
            if interactive_id and interactive_id.startswith("cat_"):
                category = interactive_id.replace("cat_", "")
        
            # ---------------------------------
            # Ignore empty / status events
            # ---------------------------------
            if not category and not text_body:
                return jsonify({"status": "ignored"}), 200
        
            # ---------------------------------
            # Still invalid → ask again
            # ---------------------------------
            if not category:
                send_text(wa_id, t(user, "category_retry"))
                send_category_list(wa_id, user)
                return jsonify({"status": "ok"}), 200
        
            # ---------------------------------
            # Save category & move forward
            # ---------------------------------
            
            user.category = category
            db.commit()
            
            save_state(db, user, ASK_SUBCATEGORY)
            
            # category is already normalized key
            send_subcategory_list(
                db,
                wa_id,
                user,
                user.category
            )

            return jsonify({"status": "ok"}), 200

        # -------------------------------
        # Sub Category (STRICT & SAFE)
        # -------------------------------
        if user.flow_state == ASK_SUBCATEGORY:
        
            if not interactive_id:
                send_text(wa_id, t(user, "subcategory_retry"))
                send_subcategory_list(db, wa_id, user, user.category)
                return jsonify({"status": "ok"}), 200
        
            if not interactive_id.startswith("subcat::"):
                logger.info(
                    "Invalid subcategory input | wa_id=%s | id=%s",
                    masked_identifier(wa_id),
                    interactive_id,
                )
                send_text(wa_id, t(user, "subcategory_retry"))
                send_subcategory_list(db, wa_id, user, user.category)
                return jsonify({"status": "ok"}), 200
        
            # Parse ID
            parsed_category, subcategory = parse_subcategory_id(interactive_id)
            expected_category = user.category
        
            if not expected_category:
                logger.error(
                    "Category missing during ASK_SUBCATEGORY | wa_id=%s",
                    masked_identifier(wa_id),
                )
                save_state(db, user, ASK_CATEGORY)
                send_category_list(wa_id, user)
                return jsonify({"status": "ok"}), 200
        
            if not parsed_category or parsed_category != expected_category:
                send_text(wa_id, t(user, "subcategory_mismatch"))
                send_subcategory_list(db, wa_id, user, expected_category)
                return jsonify({"status": "ok"}), 200
        
            # Save subcategory
            user.subcategory = subcategory
            db.commit()
        
            # Analytics
            record = (
                db.query(CategoryAnalytics)
                .filter_by(category=parsed_category, subcategory=subcategory)
                .first()
            )
        
            if record:
                record.count += 1
            else:
                db.add(CategoryAnalytics(
                    category=parsed_category,
                    subcategory=subcategory,
                    count=1,
                ))
        
            db.commit()
        
            save_state(db, user, ASK_DATE)
        
            send_available_dates(db, user, wa_id)
        
            return jsonify({"status": "ok"}), 200
                       
        
        # -------------------------------
        # Date (STRICT & SAFE)
        # -------------------------------
        if user.flow_state == ASK_DATE:
            # ---------------------------------
            # Ignore empty / status events
            # ---------------------------------
            if not interactive_id:
                send_text(wa_id, t(user, "select_date_retry"))
                send_available_dates(db, user, wa_id)
                return jsonify({"status": "ok"}), 200
        
            # ---------------------------------
            # Date selected from list
            # ---------------------------------
            if not interactive_id.startswith("date_"):
                send_text(wa_id, t(user, "select_date_retry"))
                return jsonify({"status": "ok"}), 200
        
            date_str = interactive_id.replace("date_", "").strip()
        
            # ---------------------------------
            # Validate date format
            # ---------------------------------
        
            try:
                selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                today = datetime.now(IST).date()
            
                if selected_date < today:
                    send_text(wa_id, t(user, "past_date_error"))
                    send_available_dates(db, user, wa_id)
                    return jsonify({"status": "ok"}), 200
            
            except ValueError:
                send_text(wa_id, t(user, "invalid_date"))
                return jsonify({"status": "ok"}), 200
            # ---------------------------------
            # Save date & move forward
            # ---------------------------------
            
            user.temp_date = date_str
            user.flow_state = ASK_SLOT
            db.commit()
            if not send_available_slots(db, user, wa_id, date_str):
                user.flow_state = ASK_DATE
                db.commit()
                send_available_dates(db, user, wa_id)
        
            return jsonify({"status": "ok"}), 200
            
        # -------------------------------
        # Slot (STRICT & SAFE)
        # -------------------------------
        if user.flow_state == ASK_SLOT:
            # ---------------------------------
            # Ignore empty / status events
            # ---------------------------------
            if not interactive_id:
                send_text(wa_id, t(user, "slot_retry"))
                send_available_slots(db, user, wa_id, user.temp_date)
                return jsonify({"status": "ok"}), 200

            # ---------------------------------
            # SAFETY: User clicked a DATE again
            # ---------------------------------
            if interactive_id.startswith("date_"):
                save_state(db, user, ASK_DATE)
                return jsonify({"status": "ok"}), 200
        
            # ---------------------------------
            # Validate slot selection
            # ---------------------------------
            if not interactive_id.startswith("slot_"):
                send_text(wa_id, t(user, "slot_retry"))
                return jsonify({"status": "ok"}), 200
        
            slot_code = interactive_id.replace("slot_", "").strip()
        
            # ---------------------------------
            # Validate slot exists
            # ---------------------------------
            if slot_code not in SLOT_MAP:
                send_text(wa_id, t(user, "invalid_slot"))
                send_available_slots(db, user, wa_id, user.temp_date)
                return jsonify({"status": "ok"}), 200
        
            required_fields = [
                user.name,
                user.state_name,
                user.district_name,
                user.category,
                user.temp_date,
            ]
            if not all(required_fields):
                user.flow_state = ASK_NAME
                db.commit()
                send_text(wa_id, t(user, "booking_missing"))
                return jsonify({"status": "ok"}), 200

            user.temp_slot = slot_code
            db.commit()
            send_booking_review(db, user, wa_id)
            record_event(
                "booking_review_viewed",
                {
                    "category": user.category,
                    "date": user.temp_date,
                    "slot": slot_code,
                },
                user_id=user.id,
            )
            return jsonify({"status": "ok"}), 200

        # -------------------------------
        # Review before creating payment link
        # -------------------------------
        if user.flow_state == REVIEW_BOOKING:
            if interactive_id == BTN_REVIEW_CHANGE_TIME:
                user.temp_slot = None
                user.flow_state = ASK_DATE
                db.commit()
                send_available_dates(db, user, wa_id)
                return jsonify({"status": "ok"}), 200

            if interactive_id == BTN_REVIEW_CANCEL:
                clear_booking_draft(user)
                user.flow_state = NORMAL
                db.commit()
                send_text(wa_id, t(user, "booking_cancelled_before_payment"))
                send_home(wa_id, user)
                record_event("booking_cancelled_before_payment", user_id=user.id)
                return jsonify({"status": "ok"}), 200

            if interactive_id != BTN_REVIEW_PAY:
                send_booking_review(db, user, wa_id)
                return jsonify({"status": "ok"}), 200

            record_user_consent(
                db,
                user,
                purpose="BOOKING_PAYMENT",
                policy_version=BOOKING_TERMS_VERSION,
            )
            booking, payment_link = create_booking_temp(
                db=db,
                user=user,
                name=user.name,
                state=user.state_name,
                district=user.district_name,
                category=user.category,
                subcategory=user.subcategory,
                date=user.temp_date,
                slot_code=user.temp_slot,
            )

            if not booking:
                user.temp_slot = None
                user.flow_state = ASK_DATE
                db.commit()
                send_text(wa_id, f"⚠️ {payment_link}")
                send_available_dates(db, user, wa_id)
                return jsonify({"status": "ok"}), 200

            user.last_payment_link = payment_link
            user.flow_state = WAITING_PAYMENT
            db.commit()
            send_buttons(
                wa_id,
                t(user, "payment_waiting_help"),
                [
                    {
                        "id": MORE_MENU_IDS["status"],
                        "title": t(user, "check_payment_status"),
                    },
                    {
                        "id": "payment_help",
                        "title": t(user, "payment_help"),
                    },
                ],
            )
            send_text(
                wa_id,
                f"💳 {t(user, 'payment_link_text')}\n{payment_link}",
            )
            record_event(
                "payment_link_created",
                {
                    "booking_id": booking.id,
                    "category": booking.category,
                    "amount": booking.amount,
                },
                user_id=user.id,
            )
            return jsonify({"status": "ok"}), 200

        # ===============================
        # WAITING PAYMENT (SAFE MODE)
        # ===============================
        if user.flow_state == WAITING_PAYMENT:
        
            # Ignore delivery/status callbacks
            if not text_body:
                return jsonify({"status": "ignored"}), 200
        
            booking = latest_booking(db, wa_id)
            if booking and booking.status == BookingStatus.EXPIRED:
                clear_booking_draft(user)
                user.flow_state = ASK_DATE
                db.commit()
                send_text(wa_id, t(user, "booking_status_expired"))
                send_available_dates(db, user, wa_id)
                return jsonify({"status": "ok"}), 200

            # Resend payment options without trapping the user away from help.
            send_pending_payment_options(user, wa_id, booking)

            return jsonify({"status": "ok"}), 200

                
        # -------------------------------
        # Default fallback (safe)
        # -------------------------------
        return jsonify({"status": "ignored"}), 200
    except WhatsAppDeliveryError as exc:
        completed, job_id = complete_inbound_after_delivery_failure(
            db,
            message_id,
            exc,
        )
        if completed:
            # after_request must not overwrite the delivery outcome or perform
            # a second terminal-state transaction.
            g.inbound_message_claimed = False
            if job_id is not None:
                submit_outbox_job(job_id)
            logger.warning(
                "Inbound business state preserved after outbound failure | "
                "request_id=%s | retry_queued=%s | ambiguous=%s",
                g.request_id,
                job_id is not None,
                exc.ambiguous,
            )
            return (
                jsonify(
                    {
                        "status": (
                            "delivery_queued"
                            if job_id is not None
                            else "delivery_not_retried"
                        )
                    }
                ),
                200,
            )

        db.rollback()
        fail_inbound_message(message_id, "OutboundDeliveryPersistenceError")
        logger.exception(
            "Failed outbound delivery could not be persisted | request_id=%s",
            g.request_id,
        )
        return jsonify({"status": "retry"}), 503
    except Exception:
        # Roll back partial work and fail the lease-aware claim. Meta can retry
        # a transient failure instead of the event being lost forever.
        try:
            db.rollback()
        except Exception:
            pass

        fail_inbound_message(message_id, "InboundProcessingError")
    
        try:
            if wa_id and wa_id != "UNKNOWN":
                safe_wa_id = wa_id[:5] + "*****" + wa_id[-2:]
            else:
                safe_wa_id = "UNKNOWN"
        except Exception:
            safe_wa_id = "UNKNOWN"
    
        logger.exception(
            "Webhook processing failed; provider retry requested | wa_id=%s",
            safe_wa_id,
        )
        return jsonify({"status": "retry"}), 503
    finally:
        _release_user_processing_lock(wa_id, processing_lock)
        db.close()

_CLOSED_PAYMENT_RECONCILIATION_STATUSES = frozenset(
    {
        "AUTO_RESOLVED",
        "RESOLVED",
        "REFUND_INITIATED",
        "REFUNDED",
        "IGNORED",
    }
)
_MANUAL_PAYMENT_RECONCILIATION_STATUSES = frozenset(
    {
        "RESOLVED",
        "REFUND_INITIATED",
        "REFUNDED",
        "IGNORED",
    }
)
_RAZORPAY_PAYMENT_ID_PATTERN = re.compile(r"pay_[A-Za-z0-9]{1,251}")
_RAZORPAY_PAYMENT_LINK_ID_PATTERN = re.compile(
    r"plink_[A-Za-z0-9]{1,249}"
)


def _find_manual_payment_disposition(
    db,
    *,
    payment_id: str,
    payment_link_id: str,
) -> PaymentReconciliation | None:
    return next(
        (
            item
            for item in lock_matching_payment_reconciliations(
                db,
                payment_id=payment_id,
                payment_link_id=payment_link_id,
            )
            if item.status
            in _MANUAL_PAYMENT_RECONCILIATION_STATUSES
        ),
        None,
    )


def _persist_manual_disposition_event(
    db,
    *,
    event_id: str,
    event_type: str,
    payload_hash: str,
    disposition: PaymentReconciliation,
) -> None:
    """Record the replay without changing an operator's terminal decision."""

    event = (
        db.query(WebhookEvent)
        .filter(
            WebhookEvent.provider == "razorpay",
            WebhookEvent.event_id == event_id,
        )
        .with_for_update()
        .first()
    )
    if not event:
        event = WebhookEvent(
            provider="razorpay",
            event_id=event_id,
            received_at=utc_now(),
        )
        db.add(event)
    now = utc_now()
    event.event_type = event_type
    event.payload_hash = payload_hash
    event.status = "MANUAL_DISPOSITION"
    event.attempts = (event.attempts or 0) + 1
    event.last_error = (
        f"TERMINAL_RECONCILIATION_{disposition.status}"
    )[:500]
    event.processed_at = now
    # Financial/manual evidence is intentionally retained.
    event.expires_at = None
    db.commit()


def _upsert_payment_reconciliation(
    db,
    *,
    payment_id: str,
    payment_link_id: str,
    reason: str,
    booking=None,
    received_amount=None,
    currency: str | None = None,
) -> PaymentReconciliation:
    reconciliation = (
        db.query(PaymentReconciliation)
        .filter(
            PaymentReconciliation.provider == "razorpay",
            PaymentReconciliation.payment_id == payment_id,
        )
        .with_for_update()
        .first()
    )
    if (
        reconciliation
        and reconciliation.status
        in _CLOSED_PAYMENT_RECONCILIATION_STATUSES
    ):
        # Provider retries must never reopen or rewrite an operator/system
        # disposition, especially after a refund has been initiated.
        return reconciliation

    if not reconciliation:
        reconciliation = PaymentReconciliation(
            provider="razorpay",
            payment_id=payment_id,
        )
        db.add(reconciliation)

    reconciliation.payment_link_id = (
        payment_link_id or reconciliation.payment_link_id
    )
    if booking is not None:
        reconciliation.booking_id = booking.id
    reconciliation.reason = reason
    reconciliation.status = "OPEN"
    if booking is not None:
        reconciliation.expected_amount = int(booking.amount) * 100
    if isinstance(received_amount, int) and not isinstance(
        received_amount,
        bool,
    ):
        reconciliation.received_amount = int(received_amount)
    if currency:
        reconciliation.currency = str(currency)[:8]
    if booking is not None or not reconciliation.details_json:
        reconciliation.details_json = json.dumps(
            {
                "booking_status": (
                    getattr(getattr(booking, "status", None), "value", None)
                    or str(getattr(booking, "status", "") or "")
                )[:40],
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    db.flush()
    return reconciliation


def _persist_payment_review(
    db,
    *,
    event_id: str,
    event_type: str,
    payload_hash: str,
    webhook_status: str,
    payment_link_id: str,
    reason: str,
    booking=None,
    received_amount=None,
    currency: str | None = None,
) -> PaymentReconciliation:
    event = (
        db.query(WebhookEvent)
        .filter(
            WebhookEvent.provider == "razorpay",
            WebhookEvent.event_id == event_id,
        )
        .first()
    )
    if not event:
        event = WebhookEvent(
            provider="razorpay",
            event_id=event_id,
            received_at=utc_now(),
        )
        db.add(event)
    event.event_type = event_type
    event.payload_hash = payload_hash
    event.status = webhook_status
    event.attempts = (event.attempts or 0) + 1
    event.last_error = reason[:500]
    event.processed_at = None
    # Financial exceptions remain until an operator explicitly resolves them.
    event.expires_at = None

    reconciliation = _upsert_payment_reconciliation(
        db,
        payment_id=event_id,
        payment_link_id=payment_link_id,
        reason=reason,
        booking=booking,
        received_amount=received_amount,
        currency=currency,
    )
    if reconciliation.status == "OPEN" and (
        BOOKING_NOTIFICATION_EMAILS or SUPPORT_NOTIFICATION_EMAILS
    ):
        enqueue_job(
            db,
            "payment_reconciliation_alert",
            {"payment_reconciliation_id": reconciliation.id},
            dedupe_key=(
                f"payment-review:{reconciliation.id}:"
                f"{reason[:64]}"
            ),
        )
    db.commit()
    return reconciliation


def _ensure_booking_fulfillment(
    db,
    booking,
    *,
    capacity_conflict: str | None = None,
) -> BookingFulfillment:
    return ensure_booking_fulfillment(
        db,
        booking,
        capacity_conflict=capacity_conflict,
    )


# ===============================
# PAYMENT WEBHOOK
# ===============================
@app.route("/payment/webhook", methods=["POST"])
def payment_webhook():
    db = get_db()
    event_id = None
    event_type = None
    payload_hash = None
    try:
        # Verify the exact raw bytes before parsing attacker-controlled JSON.
        raw_payload = request.get_data(cache=True)
        signature = request.headers.get("X-Razorpay-Signature", "").strip()

        if RAZORPAY_MODE not in {"test", "live"}:
            logger.critical("Invalid RAZORPAY_MODE configuration")
            return "Server misconfiguration", 500
        razorpay_webhook_secrets = tuple(
            secret
            for secret in (
                RAZORPAY_WEBHOOK_SECRET,
                RAZORPAY_WEBHOOK_SECRET_PREVIOUS,
            )
            if secret
        )
        if not razorpay_webhook_secrets:
            logger.critical("RAZORPAY_WEBHOOK_SECRET is not configured")
            return "Server misconfiguration", 500
        if not signature:
            logger.warning("Missing Razorpay signature")
            return "Signature missing", 400

        signature_valid = any(
            hmac.compare_digest(
                hmac.new(
                    secret.encode("utf-8"),
                    raw_payload,
                    hashlib.sha256,
                ).hexdigest(),
                signature,
            )
            for secret in razorpay_webhook_secrets
        )
        if not signature_valid:
            logger.warning(
                "Invalid Razorpay signature | request_id=%s",
                getattr(g, "request_id", "unknown"),
            )
            return "Invalid signature", 400

        try:
            data = json.loads(raw_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return "Invalid JSON", 400
        if not isinstance(data, dict):
            return "Invalid payload", 400

        event_type = str(data.get("event") or "")
        if event_type != "payment_link.paid":
            return "Ignored", 200

        # A signed event ID is the primary replay control. The timestamp window
        # is a configurable secondary guard and may be disabled with zero.
        event_created_at = data.get("created_at")
        now = utc_now()
        if event_created_at is not None:
            try:
                event_time = datetime.fromtimestamp(
                    int(event_created_at),
                    tz=timezone.utc,
                ).replace(tzinfo=None)
            except (TypeError, ValueError, OSError, OverflowError):
                return "Invalid timestamp", 400
            if event_time > now + timedelta(minutes=5):
                return "Invalid future timestamp", 400
            if (
                WEBHOOK_REPLAY_WINDOW_SECONDS
                and (now - event_time).total_seconds()
                > WEBHOOK_REPLAY_WINDOW_SECONDS
            ):
                # A valid captured payment must not be discarded solely
                # because delivery was delayed. The durable event/payment ID
                # remains the replay control.
                logger.warning(
                    "Delayed signed payment event accepted for reconciliation"
                )

        payload = data.get("payload")
        payment = (
            payload.get("payment", {}).get("entity")
            if isinstance(payload, dict)
            else None
        )
        payment_link = (
            payload.get("payment_link", {}).get("entity")
            if isinstance(payload, dict)
            else None
        )
        if not isinstance(payment, dict) or not isinstance(payment_link, dict):
            return "Invalid payment payload", 400

        raw_payment_id = payment.get("id")
        raw_payment_link_id = payment_link.get("id")
        if (
            not isinstance(raw_payment_id, str)
            or not isinstance(raw_payment_link_id, str)
        ):
            return "Missing payment identifiers", 400
        payment_id = raw_payment_id.strip()
        payment_link_id = raw_payment_link_id.strip()
        if (
            not _RAZORPAY_PAYMENT_ID_PATTERN.fullmatch(payment_id)
            or not _RAZORPAY_PAYMENT_LINK_ID_PATTERN.fullmatch(
                payment_link_id
            )
        ):
            return "Invalid payment identifiers", 400

        event_id = payment_id
        payload_hash = hashlib.sha256(raw_payload).hexdigest()

        # A final operator disposition is authoritative even when the payment
        # never matched a booking or Razorpay is temporarily unavailable.
        # Recheck after the provider lookup below to close the concurrent
        # operator-resolution race before entitlement can be granted.
        manual_disposition = _find_manual_payment_disposition(
            db,
            payment_id=payment_id,
            payment_link_id=payment_link_id,
        )
        if manual_disposition:
            _persist_manual_disposition_event(
                db,
                event_id=event_id,
                event_type=event_type,
                payload_hash=payload_hash,
                disposition=manual_disposition,
            )
            logger.warning(
                "Delayed payment event preserved terminal disposition | "
                "reconciliation_id=%s | status=%s",
                manual_disposition.id,
                manual_disposition.status,
            )
            return "Terminal disposition preserved", 202

        payment_status = str(payment.get("status") or "").lower()
        payment_link_status = str(payment_link.get("status") or "").lower()
        paid_amount = payment.get("amount")
        paid_currency = str(payment.get("currency") or "").upper()

        existing_event = (
            db.query(WebhookEvent)
            .filter(
                WebhookEvent.provider == "razorpay",
                WebhookEvent.event_id == event_id,
            )
            .first()
        )
        if existing_event and existing_event.status == "DONE":
            return "OK", 200

        if not (
            payment_status == "captured"
            and payment_link_status == "paid"
        ):
            logger.warning(
                "Payment event is not final | payment_status=%s | link_status=%s",
                payment_status,
                payment_link_status,
            )
            return "Not finalized", 409

        booking = (
            db.query(Booking)
            .filter(Booking.razorpay_payment_link_id == payment_link_id)
            .first()
        )
        if not booking:
            reconciliation = _persist_payment_review(
                db,
                event_id=event_id,
                event_type=event_type,
                payload_hash=payload_hash,
                webhook_status="UNMATCHED",
                payment_link_id=payment_link_id,
                reason="BOOKING_NOT_FOUND",
                received_amount=paid_amount,
                currency=paid_currency,
            )
            logger.error(
                "Captured payment requires reconciliation | reconciliation_id=%s",
                reconciliation.id,
            )
            # Keep requesting Razorpay retries in case a transaction/link race
            # is resolved shortly after this event.
            return "Booking not found", 503

        expected_amount = int(booking.amount) * 100
        if (
            isinstance(paid_amount, bool)
            or not isinstance(paid_amount, int)
            or paid_currency != "INR"
            or paid_amount != expected_amount
        ):
            reconciliation = _persist_payment_review(
                db,
                event_id=event_id,
                event_type=event_type,
                payload_hash=payload_hash,
                webhook_status="AMOUNT_MISMATCH",
                payment_link_id=payment_link_id,
                reason="AMOUNT_OR_CURRENCY_MISMATCH",
                booking=booking,
                received_amount=paid_amount,
                currency=paid_currency,
            )
            logger.critical(
                "Captured payment amount requires review | "
                "booking_id=%s | reconciliation_id=%s",
                booking.id,
                reconciliation.id,
            )
            # The exception is durable, so stop an endless provider retry
            # storm while leaving the booking unpaid pending operator review.
            return "Accepted for review", 202

        # The signed webhook is an event snapshot, not proof of the payment's
        # current refund/capture state. Release the read transaction before
        # making two bounded authenticated provider calls, then lock and
        # validate the current booking again before any entitlement change.
        db.rollback()
        (
            current_payment_link,
            current_payment,
        ) = fetch_current_razorpay_capture(
            payment_link_id,
            payment_id,
        )
        booking = (
            db.query(Booking)
            .filter(Booking.razorpay_payment_link_id == payment_link_id)
            .with_for_update()
            .first()
        )
        if not booking:
            reconciliation = _persist_payment_review(
                db,
                event_id=event_id,
                event_type=event_type,
                payload_hash=payload_hash,
                webhook_status="UNMATCHED",
                payment_link_id=payment_link_id,
                reason="BOOKING_NOT_FOUND_AFTER_PROVIDER_LOOKUP",
                received_amount=paid_amount,
                currency=paid_currency,
            )
            logger.error(
                "Captured payment requires reconciliation after provider "
                "verification | reconciliation_id=%s",
                reconciliation.id,
            )
            return "Booking not found", 503

        expected_amount = int(booking.amount) * 100
        if (
            paid_currency != "INR"
            or paid_amount != expected_amount
        ):
            _persist_payment_review(
                db,
                event_id=event_id,
                event_type=event_type,
                payload_hash=payload_hash,
                webhook_status="AMOUNT_MISMATCH",
                payment_link_id=payment_link_id,
                reason="BOOKING_CHANGED_DURING_PROVIDER_LOOKUP",
                booking=booking,
                received_amount=paid_amount,
                currency=paid_currency,
            )
            return "Accepted for review", 202

        manual_disposition = _find_manual_payment_disposition(
            db,
            payment_id=payment_id,
            payment_link_id=payment_link_id,
        )
        if manual_disposition:
            _persist_manual_disposition_event(
                db,
                event_id=event_id,
                event_type=event_type,
                payload_hash=payload_hash,
                disposition=manual_disposition,
            )
            logger.warning(
                "Delayed payment event preserved terminal disposition | "
                "reconciliation_id=%s | status=%s",
                manual_disposition.id,
                manual_disposition.status,
            )
            return "Terminal disposition preserved", 202

        current_validation_error = validate_current_razorpay_capture(
            booking,
            payment_id,
            current_payment_link,
            current_payment,
        )
        if current_validation_error:
            reconciliation = _persist_payment_review(
                db,
                event_id=event_id,
                event_type=event_type,
                payload_hash=payload_hash,
                webhook_status="CURRENT_STATE_REVIEW",
                payment_link_id=payment_link_id,
                reason=current_validation_error,
                booking=booking,
                received_amount=paid_amount,
                currency=paid_currency,
            )
            logger.critical(
                "Current Razorpay state requires review | "
                "booking_id=%s | reconciliation_id=%s | reason=%s",
                booking.id,
                reconciliation.id,
                current_validation_error,
            )
            return "Accepted for review", 202

        existing_event = (
            db.query(WebhookEvent)
            .filter(
                WebhookEvent.provider == "razorpay",
                WebhookEvent.event_id == event_id,
            )
            .with_for_update()
            .first()
        )
        if existing_event and existing_event.status == "DONE":
            return "OK", 200

        if booking.payment_processed:
            if (
                booking.razorpay_payment_id == payment_id
                and booking.status
                in (BookingStatus.PAID, BookingStatus.COMPLETED)
            ):
                # Backfill a durable inbox record for payments handled by the
                # previous production version.
                if not existing_event:
                    existing_event = WebhookEvent(
                        provider="razorpay",
                        event_id=event_id,
                        event_type=event_type,
                        payload_hash=payload_hash,
                        status="DONE",
                        attempts=1,
                        processed_at=now,
                        expires_at=now
                        + timedelta(days=WEBHOOK_EVENT_TTL_DAYS),
                    )
                    db.add(existing_event)
                    try:
                        db.commit()
                    except IntegrityError:
                        db.rollback()
                return "OK", 200
            logger.error(
                "Payment link was already processed with a different payment "
                "| booking_id=%s",
                booking.id,
            )
            reconciliation = _persist_payment_review(
                db,
                event_id=event_id,
                event_type=event_type,
                payload_hash=payload_hash,
                webhook_status="PAYMENT_CONFLICT",
                payment_link_id=payment_link_id,
                reason="BOOKING_ALREADY_PAID_WITH_DIFFERENT_PAYMENT",
                booking=booking,
                received_amount=paid_amount,
                currency=paid_currency,
            )
            logger.critical(
                "Captured payment conflict requires review | "
                "reconciliation_id=%s",
                reconciliation.id,
            )
            return "Accepted for review", 202

        if existing_event:
            existing_event.status = "PROCESSING"
            existing_event.attempts = (existing_event.attempts or 0) + 1
            existing_event.last_error = None
            existing_event.payload_hash = payload_hash
        else:
            existing_event = WebhookEvent(
                provider="razorpay",
                event_id=event_id,
                event_type=event_type,
                payload_hash=payload_hash,
                status="PROCESSING",
                attempts=1,
                expires_at=now + timedelta(days=WEBHOOK_EVENT_TTL_DAYS),
            )
            db.add(existing_event)
            try:
                db.flush()
            except IntegrityError:
                # Another worker completed or claimed the same signed event.
                db.rollback()
                concurrent_event = (
                    db.query(WebhookEvent)
                    .filter(
                        WebhookEvent.provider == "razorpay",
                        WebhookEvent.event_id == event_id,
                    )
                    .first()
                )
                if concurrent_event and concurrent_event.status == "DONE":
                    return "OK", 200
                return "Event is being processed", 503

        capacity_conflict = payment_capacity_conflict(db, booking)

        booking = mark_booking_as_paid(
            db=db,
            payment_link_id=payment_link_id,
            payment_id=payment_id,
            payment_mode=RAZORPAY_MODE,
            commit=False,
        )
        if not booking:
            raise RuntimeError("payment_update_conflict")

        _ensure_booking_fulfillment(
            db,
            booking,
            capacity_conflict=capacity_conflict,
        )

        user = (
            db.query(User)
            .filter(User.whatsapp_id == booking.whatsapp_id)
            .first()
        )
        if user:
            user.flow_state = PAYMENT_CONFIRMED
            user.last_payment_link = None

        prior_reconciliation = (
            db.query(PaymentReconciliation)
            .filter(
                PaymentReconciliation.provider == "razorpay",
                PaymentReconciliation.payment_id == payment_id,
                PaymentReconciliation.status == "OPEN",
            )
            .first()
        )
        if prior_reconciliation and not capacity_conflict:
            prior_reconciliation.status = "AUTO_RESOLVED"
            prior_reconciliation.resolved_at = now
            prior_reconciliation.resolved_by = "payment_webhook"
            prior_reconciliation.resolution_note = (
                "Booking and amount matched on a later signed delivery."
            )
        elif capacity_conflict:
            _upsert_payment_reconciliation(
                db,
                payment_id=payment_id,
                payment_link_id=payment_link_id,
                reason="CAPACITY_CONFLICT_AFTER_CAPTURE",
                booking=booking,
                received_amount=paid_amount,
                currency=paid_currency,
            )

        job_ids = [
            enqueue_job(
                db,
                "payment_success_message",
                {"booking_id": booking.id},
                dedupe_key=f"payment:{payment_id}:success-message",
            ).id
        ]
        if BOOKING_NOTIFICATION_EMAILS:
            job_ids.append(
                enqueue_job(
                    db,
                    "booking_notification",
                    {"booking_id": booking.id},
                    dedupe_key=f"payment:{payment_id}:booking-notification",
                ).id
            )
        if AUTO_SEND_RECEIPTS:
            job_ids.append(
                enqueue_job(
                    db,
                    "payment_receipt",
                    {"booking_id": booking.id},
                    dedupe_key=f"payment:{payment_id}:receipt",
                ).id
            )

        existing_event.status = "DONE"
        existing_event.processed_at = now
        existing_event.last_error = None
        existing_event.expires_at = now + timedelta(
            days=WEBHOOK_EVENT_TTL_DAYS
        )
        db.commit()

        # The committed outbox is the source of truth. This fast path reduces
        # user-visible latency; a worker safely handles anything left behind.
        for job_id in job_ids:
            submit_outbox_job(job_id)

        record_event(
            "payment_confirmed",
            {
                "booking_id": booking.id,
                "amount": booking.amount,
                "mode": RAZORPAY_MODE,
                "capacity_conflict": bool(capacity_conflict),
            },
            user_id=getattr(user, "id", None),
        )
        logger.info("Payment confirmed | booking_id=%s", booking.id)
        return "OK", 200

    except Exception as exc:
        db.rollback()
        logger.exception(
            "Razorpay webhook processing failed; retry requested | "
            "request_id=%s",
            getattr(g, "request_id", "unknown"),
        )

        # Persist a privacy-minimised failure marker when the database is
        # available. A later signed retry can safely resume this event.
        if event_id:
            try:
                failed_event = (
                    db.query(WebhookEvent)
                    .filter(
                        WebhookEvent.provider == "razorpay",
                        WebhookEvent.event_id == event_id,
                    )
                    .first()
                )
                if failed_event and failed_event.status != "DONE":
                    failed_event.status = "FAILED"
                    failed_event.attempts = (failed_event.attempts or 0) + 1
                    failed_event.last_error = type(exc).__name__[:500]
                    failed_event.expires_at = utc_now() + timedelta(
                        days=WEBHOOK_EVENT_TTL_DAYS
                    )
                elif not failed_event:
                    db.add(
                        WebhookEvent(
                            provider="razorpay",
                            event_id=event_id,
                            event_type=event_type,
                            payload_hash=payload_hash,
                            status="FAILED",
                            attempts=1,
                            last_error=type(exc).__name__[:500],
                            expires_at=utc_now()
                            + timedelta(days=WEBHOOK_EVENT_TTL_DAYS),
                        )
                    )
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("Unable to record failed payment webhook")

        return "Temporary processing failure", 503

    finally:
        db.close()
        
