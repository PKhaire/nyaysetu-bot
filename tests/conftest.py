"""Shared integration-test fixtures.

The application is configured against an in-memory database before it is
imported.  This prevents a test run from ever connecting to a developer or
production database through ambient environment variables.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


os.environ["ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ALLOW_INSECURE_WEBHOOKS"] = "false"
os.environ["WHATSAPP_APP_SECRET"] = "test-whatsapp-secret"
os.environ["WHATSAPP_VERIFY_TOKEN"] = "test-verify-token"
os.environ["WHATSAPP_PHONE_ID"] = "test-phone-id"
os.environ["WHATSAPP_TOKEN"] = "test-whatsapp-token"
os.environ["RAZORPAY_KEY_ID"] = "rzp_test_key"
os.environ["RAZORPAY_KEY_SECRET"] = "rzp_test_key_secret"
os.environ["RAZORPAY_WEBHOOK_SECRET"] = "test-razorpay-secret"
os.environ["RAZORPAY_MODE"] = "test"


@pytest.fixture(scope="session")
def app_module():
    import app as application

    application.app.config.update(TESTING=True)
    return application


@pytest.fixture
def isolated_app_db(monkeypatch, app_module):
    """Give every app-route test a fresh, process-local database."""

    from db import Base

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

    monkeypatch.setattr(app_module, "get_db", testing_session)
    monkeypatch.setattr(app_module, "record_event", lambda *args, **kwargs: None)

    app_module.user_message_times.clear()
    app_module.user_last_ai_call.clear()
    app_module.global_request_times.clear()
    app_module._rate_limit_notice_times.clear()
    app_module.maintenance_last_sent.clear()
    app_module._rate_limit_last_cleanup = 0.0

    try:
        yield testing_session
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def transport_spies(monkeypatch, app_module):
    """Replace all network-facing WhatsApp operations with successful spies."""

    spies = {
        "text": MagicMock(return_value={"ok": True}),
        "buttons": MagicMock(return_value={"ok": True}),
        "list": MagicMock(return_value={"ok": True}),
        "home": MagicMock(return_value={"ok": True}),
        "typing_on": MagicMock(return_value={"ok": True}),
        "typing_off": MagicMock(return_value={"ok": True}),
        "receipt": MagicMock(return_value={"ok": True}),
    }
    monkeypatch.setattr(app_module, "send_text", spies["text"])
    monkeypatch.setattr(app_module, "send_buttons", spies["buttons"])
    monkeypatch.setattr(app_module, "send_list_picker", spies["list"])
    monkeypatch.setattr(app_module, "send_home", spies["home"])
    monkeypatch.setattr(app_module, "send_typing_on", spies["typing_on"])
    monkeypatch.setattr(app_module, "send_typing_off", spies["typing_off"])
    monkeypatch.setattr(
        app_module,
        "send_payment_receipt_pdf",
        spies["receipt"],
    )
    return spies


@pytest.fixture
def deferred_threads(monkeypatch, app_module):
    """Keep opportunistic outbox fast-path work deterministic in route tests."""

    created = []

    monkeypatch.setattr(
        app_module,
        "submit_outbox_job",
        lambda job_id: created.append(job_id),
    )
    return created


@pytest.fixture
def client(app_module):
    return app_module.app.test_client()
