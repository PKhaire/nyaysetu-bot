from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import Booking, BookingStatus, User
from services import booking_service


FIXED_IST = datetime(2026, 7, 29, 10, 30, tzinfo=booking_service.IST)
FIXED_UTC_NAIVE = FIXED_IST.astimezone(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    session = testing_session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(booking_service, "_now_ist", lambda: FIXED_IST)
    monkeypatch.setattr(
        booking_service,
        "_utc_now_naive",
        lambda: FIXED_UTC_NAIVE,
    )


def make_user(db, suffix="1"):
    user = User(
        whatsapp_id=f"91999999999{suffix}",
        case_id=f"NS-TEST{suffix}",
        language="en",
        name="Test User",
    )
    db.add(user)
    db.commit()
    return user


def make_booking(
    db,
    *,
    suffix="1",
    booking_date=None,
    slot_code="3_4",
    status=BookingStatus.PENDING,
    created_at=None,
    payment_processed=False,
    payment_link_id=None,
    payment_id=None,
):
    booking_date = booking_date or FIXED_IST.date()
    booking = Booking(
        whatsapp_id=f"91888888888{suffix}",
        name="Booked User",
        phone=f"91888888888{suffix}",
        state_name="Maharashtra",
        district_name="Pune",
        category="Family",
        subcategory="Divorce",
        date=booking_date,
        slot_code=slot_code,
        slot_readable=booking_service.SLOT_MAP[slot_code],
        amount=499,
        status=status,
        payment_token=f"token-{suffix}",
        razorpay_payment_link_id=payment_link_id,
        razorpay_payment_id=payment_id,
        payment_processed=payment_processed,
        created_at=created_at or FIXED_UTC_NAIVE,
    )
    db.add(booking)
    db.commit()
    return booking


class FakePaymentLinkAPI:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.created_payloads = []
        self.cancelled = []

    def create(self, payload):
        self.created_payloads.append(payload)
        if self.error:
            raise self.error
        return self.response

    def cancel(self, payment_link_id):
        self.cancelled.append(payment_link_id)


class FakeRazorpayClient:
    def __init__(self, response=None, error=None):
        self.payment_link = FakePaymentLinkAPI(response=response, error=error)


def test_afternoon_and_evening_slots_use_24_hour_ist(db):
    rows = booking_service.generate_slots_calendar(
        FIXED_IST.date().isoformat(),
        db=db,
    )
    row_ids = {row["id"] for row in rows}

    assert "slot_10_11" not in row_ids
    assert "slot_12_1" not in row_ids
    assert {"slot_3_4", "slot_6_7", "slot_8_9"} <= row_ids
    assert (
        booking_service._slot_start_at(FIXED_IST.date(), "3_4").hour
        == 15
    )


def test_booking_horizon_is_enforced(monkeypatch, db):
    monkeypatch.setattr(booking_service, "BOOKING_MAX_AHEAD_DAYS", 3)
    too_far = (FIXED_IST.date() + timedelta(days=4)).isoformat()

    valid, message = booking_service.validate_slot(too_far, "10_11")
    rows = booking_service.generate_dates_calendar(db=db)

    assert valid is False
    assert "booking window" in message
    assert all(
        datetime.fromisoformat(row["id"].removeprefix("date_")).date()
        <= FIXED_IST.date() + timedelta(days=3)
        for row in rows
    )


def test_daily_and_per_slot_capacity_hide_unavailable_slots(
    monkeypatch,
    db,
):
    monkeypatch.setattr(booking_service, "BOOKING_MAX_PER_DAY", 3)
    monkeypatch.setattr(booking_service, "BOOKING_MAX_PER_SLOT", 1)
    make_booking(db, suffix="1", slot_code="3_4")
    make_booking(
        db,
        suffix="2",
        slot_code="6_7",
        status=BookingStatus.PAID,
    )

    rows = booking_service.generate_slots_calendar(
        FIXED_IST.date().isoformat(),
        db=db,
    )
    row_ids = {row["id"] for row in rows}

    assert "slot_3_4" not in row_ids
    assert "slot_6_7" not in row_ids
    assert "slot_8_9" in row_ids

    monkeypatch.setattr(booking_service, "BOOKING_MAX_PER_DAY", 2)
    assert (
        booking_service.generate_slots_calendar(
            FIXED_IST.date().isoformat(),
            db=db,
        )
        == []
    )


def test_provider_failure_rolls_back_booking(monkeypatch, db):
    user = make_user(db)
    fake_client = FakeRazorpayClient(error=RuntimeError("provider down"))
    monkeypatch.setattr(
        booking_service,
        "_get_razorpay_client",
        lambda: fake_client,
    )

    booking, message = booking_service.create_booking_temp(
        db=db,
        user=user,
        name=user.name,
        state="Maharashtra",
        district="Pune",
        category="Family",
        subcategory="Divorce",
        date=(FIXED_IST.date() + timedelta(days=1)).isoformat(),
        slot_code="3_4",
    )

    assert booking is None
    assert "try again" in message.lower()
    assert db.query(Booking).count() == 0


def test_booking_uses_its_amount_and_provider_expiry(monkeypatch, db):
    user = make_user(db)
    fake_client = FakeRazorpayClient(
        response={
            "id": "plink_test",
            "short_url": "https://rzp.test/link",
        }
    )
    monkeypatch.setattr(
        booking_service,
        "_get_razorpay_client",
        lambda: fake_client,
    )
    monkeypatch.setattr(booking_service, "BOOKING_PRICE", 777)

    booking, short_url = booking_service.create_booking_temp(
        db=db,
        user=user,
        name=user.name,
        state="Maharashtra",
        district="Pune",
        category="Family",
        subcategory="Divorce",
        date=(FIXED_IST.date() + timedelta(days=1)).isoformat(),
        slot_code="3_4",
    )

    payload = fake_client.payment_link.created_payloads[0]
    assert short_url == "https://rzp.test/link"
    assert booking.status == BookingStatus.PENDING
    assert booking.amount == 777
    assert payload["amount"] == booking.amount * 100
    assert payload["reference_id"] == booking.payment_token
    assert payload["expire_by"] >= int(
        (
            FIXED_UTC_NAIVE.replace(tzinfo=timezone.utc)
            + timedelta(minutes=16)
        ).timestamp()
    )


def test_direct_razorpay_transport_uses_bounded_authenticated_http(
    monkeypatch,
):
    http_client = MagicMock()
    constructor = MagicMock(return_value=http_client)
    monkeypatch.setattr(booking_service.httpx, "Client", constructor)

    client = booking_service._RazorpayHTTPClient()

    kwargs = constructor.call_args.kwargs
    assert kwargs["base_url"] == "https://api.razorpay.com"
    assert kwargs["auth"] == (
        booking_service.RAZORPAY_KEY_ID,
        booking_service.RAZORPAY_KEY_SECRET,
    )
    assert kwargs["follow_redirects"] is False
    assert isinstance(kwargs["timeout"], httpx.Timeout)
    assert kwargs["timeout"].connect <= 5.0
    assert kwargs["timeout"].read == booking_service.RAZORPAY_API_TIMEOUT_SECONDS
    assert client.payment_link._http_client is http_client


def test_direct_razorpay_payment_link_endpoints_validate_responses():
    requests = []

    def handler(request: httpx.Request):
        requests.append(request)
        if request.url.path.endswith("/cancel"):
            return httpx.Response(
                200,
                request=request,
                json={"id": "plink_Valid123", "status": "cancelled"},
            )
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "plink_Valid123",
                "short_url": "https://rzp.test/x",
            },
        )

    client = httpx.Client(
        base_url="https://api.razorpay.com",
        transport=httpx.MockTransport(handler),
    )
    api = booking_service._PaymentLinkAPI(client)
    try:
        created = api.create({"amount": 49_900, "currency": "INR"})
        cancelled = api.cancel("plink_Valid123")
        with pytest.raises(ValueError):
            api.cancel("../invalid")
    finally:
        client.close()

    assert created["id"] == "plink_Valid123"
    assert cancelled["status"] == "cancelled"
    assert [request.method for request in requests] == ["POST", "POST"]
    assert [request.url.path for request in requests] == [
        "/v1/payment_links",
        "/v1/payment_links/plink_Valid123/cancel",
    ]


def test_mark_booking_paid_uses_caller_session_and_is_idempotent(db):
    booking = make_booking(
        db,
        payment_link_id="plink_paid",
        payment_processed=False,
    )

    paid = booking_service.mark_booking_as_paid(
        db=db,
        payment_link_id="plink_paid",
        payment_id="pay_123",
        payment_mode="test",
    )
    replay = booking_service.mark_booking_as_paid(
        db=db,
        payment_link_id="plink_paid",
        payment_id="pay_123",
        payment_mode="test",
    )

    assert paid.id == booking.id
    assert replay.id == booking.id
    assert paid.status == BookingStatus.PAID
    assert paid.payment_processed is True
    assert paid.razorpay_payment_id == "pay_123"
    assert paid.paid_at == FIXED_UTC_NAIVE


def test_confirm_missing_booking_and_expire_with_supplied_session(db):
    missing, message = booking_service.confirm_booking_after_payment(
        db,
        "missing-token",
    )
    old_booking = make_booking(
        db,
        suffix="old",
        created_at=(
            FIXED_UTC_NAIVE
            - timedelta(
                minutes=booking_service.PAYMENT_LINK_TTL_MINUTES + 1
            )
        ),
    )
    fresh_booking = make_booking(db, suffix="fresh")

    expired_count = booking_service.expire_old_pending_bookings(db)

    assert missing is None
    assert message == "Booking not found."
    assert expired_count == 1
    assert db.get(Booking, old_booking.id).status == BookingStatus.EXPIRED
    assert db.get(Booking, fresh_booking.id).status == BookingStatus.PENDING
