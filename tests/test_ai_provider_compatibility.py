from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from config import AI_RESPONSE_CACHE_TTL_SECONDS
from services import ai_safety, claude_service, openai_service


class FakeOpenAIResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def reset_openai_state(monkeypatch):
    monkeypatch.setattr(openai_service, "AI_DISABLED_UNTIL", None)
    openai_service.AI_RESPONSE_CACHE.clear()
    yield
    openai_service.AI_RESPONSE_CACHE.clear()


def test_openai_cache_uses_configured_ttl_and_zero_disables_it(monkeypatch):
    assert openai_service.AI_CACHE_TTL == AI_RESPONSE_CACHE_TTL_SECONDS

    clock = {"now": 100.0}
    monkeypatch.setattr(openai_service.time, "time", lambda: clock["now"])
    monkeypatch.setattr(openai_service, "AI_CACHE_TTL", 5)

    openai_service._set_cached_reply("user-ref", "same prompt", "cached reply")
    clock["now"] = 104.9
    assert (
        openai_service._get_cached_reply("user-ref", "same prompt")
        == "cached reply"
    )

    clock["now"] = 105.1
    assert openai_service._get_cached_reply("user-ref", "same prompt") is None

    monkeypatch.setattr(openai_service, "AI_CACHE_TTL", 0)
    openai_service._set_cached_reply("user-ref", "new prompt", "not cached")
    assert openai_service.AI_RESPONSE_CACHE == {}


def test_openai_cache_is_bounded_and_evicts_the_oldest_entry(monkeypatch):
    clock = {"now": 100.0}
    monkeypatch.setattr(openai_service.time, "time", lambda: clock["now"])
    monkeypatch.setattr(openai_service, "AI_CACHE_TTL", 3_600)
    monkeypatch.setattr(openai_service, "AI_CACHE_MAX_ENTRIES", 2)

    openai_service._set_cached_reply("user-a", "prompt-a", "reply-a")
    clock["now"] = 101.0
    openai_service._set_cached_reply("user-b", "prompt-b", "reply-b")
    clock["now"] = 102.0
    openai_service._set_cached_reply("user-c", "prompt-c", "reply-c")

    assert len(openai_service.AI_RESPONSE_CACHE) == 2
    assert openai_service._get_cached_reply("user-a", "prompt-a") is None
    assert (
        openai_service._get_cached_reply("user-b", "prompt-b")
        == "reply-b"
    )
    assert (
        openai_service._get_cached_reply("user-c", "prompt-c")
        == "reply-c"
    )


def test_openai_uses_one_fallback_model_for_explicit_model_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-primary-test")
    monkeypatch.setenv("OPENAI_FALLBACK_MODEL", "gpt-fallback-test")
    monkeypatch.setenv(
        "AI_SAFETY_IDENTIFIER_SECRET",
        "stable-openai-provider-test-secret",
    )

    responses = [
        FakeOpenAIResponse(
            404,
            {
                "error": {
                    "code": "model_not_found",
                    "message": "The requested model does not exist.",
                    "param": "model",
                }
            },
        ),
        FakeOpenAIResponse(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "Use the lawful process and do not send details "
                                "to reply.private@example.com."
                            )
                        }
                    }
                ]
            },
        ),
    ]
    calls = []

    def fake_post(url, headers, data):
        calls.append({"url": url, "headers": headers, "data": data})
        return responses.pop(0)

    monkeypatch.setattr(openai_service, "_post_openai", fake_post)
    user = SimpleNamespace(language="en", whatsapp_id="919876543210")
    prompt = (
        "My email is prompt.private@example.com. What records are useful "
        "for a consumer complaint?"
    )

    answer = openai_service.openai_reply_external(
        prompt,
        user,
        context="post_payment",
    )

    assert [call["data"]["model"] for call in calls] == [
        "gpt-primary-test",
        "gpt-fallback-test",
    ]
    for call in calls:
        provider_prompt = call["data"]["messages"][1]["content"]
        assert "prompt.private@example.com" not in provider_prompt
        assert "[EMAIL REDACTED]" in provider_prompt
        assert call["data"]["safety_identifier"] == ai_safety.safety_identifier(
            user
        )
    assert "reply.private@example.com" not in answer
    assert "[EMAIL REDACTED]" in answer


@pytest.mark.parametrize(
    ("status_code", "payload", "expected_reason"),
    [
        (
            401,
            {
                "error": {
                    "code": "invalid_api_key",
                    "message": "Incorrect API key.",
                }
            },
            "http_401",
        ),
        (
            400,
            {
                "error": {
                    "code": "invalid_value",
                    "message": "A message field is invalid.",
                    "param": "messages",
                }
            },
            "http_400",
        ),
        (
            429,
            {
                "error": {
                    "code": "insufficient_quota",
                    "message": "Quota exceeded.",
                }
            },
            "rate_limited",
        ),
    ],
)
def test_openai_does_not_model_fallback_for_non_model_errors(
    monkeypatch,
    status_code,
    payload,
    expected_reason,
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-primary-test")
    monkeypatch.setenv("OPENAI_FALLBACK_MODEL", "gpt-fallback-test")
    calls = []

    def fake_post(url, headers, data):
        calls.append(data)
        return FakeOpenAIResponse(status_code, payload)

    monkeypatch.setattr(openai_service, "_post_openai", fake_post)
    user = SimpleNamespace(language="en", whatsapp_id="919876543210")

    with pytest.raises(openai_service.OpenAIProviderError) as exc_info:
        openai_service.openai_reply_external(
            "What documents are useful for a consumer complaint?",
            user,
            context="post_payment",
        )

    assert str(exc_info.value) == expected_reason
    assert [call["model"] for call in calls] == ["gpt-primary-test"]


def test_openai_model_fallback_is_bounded_to_one_attempt(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-primary-test")
    monkeypatch.setenv("OPENAI_FALLBACK_MODEL", "gpt-fallback-test")
    calls = []
    model_error = FakeOpenAIResponse(
        404,
        {
            "error": {
                "code": "model_not_found",
                "message": "The requested model does not exist.",
                "param": "model",
            }
        },
    )

    def fake_post(url, headers, data):
        calls.append(data)
        return model_error

    monkeypatch.setattr(openai_service, "_post_openai", fake_post)
    user = SimpleNamespace(language="en", whatsapp_id="919876543210")

    with pytest.raises(openai_service.OpenAIProviderError, match="http_404"):
        openai_service.openai_reply_external(
            "What records are useful for a property dispute?",
            user,
            context="post_payment",
        )

    assert [call["model"] for call in calls] == [
        "gpt-primary-test",
        "gpt-fallback-test",
    ]


@pytest.mark.parametrize(
    ("model", "supports_temperature"),
    [
        ("claude-opus-4-6", True),
        ("claude-opus-4-20250514", True),
        ("claude-sonnet-5", True),
        ("claude-opus-4-7", False),
        ("claude-opus-4-8-20260528", False),
        ("claude-opus-4-10", False),
        ("claude-opus-5", False),
        ("claude-opus-6-20280101", False),
    ],
)
def test_claude_temperature_capability_by_model(
    model,
    supports_temperature,
):
    assert (
        claude_service._model_supports_temperature(model)
        is supports_temperature
    )


def test_claude_omits_temperature_for_new_opus_and_preserves_privacy(
    monkeypatch,
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-4-8")
    monkeypatch.setenv(
        "AI_SAFETY_IDENTIFIER_SECRET",
        "stable-claude-provider-test-secret",
    )
    captured = {}

    class FakeMessages:
        @staticmethod
        def create(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        text=(
                            "Use the lawful process. Do not send details to "
                            "reply.private@example.com."
                        )
                    )
                ]
            )

    class FakeAnthropic:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.messages = FakeMessages()

    anthropic_module = ModuleType("anthropic")
    anthropic_module.Anthropic = FakeAnthropic
    monkeypatch.setitem(sys.modules, "anthropic", anthropic_module)

    user = SimpleNamespace(language="mr", whatsapp_id="919876543210")
    answer = claude_service.claude_reply_external(
        (
            "My email is prompt.private@example.com. What documents are "
            "generally useful?"
        ),
        user,
    )

    assert captured["model"] == "claude-opus-4-8"
    assert "temperature" not in captured
    provider_message = captured["messages"][0]["content"]
    assert "prompt.private@example.com" not in provider_message
    assert "[EMAIL REDACTED]" in provider_message
    assert captured["metadata"]["user_id"] == ai_safety.safety_identifier(user)
    assert "reply.private@example.com" not in answer
    assert "[EMAIL REDACTED]" in answer


def test_claude_retains_temperature_for_compatible_model():
    request = claude_service._message_request(
        "claude-opus-4-6",
        "A scrubbed legal question",
        SimpleNamespace(language="en"),
        "ns_test_identifier",
    )

    assert request["temperature"] == 0.2
