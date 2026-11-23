def test_valid_verification_challenge_is_returned_as_plain_text(client):
    challenge = "<script>alert(1)</script>"

    response = client.get(
        "/webhook",
        query_string={
            "hub.verify_token": "test-verify-token",
            "hub.challenge": challenge,
        },
    )

    assert response.status_code == 200
    assert response.get_data(as_text=True) == challenge
    assert response.mimetype == "text/plain"
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
