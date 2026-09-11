"""Private object-storage adapter for immutable Draft Studio artifacts."""

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


_SAFE_REF = re.compile(r"^[A-Z0-9-]{6,32}$")
_KINDS = {
    "PREVIEW_PDF": "pdf",
    "FINAL_PDF": "pdf",
    "FINAL_DOCX": "docx",
    "FACTUAL_SUMMARY_PDF": "pdf",
    "NOTICE_REVIEW_PDF": "pdf",
    "NOTICE_DRAFT_PDF": "pdf",
    "ISSUED_PDF": "pdf",
}


@dataclass(frozen=True)
class StoredObject:
    bucket: str
    object_key: str
    etag: str
    size_bytes: int


class S3ArtifactVault:
    """Store private encrypted objects and issue short-lived GET URLs."""

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

    @staticmethod
    def object_key(
        order_ref: str,
        revision_number: int,
        artifact_kind: str,
        content_hash: str,
    ) -> str:
        if not _SAFE_REF.fullmatch(str(order_ref or "")):
            raise ValueError("invalid_document_order_reference")
        if artifact_kind not in _KINDS or revision_number < 1:
            raise ValueError("invalid_document_artifact_identity")
        if not re.fullmatch(r"[0-9a-f]{64}", content_hash):
            raise ValueError("invalid_document_content_hash")
        extension = _KINDS[artifact_kind]
        return (
            f"document-studio/{order_ref}/{revision_number}/"
            f"{artifact_kind.lower()}-{content_hash[:16]}.{extension}"
        )

    def put(
        self,
        *,
        order_ref: str,
        revision_number: int,
        artifact_kind: str,
        content: bytes,
        content_type: str,
        content_hash: str,
        manifest_hash: str,
    ) -> StoredObject:
        if hashlib.sha256(content).hexdigest() != content_hash:
            raise ValueError("document_artifact_hash_mismatch")
        key = self.object_key(
            order_ref, revision_number, artifact_kind, content_hash
        )
        response = self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentLength=len(content),
            ContentType=content_type,
            ServerSideEncryption="AES256",
            Metadata={
                "sha256": content_hash,
                "manifest-sha256": manifest_hash,
            },
        )
        head = self.client.head_object(Bucket=self.bucket, Key=key)
        if int(head.get("ContentLength", -1)) != len(content):
            raise RuntimeError("stored_document_size_mismatch")
        metadata = head.get("Metadata") or {}
        if metadata.get("sha256") != content_hash:
            raise RuntimeError("stored_document_hash_metadata_mismatch")
        return StoredObject(
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


class MemoryArtifactVault:
    """Deterministic test adapter; not selected by production configuration."""

    def __init__(self):
        self.bucket = "memory-test-only"
        self.objects: dict[str, bytes] = {}

    def put(self, **kwargs) -> StoredObject:
        key = S3ArtifactVault.object_key(
            kwargs["order_ref"],
            kwargs["revision_number"],
            kwargs["artifact_kind"],
            kwargs["content_hash"],
        )
        content = kwargs["content"]
        if hashlib.sha256(content).hexdigest() != kwargs["content_hash"]:
            raise ValueError("document_artifact_hash_mismatch")
        self.objects[key] = content
        return StoredObject(self.bucket, key, "memory-etag", len(content))

    def download_url(self, object_key: str) -> str:
        if object_key not in self.objects:
            raise KeyError(object_key)
        return f"memory://{object_key}"

    def delete(self, object_key: str) -> None:
        self.objects.pop(object_key, None)
