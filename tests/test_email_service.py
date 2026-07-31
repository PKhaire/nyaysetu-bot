from __future__ import annotations

import logging
from unittest.mock import MagicMock

import httpx
import pytest

from models import PaymentReconciliation
from services import email_service


@pytest.fixture
def configured_sendgrid(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(email_service, "_HTTP_CLIENT", client)
    monkeypatch.setattr(
        email_service,
        "SENDGRID_API_KEY",
        "SG.production-secret",
    )
    monkeypatch.setattr(
        email_service,
        "SENDGRID_FROM_EMAIL",
        "notifications@example.test",
    )
    return client


def test_sendgrid_success_uses_v3_payload_and_explicit_timeouts(
    configured_sendgrid,
):
    configured_sendgrid.post.return_value.status_code = 202

    result = email_service._send_via_sendgrid(
        "Booking confirmed",
        "Your booking is confirmed.",
        [
            "first@example.test",
            "second@example.test",
            "first@example.test",
        ],
    )

    assert result is True
    configured_sendgrid.post.assert_called_once()
    url = configured_sendgrid.post.call_args.args[0]
    kwargs = configured_sendgrid.post.call_args.kwargs
    assert url == "https://api.sendgrid.com/v3/mail/send"
    assert kwargs["headers"]["Authorization"] == "Bearer SG.production-secret"
    assert kwargs["json"] == {
        "personalizations": [
            {"to": [{"email": "first@example.test"}]},
            {"to": [{"email": "second@example.test"}]},
        ],
        "from": {"email": "notifications@example.test"},
        "subject": "Booking confirmed",
        "content": [
            {
                "type": "text/plain",
                "value": "Your booking is confirmed.",
            }
        ],
    }
    assert (
        kwargs["timeout"].connect
        == email_service.SENDGRID_CONNECT_TIMEOUT_SECONDS
    )
    assert (
        kwargs["timeout"].read
        == email_service.SENDGRID_READ_TIMEOUT_SECONDS
    )


def test_sendgrid_timeout_returns_false_without_retry(
    configured_sendgrid,
    caplog,
):
    configured_sendgrid.post.side_effect = httpx.ReadTimeout(
        "provider stalled"
    )

    with caplog.at_level(logging.ERROR):
        result = email_service._send_via_sendgrid(
            "Booking confirmed",
            "Your booking is confirmed.",
            ["user@example.test"],
        )

    assert result is False
    configured_sendgrid.post.assert_called_once()
    assert "ReadTimeout" in caplog.text


@pytest.mark.parametrize("status_code", [400, 429, 500])
def test_sendgrid_non_2xx_returns_false(
    configured_sendgrid,
    caplog,
    status_code,
):
    configured_sendgrid.post.return_value.status_code = status_code

    with caplog.at_level(logging.ERROR):
        result = email_service._send_via_sendgrid(
            "Booking confirmed",
            "Your booking is confirmed.",
            ["user@example.test"],
        )

    assert result is False
    assert f"status={status_code}" in caplog.text


@pytest.mark.parametrize(
    ("api_key", "from_email", "recipients"),
    [
        ("", "notifications@example.test", ["user@example.test"]),
        ("SG.production-secret", "", ["user@example.test"]),
        ("SG.production-secret", "notifications@example.test", []),
        ("SG.production-secret", "notifications@example.test", [" ", ""]),
    ],
)
def test_sendgrid_missing_config_or_recipients_skips_request(
    configured_sendgrid,
    monkeypatch,
    api_key,
    from_email,
    recipients,
):
    monkeypatch.setattr(email_service, "SENDGRID_API_KEY", api_key)
    monkeypatch.setattr(email_service, "SENDGRID_FROM_EMAIL", from_email)

    result = email_service._send_via_sendgrid(
        "Booking confirmed",
        "Your booking is confirmed.",
        recipients,
    )

    assert result is False
    configured_sendgrid.post.assert_not_called()


def test_sendgrid_errors_do_not_leak_secrets_or_message_data(
    configured_sendgrid,
    caplog,
):
    secret = "SG.production-secret"
    recipient = "private.user@example.test"
    body = "Sensitive legal support message"
    configured_sendgrid.post.side_effect = httpx.ConnectTimeout(
        f"{secret} {recipient} {body}"
    )

    with caplog.at_level(logging.ERROR):
        result = email_service._send_via_sendgrid(
            "Private subject",
            body,
            [recipient],
        )

    assert result is False
    assert secret not in caplog.text
    assert recipient not in caplog.text
    assert body not in caplog.text
    assert "ConnectTimeout" in caplog.text


def test_payment_review_email_deduplicates_recipients_and_preserves_zero(
    configured_sendgrid,
    monkeypatch,
):
    configured_sendgrid.post.return_value.status_code = 202
    monkeypatch.setattr(
        email_service,
        "BOOKING_NOTIFICATION_EMAILS",
        ["finance@example.test"],
    )
    monkeypatch.setattr(
        email_service,
        "SUPPORT_NOTIFICATION_EMAILS",
        ["finance@example.test", "operations@example.test"],
    )
    reconciliation = PaymentReconciliation(
        id=42,
        provider="razorpay",
        payment_id="pay_review_email",
        reason="PROVIDER_AMOUNT_MISMATCH",
        status="OPEN",
        expected_amount=0,
        received_amount=0,
        currency="INR",
    )

    assert (
        email_service.send_payment_reconciliation_email(reconciliation)
        is True
    )

    payload = configured_sendgrid.post.call_args.kwargs["json"]
    assert payload["personalizations"] == [
        {"to": [{"email": "finance@example.test"}]},
        {"to": [{"email": "operations@example.test"}]},
    ]
    body = payload["content"][0]["value"]
    assert "Expected (paise)  : 0" in body
    assert "Received (paise)  : 0" in body
