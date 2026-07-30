"""Focused tests for the WhatsApp Cloud API transport.

These tests deliberately mock the shared HTTP client so they never contact
Meta.  They cover the two failure modes that matter most for a messaging
transport: rejecting malformed payloads before I/O and avoiding duplicate
user-visible sends when a response is ambiguous.
"""

from __future__ import annotations

import logging
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

from services import whatsapp_service as whatsapp


def _response(
    status_code: int,
    payload: dict,
    *,
    headers: dict | None = None,
) -> httpx.Response:
    request = httpx.Request("POST", "https://graph.facebook.test/messages")
    return httpx.Response(
        status_code,
        json=payload,
        headers=headers,
        request=request,
    )


def _configure_transport(monkeypatch) -> None:
    monkeypatch.setattr(
        whatsapp,
        "WHATSAPP_API_URL",
        "https://graph.facebook.test/messages",
    )
    monkeypatch.setattr(whatsapp, "WHATSAPP_TOKEN", "transport-test-token")


def test_text_and_interactive_fields_are_truncated_before_send(monkeypatch):
    _configure_transport(monkeypatch)
    request = MagicMock(return_value=_response(200, {"messages": [{"id": "1"}]}))
    monkeypatch.setattr(whatsapp._HTTP_CLIENT, "request", request)

    text_result = whatsapp.send_text("919876543210", "x" * 5_000)
    button_result = whatsapp.send_buttons(
        "919876543210",
        "b" * 2_000,
        [{"id": "safe-id", "title": "A title that is much too long"}],
    )

    assert text_result["ok"] is True
    assert button_result["ok"] is True

    text_payload = request.call_args_list[0].kwargs["json"]
    button_payload = request.call_args_list[1].kwargs["json"]
    assert len(text_payload["text"]["body"]) == whatsapp.TEXT_BODY_MAX
    assert (
        len(button_payload["interactive"]["body"]["text"])
        == whatsapp.INTERACTIVE_BODY_MAX
    )
    assert (
        len(
            button_payload["interactive"]["action"]["buttons"][0]["reply"][
                "title"
            ]
        )
        == whatsapp.BUTTON_TITLE_MAX
    )


@pytest.mark.parametrize(
    "send",
    [
        lambda: whatsapp.send_buttons(
            "919876543210",
            "Choose",
            [
                {"id": "one", "title": "One"},
                {"id": "two", "title": "Two"},
                {"id": "three", "title": "Three"},
                {"id": "four", "title": "Four"},
            ],
        ),
        lambda: whatsapp.send_list_picker(
            "919876543210",
            "Options",
            "Choose",
            [
                {
                    "id": f"row-{index}",
                    "title": f"Row {index}",
                    "description": "",
                }
                for index in range(11)
            ],
        ),
    ],
)
def test_payload_count_limits_fail_before_network_io(monkeypatch, send):
    _configure_transport(monkeypatch)
    request = MagicMock()
    monkeypatch.setattr(whatsapp._HTTP_CLIENT, "request", request)

    with pytest.raises(whatsapp.WhatsAppValidationError):
        send()

    request.assert_not_called()


def test_missing_transport_configuration_returns_structured_failure(monkeypatch):
    monkeypatch.setattr(whatsapp, "WHATSAPP_API_URL", "")
    monkeypatch.setattr(whatsapp, "WHATSAPP_TOKEN", "")
    request = MagicMock()
    monkeypatch.setattr(whatsapp._HTTP_CLIENT, "request", request)

    result = whatsapp.send_text("919876543210", "Hello")

    assert result == {"ok": False, "error": "no_whatsapp_config"}
    request.assert_not_called()


def test_logs_and_provider_error_details_do_not_expose_secrets_or_pii(
    monkeypatch,
    caplog,
):
    _configure_transport(monkeypatch)
    private_phone = "919876543210"
    private_body = "Private facts for the lawyer"
    private_token = "do-not-log-this-token"
    request = MagicMock(
        return_value=_response(
            400,
            {
                "error": {
                    "message": (
                        f"token={private_token} recipient={private_phone}"
                    ),
                    "type": "OAuthException",
                    "code": 190,
                }
            },
        )
    )
    monkeypatch.setattr(whatsapp._HTTP_CLIENT, "request", request)

    with caplog.at_level(logging.INFO, logger=whatsapp.logger.name):
        result = whatsapp.send_text(private_phone, private_body)

    assert result["ok"] is False
    assert result["details"]["message"] == (
        "token=[REDACTED] recipient=[REDACTED]"
    )
    rendered_logs = caplog.text
    assert private_phone not in rendered_logs
    assert private_body not in rendered_logs
    assert private_token not in rendered_logs
    assert "transport-test-token" not in rendered_logs


def test_transient_connect_and_http_failures_are_bounded_and_retried(
    monkeypatch,
):
    _configure_transport(monkeypatch)
    monkeypatch.setenv("WHATSAPP_HTTP_MAX_RETRIES", "2")
    monkeypatch.setattr(whatsapp.time, "sleep", MagicMock())
    request = MagicMock(
        side_effect=[
            httpx.ConnectTimeout("connect timeout"),
            _response(503, {"error": {"message": "temporary"}}),
            _response(200, {"messages": [{"id": "accepted"}]}),
        ]
    )
    monkeypatch.setattr(whatsapp._HTTP_CLIENT, "request", request)

    result = whatsapp.send_text("919876543210", "Hello")

    assert result["ok"] is True
    assert result["messages"][0]["id"] == "accepted"
    assert request.call_count == 3
    assert whatsapp.time.sleep.call_count == 2


@pytest.mark.parametrize("exception_type", [httpx.ReadTimeout, httpx.ReadError])
def test_ambiguous_read_failures_are_not_retried(monkeypatch, exception_type):
    _configure_transport(monkeypatch)
    monkeypatch.setenv("WHATSAPP_HTTP_MAX_RETRIES", "2")
    monkeypatch.setattr(whatsapp.time, "sleep", MagicMock())
    request = MagicMock(side_effect=exception_type("ambiguous response"))
    monkeypatch.setattr(whatsapp._HTTP_CLIENT, "request", request)

    result = whatsapp.send_text("919876543210", "Send exactly once")

    assert result == {
        "ok": False,
        "error": "whatsapp_transport_error",
        "reason": exception_type.__name__,
    }
    request.assert_called_once()
    whatsapp.time.sleep.assert_not_called()


def test_payment_success_message_uses_amount_stored_on_booking(monkeypatch):
    booking = SimpleNamespace(
        id=42,
        whatsapp_id="919876543210",
        date=date(2026, 8, 3),
        slot_code="9_10",
        amount=777,
    )
    user = SimpleNamespace(language="en")
    query = MagicMock()
    query.filter.return_value.first.return_value = user
    db = MagicMock()
    db.query.return_value = query
    monkeypatch.setattr(whatsapp, "SessionLocal", MagicMock(return_value=db))

    translate = MagicMock(return_value="Stored amount: INR 777")
    send_text = MagicMock(return_value={"ok": True})
    monkeypatch.setattr(whatsapp, "t", translate)
    monkeypatch.setattr(whatsapp, "send_text", send_text)

    result = whatsapp.send_payment_success_message(booking)

    assert result == {"ok": True}
    translate.assert_called_once()
    assert translate.call_args.args[1] == "payment_success"
    assert translate.call_args.kwargs["amount"] == 777
    send_text.assert_called_once_with(
        booking.whatsapp_id,
        "Stored amount: INR 777",
    )
    db.close.assert_called_once()
