from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError, ConnectTimeoutError

from models import PaymentReconciliation
from services import email_service


@pytest.fixture
def configured_ses(monkeypatch):
    client = MagicMock()
    client.send_email.return_value = {"MessageId": "ses-message-123"}
    monkeypatch.setattr(email_service, "_get_ses_client", lambda: client)
    monkeypatch.setattr(email_service, "SES_REGION", "ap-south-1")
    monkeypatch.setattr(
        email_service,
        "SES_FROM_EMAIL",
        "notifications@example.test",
    )
    monkeypatch.setattr(
        email_service,
        "SES_CONFIGURATION_SET",
        "nyaysetu-transactional",
    )
    monkeypatch.setattr(
        email_service,
        "AWS_ACCESS_KEY_ID",
        "test-access-key-id-123456",
    )
    monkeypatch.setattr(
        email_service,
        "AWS_SECRET_ACCESS_KEY",
        "s" * 40,
    )
    monkeypatch.setattr(email_service, "AWS_SESSION_TOKEN", "")
    return client


def test_ses_success_uses_one_private_utf8_request_and_deduplicates(
    configured_ses,
):
    result = email_service._send_via_ses(
        "Booking confirmed",
        "Your booking is confirmed.",
        [
            "first@example.test",
            "second@example.test",
            "first@example.test",
        ],
        event_type="booking_notification",
        event_id="booking-42",
    )

    assert result is True
    configured_ses.send_email.assert_called_once_with(
        FromEmailAddress="notifications@example.test",
        Destination={
            "BccAddresses": [
                "first@example.test",
                "second@example.test",
            ]
        },
        Content={
            "Simple": {
                "Subject": {
                    "Data": "Booking confirmed",
                    "Charset": "UTF-8",
                },
                "Body": {
                    "Text": {
                        "Data": "Your booking is confirmed.",
                        "Charset": "UTF-8",
                    }
                },
            }
        },
        ConfigurationSetName="nyaysetu-transactional",
        EmailTags=[
            {
                "Name": "nyaysetu_event_type",
                "Value": "booking_notification",
            },
            {"Name": "nyaysetu_event_id", "Value": "booking-42"},
        ],
    )
    payload = configured_ses.send_email.call_args.kwargs
    assert "ToAddresses" not in payload["Destination"]
    assert "CcAddresses" not in payload["Destination"]


def test_ses_omits_optional_configuration_set(configured_ses, monkeypatch):
    monkeypatch.setattr(email_service, "SES_CONFIGURATION_SET", "")

    assert (
        email_service._send_via_ses(
            "Operational update",
            "A bounded background task completed.",
            ["operations@example.test"],
        )
        is True
    )

    payload = configured_ses.send_email.call_args.kwargs
    assert "ConfigurationSetName" not in payload
    assert payload["EmailTags"] == [
        {"Name": "nyaysetu_event_type", "Value": "operational"},
        {"Name": "nyaysetu_event_id", "Value": "unknown"},
    ]


def test_ses_requires_configuration_set_outside_test_and_development(
    configured_ses,
    monkeypatch,
):
    monkeypatch.setattr(email_service, "ENV", "production")
    monkeypatch.setattr(email_service, "SES_CONFIGURATION_SET", "")

    assert (
        email_service._send_via_ses(
            "Operational update",
            "A bounded background task completed.",
            ["operations@example.test"],
        )
        is False
    )
    configured_ses.send_email.assert_not_called()


def test_ses_sanitizes_event_tags_to_the_provider_character_contract(
    configured_ses,
):
    assert (
        email_service._send_via_ses(
            "Operational update",
            "A bounded background task completed.",
            ["operations@example.test"],
            event_type="support.request/v2",
            event_id="हिंदी:42",
        )
        is True
    )

    assert configured_ses.send_email.call_args.kwargs["EmailTags"] == [
        {"Name": "nyaysetu_event_type", "Value": "support_request_v2"},
        {"Name": "nyaysetu_event_id", "Value": "_42"},
    ]


def test_aws_transport_loggers_cannot_inherit_debug_payload_logging():
    for name in ("boto3", "botocore", "urllib3"):
        assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING


def test_ses_client_is_lazy_and_disables_immediate_sdk_retries(
    monkeypatch,
):
    client = MagicMock()
    boto_client = MagicMock(return_value=client)
    monkeypatch.setattr(email_service, "_SES_CLIENT", None)
    monkeypatch.setattr(email_service.boto3, "client", boto_client)
    monkeypatch.setattr(email_service, "SES_REGION", "ap-south-1")
    monkeypatch.setattr(
        email_service,
        "SES_CONNECT_TIMEOUT_SECONDS",
        4.0,
    )
    monkeypatch.setattr(
        email_service,
        "SES_READ_TIMEOUT_SECONDS",
        12.0,
    )
    monkeypatch.setattr(
        email_service,
        "AWS_ACCESS_KEY_ID",
        "test-access-key-id-123456",
    )
    monkeypatch.setattr(
        email_service,
        "AWS_SECRET_ACCESS_KEY",
        "s" * 40,
    )
    monkeypatch.setattr(
        email_service,
        "AWS_SESSION_TOKEN",
        "temporary-session-token",
    )

    assert email_service._get_ses_client() is client
    assert email_service._get_ses_client() is client
    boto_client.assert_called_once()

    args = boto_client.call_args.args
    kwargs = boto_client.call_args.kwargs
    assert args == ("sesv2",)
    assert kwargs["region_name"] == "ap-south-1"
    assert kwargs["aws_access_key_id"] == "test-access-key-id-123456"
    assert kwargs["aws_secret_access_key"] == "s" * 40
    assert kwargs["aws_session_token"] == "temporary-session-token"
    sdk_config = kwargs["config"]
    assert sdk_config.connect_timeout == 4.0
    assert sdk_config.read_timeout == 12.0
    assert sdk_config.retries["total_max_attempts"] == 1


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("SES_REGION", ""),
        ("SES_FROM_EMAIL", ""),
        ("AWS_ACCESS_KEY_ID", ""),
        ("AWS_SECRET_ACCESS_KEY", ""),
    ],
)
def test_ses_missing_configuration_skips_request(
    configured_ses,
    monkeypatch,
    setting,
    value,
):
    monkeypatch.setattr(email_service, setting, value)

    result = email_service._send_via_ses(
        "Booking confirmed",
        "Your booking is confirmed.",
        ["user@example.test"],
    )

    assert result is False
    configured_ses.send_email.assert_not_called()


@pytest.mark.parametrize(
    "recipients",
    [
        [],
        [" ", ""],
        ["valid@example.test", "not-an-email"],
    ],
)
def test_ses_missing_recipients_skips_request(
    configured_ses,
    recipients,
):
    result = email_service._send_via_ses(
        "Booking confirmed",
        "Your booking is confirmed.",
        recipients,
    )

    assert result is False
    configured_ses.send_email.assert_not_called()


def test_send_email_does_not_replace_an_explicit_empty_recipient_list(
    configured_ses,
    monkeypatch,
):
    monkeypatch.setattr(
        email_service,
        "BOOKING_NOTIFICATION_EMAILS",
        ["bookings@example.test"],
    )

    assert email_service.send_email("Daily report", "No bookings.", []) is False
    configured_ses.send_email.assert_not_called()


@pytest.mark.parametrize(
    ("subject", "body"),
    [
        ("", "Body"),
        ("s" * 201, "Body"),
        ("Subject", "b" * 100_001),
    ],
    ids=("empty-subject", "oversized-subject", "oversized-body"),
)
def test_ses_rejects_invalid_content_bounds(
    configured_ses,
    subject,
    body,
):
    assert (
        email_service._send_via_ses(
            subject,
            body,
            ["operations@example.test"],
        )
        is False
    )
    configured_ses.send_email.assert_not_called()


def test_ses_rejects_more_than_fifty_unique_recipients(configured_ses):
    recipients = [f"recipient-{index}@example.test" for index in range(51)]

    result = email_service._send_via_ses(
        "Booking confirmed",
        "Your booking is confirmed.",
        recipients,
    )

    assert result is False
    configured_ses.send_email.assert_not_called()


@pytest.mark.parametrize("response", [{}, {"MessageId": ""}])
def test_ses_requires_nonempty_message_id(
    configured_ses,
    response,
    caplog,
):
    configured_ses.send_email.return_value = response

    with caplog.at_level(logging.ERROR):
        result = email_service._send_via_ses(
            "Booking confirmed",
            "Your booking is confirmed.",
            ["user@example.test"],
        )

    assert result is False
    configured_ses.send_email.assert_called_once()
    assert "message identifier" in caplog.text.lower()


def test_ses_errors_do_not_retry_or_leak_secrets_or_message_data(
    configured_ses,
    caplog,
):
    secret = "s" * 40
    recipient = "private.user@example.test"
    body = "Sensitive legal support message"
    configured_ses.send_email.side_effect = RuntimeError(
        f"{secret} {recipient} {body}"
    )

    with caplog.at_level(logging.ERROR):
        result = email_service._send_via_ses(
            "Private subject",
            body,
            [recipient],
            event_type="support_notification",
            event_id="support-93",
        )

    assert result is False
    configured_ses.send_email.assert_called_once()
    assert secret not in caplog.text
    assert recipient not in caplog.text
    assert body not in caplog.text
    assert "RuntimeError" in caplog.text


def test_ses_client_error_is_single_attempt_and_logs_only_safe_code(
    configured_ses,
    caplog,
):
    recipient = "private.client-error@example.test"
    body = "Sensitive client-error legal narrative"
    error_secret = "provider-error-secret-value"
    configured_ses.send_email.side_effect = ClientError(
        {
            "Error": {
                "Code": "MessageRejected",
                "Message": (
                    f"{error_secret}; recipient={recipient}; body={body}"
                ),
            },
            "ResponseMetadata": {
                "RequestId": "private-provider-request-id",
                "HTTPStatusCode": 400,
            },
        },
        "SendEmail",
    )

    with caplog.at_level(logging.ERROR, logger=email_service.__name__):
        result = email_service._send_via_ses(
            "Private client-error subject",
            body,
            [recipient],
            event_type="support_notification",
            event_id="support-94",
        )

    assert result is False
    configured_ses.send_email.assert_called_once()
    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == email_service.__name__
    ]
    assert messages == ["Amazon SES rejected email | code=MessageRejected"]
    for private_value in (
        recipient,
        body,
        error_secret,
        "private-provider-request-id",
    ):
        assert private_value not in caplog.text


def test_ses_connect_timeout_is_single_attempt_and_logs_only_exception_type(
    configured_ses,
    caplog,
):
    recipient = "private.timeout@example.test"
    body = "Sensitive timeout legal narrative"
    error_secret = "transport-timeout-secret-value"
    configured_ses.send_email.side_effect = ConnectTimeoutError(
        endpoint_url=(
            "https://email.ap-south-1.amazonaws.com/"
            f"{error_secret}/{recipient}/{body}"
        )
    )

    with caplog.at_level(logging.ERROR, logger=email_service.__name__):
        result = email_service._send_via_ses(
            "Private timeout subject",
            body,
            [recipient],
            event_type="support_notification",
            event_id="support-95",
        )

    assert result is False
    configured_ses.send_email.assert_called_once()
    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == email_service.__name__
    ]
    assert messages == [
        "Amazon SES email transport failed | reason=ConnectTimeoutError"
    ]
    for private_value in (recipient, body, error_secret):
        assert private_value not in caplog.text


def test_payment_review_email_deduplicates_recipients_and_preserves_zero(
    configured_ses,
    monkeypatch,
):
    monkeypatch.setattr(
        email_service,
        "PAYMENT_RECONCILIATION_EMAILS",
        [
            "finance@example.test",
            "operations@example.test",
            "finance@example.test",
        ],
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

    payload = configured_ses.send_email.call_args.kwargs
    assert payload["Destination"]["BccAddresses"] == [
        "finance@example.test",
        "operations@example.test",
    ]
    body = payload["Content"]["Simple"]["Body"]["Text"]["Data"]
    assert "Expected (paise)  : 0" in body
    assert "Received (paise)  : 0" in body
    assert "pay_review_email" not in body


def test_booking_alert_does_not_copy_contact_or_legal_matter_data(
    configured_ses,
    monkeypatch,
):
    monkeypatch.setattr(
        email_service,
        "BOOKING_NOTIFICATION_EMAILS",
        ["bookings@example.test"],
    )
    booking = SimpleNamespace(
        id=73,
        date="2026-08-05",
        slot_readable="10:00 AM - 10:30 AM",
        name="Private Person",
        phone="919876543210",
        whatsapp_id="919876543210",
        category="Sensitive legal category",
        district_name="Private District",
    )

    assert email_service.send_booking_notification_email(booking) is True

    body = configured_ses.send_email.call_args.kwargs[
        "Content"
    ]["Simple"]["Body"]["Text"]["Data"]
    assert "Booking ID : 73" in body
    for private_value in (
        booking.name,
        booking.phone,
        booking.whatsapp_id,
        booking.category,
        booking.district_name,
    ):
        assert private_value not in body


def test_support_alert_does_not_copy_subject_or_narrative(
    configured_ses,
    monkeypatch,
):
    monkeypatch.setattr(
        email_service,
        "SUPPORT_NOTIFICATION_EMAILS",
        ["support@example.test"],
    )
    support_request = SimpleNamespace(
        id=19,
        case_id="NS-CASE-19",
        request_type="GENERAL",
        priority="NORMAL",
        sla_due_at="2026-08-02T10:00:00",
        subject="Private support subject",
        message="Sensitive legal narrative and phone 919876543210",
    )

    assert email_service.send_support_request_email(support_request) is True

    body = configured_ses.send_email.call_args.kwargs[
        "Content"
    ]["Simple"]["Body"]["Text"]["Data"]
    assert "Ticket ID : NSH-000019" in body
    assert support_request.subject not in body
    assert support_request.message not in body
