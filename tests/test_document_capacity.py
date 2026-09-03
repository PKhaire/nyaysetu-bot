"""Global daily-capacity tests for the integrated Document Studio release."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import DocumentCapacityReservation, User
from services import document_catalogue as catalogue
from services import document_capacity_service as capacity
from services.document_capacity_service import (
    DocumentStudioCapacityExhausted,
    business_date_for,
    capacity_snapshot,
    release_capacity,
)
from services.document_studio_rc9_service import (
    cancel_order,
    confirm_answers,
    create_or_resume_order,
    save_answer,
)


@pytest.fixture
def capacity_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _enable_product(monkeypatch, *, daily_capacity: int) -> None:
    monkeypatch.setattr(catalogue, "DOCUMENT_STUDIO_ENABLED", True)
    monkeypatch.setattr(catalogue, "DOCUMENT_STUDIO_PRICE_INR", 299)
    monkeypatch.setattr(
        catalogue,
        "DOCUMENT_STUDIO_PRODUCT_ALLOWLIST",
        frozenset({catalogue.PRODUCT_CODE}),
    )
    monkeypatch.setattr(
        capacity,
        "DOCUMENT_STUDIO_DAILY_CAPACITY",
        daily_capacity,
    )


def _add_user(db, suffix: str) -> User:
    user = User(
        whatsapp_id=f"91991111{suffix}",
        case_id=f"NS-CAP-{suffix}",
    )
    db.add(user)
    db.flush()
    return user


def test_business_date_uses_configured_india_timezone():
    before_midnight = datetime(
        2026,
        9,
        3,
        18,
        29,
        tzinfo=timezone.utc,
    )
    after_midnight = datetime(
        2026,
        9,
        3,
        18,
        30,
        tzinfo=timezone.utc,
    )

    assert business_date_for(before_midnight).isoformat() == "2026-09-03"
    assert business_date_for(after_midnight).isoformat() == "2026-09-04"


def test_global_limit_rejects_next_user_without_creating_order(
    monkeypatch,
    capacity_db,
):
    _enable_product(monkeypatch, daily_capacity=2)
    db = capacity_db()
    try:
        first = _add_user(db, "0001")
        second = _add_user(db, "0002")
        third = _add_user(db, "0003")

        create_or_resume_order(db, first.id)
        create_or_resume_order(db, second.id)
        with pytest.raises(DocumentStudioCapacityExhausted):
            create_or_resume_order(db, third.id)

        snapshot = capacity_snapshot(db)
        assert snapshot == {
            "business_date": business_date_for().isoformat(),
            "timezone": "Asia/Kolkata",
            "limit": 2,
            "reserved": 2,
            "consumed": 0,
            "released": 0,
            "used": 2,
            "remaining": 0,
            "exhausted": True,
        }
    finally:
        db.close()


def test_resuming_same_draft_does_not_use_another_slot(
    monkeypatch,
    capacity_db,
):
    _enable_product(monkeypatch, daily_capacity=1)
    db = capacity_db()
    try:
        user = _add_user(db, "0010")
        first = create_or_resume_order(db, user.id)
        resumed = create_or_resume_order(db, user.id)

        assert resumed.id == first.id
        assert db.query(DocumentCapacityReservation).count() == 1
        assert capacity_snapshot(db)["used"] == 1
    finally:
        db.close()


def test_customer_cancellation_releases_unconsumed_slot(
    monkeypatch,
    capacity_db,
):
    _enable_product(monkeypatch, daily_capacity=1)
    db = capacity_db()
    try:
        first_user = _add_user(db, "0020")
        second_user = _add_user(db, "0021")
        first_order = create_or_resume_order(db, first_user.id)

        cancel_order(db, first_order)
        second_order = create_or_resume_order(db, second_user.id)

        reservations = (
            db.query(DocumentCapacityReservation)
            .order_by(DocumentCapacityReservation.id)
            .all()
        )
        assert second_order.user_id == second_user.id
        assert [item.status for item in reservations] == [
            "RELEASED",
            "RESERVED",
        ]
        assert reservations[0].release_reason == "CUSTOMER_CANCELLED"
        assert capacity_snapshot(db)["remaining"] == 0
    finally:
        db.close()


def test_ineligible_route_releases_slot_before_payment(
    monkeypatch,
    capacity_db,
):
    _enable_product(monkeypatch, daily_capacity=1)
    db = capacity_db()
    try:
        user = _add_user(db, "0030")
        order = create_or_resume_order(db, user.id)

        save_answer(order, "OTHER", db=db)

        reservation = db.query(DocumentCapacityReservation).one()
        assert order.state == "ROUTED_OUT"
        assert reservation.status == "RELEASED"
        assert reservation.release_reason == "INELIGIBLE_ROUTE_OUT"
        assert capacity_snapshot(db)["remaining"] == 1
    finally:
        db.close()


def test_confirmed_draft_consumes_slot_and_cannot_be_released(
    monkeypatch,
    capacity_db,
):
    _enable_product(monkeypatch, daily_capacity=1)
    db = capacity_db()
    try:
        first_user = _add_user(db, "0040")
        second_user = _add_user(db, "0041")
        order = create_or_resume_order(db, first_user.id)
        order.state = "DRAFTING"
        order.current_step = "review"

        confirm_answers(db, order)

        reservation = db.query(DocumentCapacityReservation).one()
        assert reservation.status == "CONSUMED"
        assert reservation.consumed_at is not None
        assert release_capacity(
            db,
            order,
            reason="PAYMENT_FAILED",
        ) is False
        with pytest.raises(DocumentStudioCapacityExhausted):
            create_or_resume_order(db, second_user.id)
    finally:
        db.close()


def test_postgresql_reservations_take_transaction_advisory_lock():
    class _Dialect:
        name = "postgresql"

    class _Bind:
        dialect = _Dialect()

    class _Db:
        statement = None
        params = None

        def get_bind(self):
            return _Bind()

        def execute(self, statement, params):
            self.statement = str(statement)
            self.params = params

    db = _Db()
    capacity._lock_business_date(
        db,
        business_date_for(
            datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
        ),
    )

    assert "pg_advisory_xact_lock" in db.statement
    assert isinstance(db.params["lock_key"], int)
