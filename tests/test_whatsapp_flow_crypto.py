"""Contract tests for encrypted WhatsApp Flow endpoint traffic."""

from __future__ import annotations

import base64
import json
import os

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from services.whatsapp_flow_crypto import (
    FlowEncryptionError,
    decrypt_flow_request,
    encrypt_flow_response,
    flow_private_key_is_valid,
)


@pytest.fixture(scope="module")
def flow_keys():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    return private_key, private_pem


def _encrypted_envelope(private_key, body):
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


def test_flow_request_and_response_follow_meta_encryption_contract(flow_keys):
    private_key, private_pem = flow_keys
    request_body = {
        "action": "INIT",
        "flow_token": "synthetic-signed-token",
    }
    envelope, aes_key, initial_vector = _encrypted_envelope(
        private_key,
        request_body,
    )

    decrypted = decrypt_flow_request(
        envelope,
        private_key_pem=private_pem,
    )
    encrypted_response = encrypt_flow_response(
        {"screen": "SUITABILITY", "data": {"has_error": False}},
        aes_key=decrypted.aes_key,
        initial_vector=decrypted.initial_vector,
    )

    assert decrypted.body == request_body
    inverted_iv = bytes(value ^ 0xFF for value in initial_vector)
    response_bytes = AESGCM(aes_key).decrypt(
        inverted_iv,
        base64.b64decode(encrypted_response),
        None,
    )
    assert json.loads(response_bytes) == {
        "screen": "SUITABILITY",
        "data": {"has_error": False},
    }
    assert flow_private_key_is_valid(private_pem) is True


def test_tampered_flow_request_is_rejected(flow_keys):
    private_key, private_pem = flow_keys
    envelope, _, _ = _encrypted_envelope(
        private_key,
        {"action": "ping"},
    )
    ciphertext = bytearray(base64.b64decode(envelope["encrypted_flow_data"]))
    ciphertext[-1] ^= 1
    envelope["encrypted_flow_data"] = base64.b64encode(ciphertext).decode()

    with pytest.raises(
        FlowEncryptionError,
        match="flow_data_decryption_failed",
    ):
        decrypt_flow_request(envelope, private_key_pem=private_pem)


def test_flow_crypto_rejects_wrong_key_and_wrong_iv_size(flow_keys):
    private_key, private_pem = flow_keys
    envelope, _, _ = _encrypted_envelope(
        private_key,
        {"action": "ping"},
    )
    another_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    another_pem = another_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")

    with pytest.raises(FlowEncryptionError, match="flow_key_decryption_failed"):
        decrypt_flow_request(envelope, private_key_pem=another_pem)

    envelope["initial_vector"] = base64.b64encode(os.urandom(12)).decode()
    with pytest.raises(FlowEncryptionError, match="invalid_initial_vector"):
        decrypt_flow_request(envelope, private_key_pem=private_pem)
