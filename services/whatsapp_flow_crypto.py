"""Authenticated encryption for Meta WhatsApp Flow endpoint traffic.

Meta encrypts each Flow endpoint request with a one-time AES key protected by
the business public RSA key.  The response uses the same key and the bitwise
inverse of the request IV.  This module deliberately knows nothing about legal
facts or database state.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_MAX_ENCRYPTED_FIELD_BYTES = 256 * 1024
# Meta's Flow endpoint examples use a 16-byte initial vector.  Keep this exact
# instead of accepting arbitrary GCM nonce lengths from untrusted requests.
_AES_GCM_IV_BYTES = 16


class FlowEncryptionError(ValueError):
    """Reject malformed, unauthenticated or undecryptable Flow traffic."""


@dataclass(frozen=True)
class DecryptedFlowRequest:
    """Decrypted request plus the material required for its response."""

    body: dict[str, object]
    aes_key: bytes
    initial_vector: bytes


def _decode_base64(value: object, field: str) -> bytes:
    try:
        encoded = str(value or "").encode("ascii")
        decoded = base64.b64decode(encoded, validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise FlowEncryptionError(f"invalid_{field}") from exc
    if not decoded or len(decoded) > _MAX_ENCRYPTED_FIELD_BYTES:
        raise FlowEncryptionError(f"invalid_{field}")
    return decoded


def _private_key(private_key_pem: str, passphrase: str):
    normalized = str(private_key_pem or "").strip().replace("\\n", "\n")
    if not normalized:
        raise FlowEncryptionError("flow_private_key_required")
    password = str(passphrase or "").encode("utf-8") or None
    try:
        return serialization.load_pem_private_key(
            normalized.encode("utf-8"),
            password=password,
        )
    except (TypeError, ValueError) as exc:
        raise FlowEncryptionError("invalid_flow_private_key") from exc


def flow_private_key_is_valid(private_key_pem: str, passphrase: str = "") -> bool:
    """Validate configured key material without exposing or serializing it."""

    try:
        key = _private_key(private_key_pem, passphrase)
    except FlowEncryptionError:
        return False
    return hasattr(key, "decrypt") and getattr(key, "key_size", 0) >= 2048


def decrypt_flow_request(
    payload: object,
    *,
    private_key_pem: str,
    passphrase: str = "",
) -> DecryptedFlowRequest:
    """Decrypt and authenticate one bounded Meta Flow endpoint request."""

    if not isinstance(payload, dict):
        raise FlowEncryptionError("invalid_flow_envelope")
    encrypted_key = _decode_base64(
        payload.get("encrypted_aes_key"),
        "encrypted_aes_key",
    )
    encrypted_data = _decode_base64(
        payload.get("encrypted_flow_data"),
        "encrypted_flow_data",
    )
    initial_vector = _decode_base64(
        payload.get("initial_vector"),
        "initial_vector",
    )
    if len(initial_vector) != _AES_GCM_IV_BYTES:
        raise FlowEncryptionError("invalid_initial_vector")

    try:
        aes_key = _private_key(private_key_pem, passphrase).decrypt(
            encrypted_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
    except FlowEncryptionError:
        raise
    except ValueError as exc:
        raise FlowEncryptionError("flow_key_decryption_failed") from exc
    if len(aes_key) not in {16, 24, 32}:
        raise FlowEncryptionError("invalid_flow_aes_key")

    try:
        plaintext = AESGCM(aes_key).decrypt(
            initial_vector,
            encrypted_data,
            None,
        )
        body = json.loads(plaintext.decode("utf-8"))
    except (InvalidTag, UnicodeDecodeError, ValueError) as exc:
        raise FlowEncryptionError("flow_data_decryption_failed") from exc
    if not isinstance(body, dict):
        raise FlowEncryptionError("invalid_flow_request_body")
    return DecryptedFlowRequest(body, aes_key, initial_vector)


def encrypt_flow_response(
    response: object,
    *,
    aes_key: bytes,
    initial_vector: bytes,
) -> str:
    """Encrypt one JSON response using Meta's inverted-IV convention."""

    if not isinstance(response, dict):
        raise FlowEncryptionError("invalid_flow_response")
    if len(aes_key) not in {16, 24, 32}:
        raise FlowEncryptionError("invalid_flow_aes_key")
    if len(initial_vector) != _AES_GCM_IV_BYTES:
        raise FlowEncryptionError("invalid_initial_vector")
    flipped_iv = bytes(byte ^ 0xFF for byte in initial_vector)
    plaintext = json.dumps(
        response,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    ciphertext = AESGCM(aes_key).encrypt(flipped_iv, plaintext, None)
    return base64.b64encode(ciphertext).decode("ascii")
