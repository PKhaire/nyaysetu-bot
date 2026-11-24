import pytest


def test_html_challenge_is_rejected_without_reflection(client):
    challenge = "<script>alert(1)</script>"

    response = client.get(
        "/webhook",
        query_string={
            "hub.verify_token": "test-verify-token",
            "hub.challenge": challenge,
        },
    )

    assert response.status_code == 400
    assert challenge not in response.get_data(as_text=True)
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_invalid_verification_token_is_rejected(client):
    response = client.get(
        "/webhook",
        query_string={"hub.verify_token": "incorrect", "hub.challenge": "12345"},
    )

    assert response.status_code == 403
    assert response.get_data(as_text=True) == "Invalid token"


def test_numeric_verification_challenge_is_returned_unchanged(client):
    response = client.get(
        "/webhook",
        query_string={"hub.verify_token": "test-verify-token", "hub.challenge": "12345"},
    )

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "12345"
    assert response.mimetype == "text/plain"


@pytest.mark.parametrize("challenge", ["0", "000123", "1158201444", "safe-identifier_123"])
def test_safe_challenges_are_returned_exactly(client, challenge):
    response = client.get("/webhook", query_string={
        "hub.verify_token": "test-verify-token", "hub.challenge": challenge,
    })
    assert response.status_code == 200
    assert response.get_data(as_text=True) == challenge
    assert response.mimetype == "text/plain"


@pytest.mark.parametrize("challenge", ["a&b", "a<b", "a>b", "a'b", 'a"b'])
def test_html_special_challenges_are_rejected_without_reflection(client, challenge):
    response = client.get("/webhook", query_string={
        "hub.verify_token": "test-verify-token", "hub.challenge": challenge,
    })
    assert response.status_code == 400
    assert challenge not in response.get_data(as_text=True)


def test_missing_challenge_is_rejected(client):
    response = client.get("/webhook", query_string={"hub.verify_token": "test-verify-token"})
    assert response.status_code == 400
