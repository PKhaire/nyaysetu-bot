"""HTTP contract tests for the encrypted WhatsApp Flow endpoint."""

from __future__ import annotations

import base64
import json
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _flow_envelope(private_key, body):
    aes_key = os.urandom(32)
    initial_vector = os.urandom(16)
    encrypted_key = private_key.public_key().encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    encrypted_data = AESGCM(aes_key).encrypt(
        initial_vector,
        json.dumps(body, separators=(",", ":")).encode("utf-8"),
        None,
    )
    return (
        {
            "encrypted_aes_key": base64.b64encode(encrypted_key).decode(),
            "encrypted_flow_data": base64.b64encode(encrypted_data).decode(),
            "initial_vector": base64.b64encode(initial_vector).decode(),
        },
        aes_key,
        initial_vector,
    )


def test_encrypted_flow_ping_uses_separate_endpoint_contract(
    monkeypatch,
    app_module,
    client,
    isolated_app_db,
):
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    monkeypatch.setattr(app_module, "ENV", "staging")
    monkeypatch.setattr(
        app_module,
        "CHEQUE_NOTICE_STAGING_UAT_ENABLED",
        True,
    )
    monkeypatch.setattr(
        app_module,
        "WHATSAPP_CHEQUE_NOTICE_FLOW_PRIVATE_KEY",
        private_pem,
    )
    monkeypatch.setattr(
        app_module,
        "WHATSAPP_CHEQUE_NOTICE_FLOW_PRIVATE_KEY_PASSPHRASE",
        "",
    )
    envelope, aes_key, initial_vector = _flow_envelope(
        private_key,
        {"action": "ping"},
    )

    response = client.post(
        "/whatsapp/flows/cheque-notice",
        json=envelope,
    )

    assert response.status_code == 200
    inverted_iv = bytes(value ^ 0xFF for value in initial_vector)
    plaintext = AESGCM(aes_key).decrypt(
        inverted_iv,
        base64.b64decode(response.get_data(as_text=True)),
        None,
    )
    assert json.loads(plaintext) == {"data": {"status": "active"}}


def test_flow_endpoint_is_not_exposed_outside_staging(
    monkeypatch,
    app_module,
    client,
):
    monkeypatch.setattr(app_module, "ENV", "production")
    monkeypatch.setattr(
        app_module,
        "CHEQUE_NOTICE_STAGING_UAT_ENABLED",
        True,
    )

    response = client.post(
        "/whatsapp/flows/cheque-notice",
        json={},
    )

    assert response.status_code == 404


def test_flow_endpoint_applies_the_bounded_global_rate_limit(
    monkeypatch,
    app_module,
    client,
):
    monkeypatch.setattr(app_module, "ENV", "staging")
    monkeypatch.setattr(
        app_module,
        "CHEQUE_NOTICE_STAGING_UAT_ENABLED",
        True,
    )
    monkeypatch.setattr(app_module, "is_global_rate_limited", lambda: True)

    response = client.post(
        "/whatsapp/flows/cheque-notice",
        json={},
    )

    assert response.status_code == 429
