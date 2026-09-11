"""Private object-storage adapters for customer evidence."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

import boto3
from botocore.config import Config

from config import (
    DOCUMENT_STUDIO_DOWNLOAD_TTL_SECONDS,
    DOCUMENT_STUDIO_S3_ACCESS_KEY_ID,
    DOCUMENT_STUDIO_S3_BUCKET,
    DOCUMENT_STUDIO_S3_ENDPOINT_URL,
    DOCUMENT_STUDIO_S3_REGION,
    DOCUMENT_STUDIO_S3_SECRET_ACCESS_KEY,
)


_SAFE_ORDER_REF = re.compile(r"^[A-Z0-9-]{6,32}$")
_SAFE_EVIDENCE_REF = re.compile(r"^EVD-[A-F0-9]{12}$")
_EXTENSIONS = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png",
}


@dataclass(frozen=True)
class StoredEvidenceObject:
    bucket: str
    object_key: str
    etag: str
    size_bytes: int


def evidence_object_key(
    order_ref: str,
    evidence_ref: str,
    content_type: str,
    content_hash: str,
) -> str:
    if not _SAFE_ORDER_REF.fullmatch(str(order_ref or "")):
        raise ValueError("invalid_document_order_reference")
    if not _SAFE_EVIDENCE_REF.fullmatch(str(evidence_ref or "")):
        raise ValueError("invalid_document_evidence_reference")
    if content_type not in _EXTENSIONS:
        raise ValueError("invalid_document_evidence_type")
    if not re.fullmatch(r"[0-9a-f]{64}", content_hash):
        raise ValueError("invalid_document_evidence_hash")
    return (
        f"document-evidence/{order_ref}/{evidence_ref}/"
        f"content-{content_hash[:16]}.{_EXTENSIONS[content_type]}"
    )


class S3EvidenceVault:
    """Store evidence privately and issue short-lived GET URLs."""

    def __init__(self, client=None, *, bucket: str | None = None):
        self.bucket = str(bucket or DOCUMENT_STUDIO_S3_BUCKET).strip()
        if not self.bucket:
            raise ValueError("document_studio_s3_bucket_required")
        if client is None:
            s3_options = (
                {"addressing_style": "virtual"}
                if not DOCUMENT_STUDIO_S3_ENDPOINT_URL
                else None
            )
            kwargs = {
                "region_name": DOCUMENT_STUDIO_S3_REGION,
                "config": Config(
                    signature_version="s3v4",
                    s3=s3_options,
                    retries={"max_attempts": 3, "mode": "standard"},
                    connect_timeout=5,
                    read_timeout=15,
                ),
            }
            if DOCUMENT_STUDIO_S3_ENDPOINT_URL:
                kwargs["endpoint_url"] = DOCUMENT_STUDIO_S3_ENDPOINT_URL
            if DOCUMENT_STUDIO_S3_ACCESS_KEY_ID:
                kwargs["aws_access_key_id"] = DOCUMENT_STUDIO_S3_ACCESS_KEY_ID
                kwargs["aws_secret_access_key"] = (
                    DOCUMENT_STUDIO_S3_SECRET_ACCESS_KEY
                )
            client = boto3.client("s3", **kwargs)
        self.client = client

    def put(self, **kwargs) -> StoredEvidenceObject:
        content = kwargs["content"]
        content_hash = kwargs["content_hash"]
        if hashlib.sha256(content).hexdigest() != content_hash:
            raise ValueError("document_evidence_hash_mismatch")
        key = evidence_object_key(
            kwargs["order_ref"],
            kwargs["evidence_ref"],
            kwargs["content_type"],
            content_hash,
        )
        response = self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentLength=len(content),
            ContentType=kwargs["content_type"],
            ServerSideEncryption="AES256",
            Metadata={"sha256": content_hash},
        )
        head = self.client.head_object(Bucket=self.bucket, Key=key)
        if int(head.get("ContentLength", -1)) != len(content):
            raise RuntimeError("stored_evidence_size_mismatch")
        if (head.get("Metadata") or {}).get("sha256") != content_hash:
            raise RuntimeError("stored_evidence_hash_metadata_mismatch")
        return StoredEvidenceObject(
            self.bucket,
            key,
            str(response.get("ETag") or "").strip('"'),
            len(content),
        )

    def download_url(self, object_key: str) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": object_key},
            ExpiresIn=DOCUMENT_STUDIO_DOWNLOAD_TTL_SECONDS,
        )

    def delete(self, object_key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=object_key)


class MemoryEvidenceVault:
    """Deterministic test adapter; never selected by runtime configuration."""

    def __init__(self):
        self.bucket = "memory-evidence-test-only"
        self.objects: dict[str, bytes] = {}
        self._keys_by_ref: dict[str, str] = {}

    def put(self, **kwargs) -> StoredEvidenceObject:
        content = kwargs["content"]
        content_hash = kwargs["content_hash"]
        if hashlib.sha256(content).hexdigest() != content_hash:
            raise ValueError("document_evidence_hash_mismatch")
        key = evidence_object_key(
            kwargs["order_ref"],
            kwargs["evidence_ref"],
            kwargs["content_type"],
            content_hash,
        )
        self.objects[key] = content
        self._keys_by_ref[kwargs["evidence_ref"]] = key
        return StoredEvidenceObject(self.bucket, key, "memory-etag", len(content))

    def object_key_for(self, evidence_ref: str) -> str:
        return self._keys_by_ref[evidence_ref]

    def download_url(self, object_key: str) -> str:
        if object_key not in self.objects:
            raise KeyError(object_key)
        return f"memory://{object_key}"

    def delete(self, object_key: str) -> None:
        self.objects.pop(object_key, None)
