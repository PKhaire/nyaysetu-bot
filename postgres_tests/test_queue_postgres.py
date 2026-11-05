"""Queue integration against the explicitly isolated GitHub Actions service."""

from __future__ import annotations

import os
from datetime import date

import pytest


CI_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/nyaysetu_ci"


def test_postgresql_queue_reaches_searches_and_counts_201_records(monkeypatch):
    if os.environ.get("NYAYSETU_POSTGRES_QUEUE_CI") != "1":
        pytest.skip("Run explicitly in the isolated PostgreSQL CI job")
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("DATABASE_URL") != CI_DATABASE_URL
    ):
        pytest.fail("Refusing to run outside the designated disposable CI database")

    # Do not allow application startup to use real external integrations.
    for key, value in {
        "ENV": "test",
        "ADMIN_TOKEN": "synthetic-ci-admin-token",
        "ALLOW_INSECURE_WEBHOOKS": "false",
        "WHATSAPP_APP_SECRET": "synthetic-ci-secret",
        "WHATSAPP_VERIFY_TOKEN": "synthetic-ci-verify",
        "WHATSAPP_PHONE_ID": "synthetic-ci-phone",
        "WHATSAPP_TOKEN": "synthetic-ci-token",
        "RAZORPAY_KEY_ID": "rzp_test_synthetic",
        "RAZORPAY_KEY_SECRET": "synthetic-ci-secret",
        "RAZORPAY_WEBHOOK_SECRET": "synthetic-ci-webhook",
        "RAZORPAY_MODE": "test",
    }.items():
        monkeypatch.setenv(key, value)

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import admin
    from app import app
    from models import Booking, BookingFulfillment, BookingStatus

    engine = create_engine(CI_DATABASE_URL)
    connection = engine.connect()
    transaction = connection.begin()
    try:
        sessions = sessionmaker(
            bind=connection,
            autoflush=False,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        monkeypatch.setattr(admin, "SessionLocal", sessions)
        monkeypatch.setattr(admin, "ADMIN_TOKEN", "synthetic-ci-admin-token")
        app.config.update(TESTING=True)
        db = sessions()
        try:
            assert db.query(Booking).count() == 0
            assert db.query(BookingFulfillment).count() == 0
            for index in range(201):
                booking = Booking(
                    whatsapp_id=f"919000{index:06d}",
                    name=f"Synthetic CI Queue User {index}",
                    phone=f"919000{index:06d}",
                    state_name="Maharashtra",
                    district_name="Pune",
                    category="Family",
                    subcategory="Other Family Issue",
                    date=date(2099, 8, 3),
                    slot_code="10_11",
                    slot_readable="10:00 AM - 11:00 AM",
                    amount=499,
                    status=BookingStatus.PAID,
                    payment_token=f"synthetic-pg-queue-{index}",
                )
                db.add(booking)
                db.flush()
                db.add(BookingFulfillment(
                    booking_id=booking.id,
                    status="ASSIGNED" if index == 200 else "UNASSIGNED",
                ))
            db.flush()
            client = app.test_client()
            headers = {"Authorization": "Bearer synthetic-ci-admin-token"}
            first = client.get("/admin/fulfillments?limit=200", headers=headers)
            second = client.get("/admin/fulfillments?limit=200&offset=200", headers=headers)
            assert first.status_code == second.status_code == 200
            assert first.get_json()["total"] == 201
            assert first.get_json()["status_counts"]["UNASSIGNED"] == 200
            assert first.get_json()["status_counts"]["ASSIGNED"] == 1
            first_ids = {row["booking_id"] for row in first.get_json()["items"]}
            second_ids = {row["booking_id"] for row in second.get_json()["items"]}
            assert len(first_ids) == 200
            assert len(second_ids) == 1
            assert first_ids.isdisjoint(second_ids)
            search = client.get(
                "/admin/fulfillments",
                query_string={"search": "Synthetic CI Queue User 200"},
                headers=headers,
            )
            assert search.status_code == 200
            assert search.get_json()["total"] == 1
            assert {row["booking_id"] for row in search.get_json()["items"]} == second_ids
        finally:
            db.close()
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()
