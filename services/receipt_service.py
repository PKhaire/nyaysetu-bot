"""Generate short-lived payment receipt PDFs.

Receipt documents contain personal and payment information. They therefore use
an unpredictable, owner-only temporary file rather than a durable project
directory. The caller owns the returned path and must remove it after delivery.
"""

from __future__ import annotations

import os
import tempfile
import time
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from db import SessionLocal
from models import Booking
from utils.date_utils import format_date_readable


_TEMP_PREFIX = "nyaysetu-receipt-"
_STALE_RECEIPT_SECONDS = 60 * 60
# Kept for compatibility with code that previously imported this constant.
# Files now use randomized names directly under the system temporary directory.
RECEIPT_DIR = tempfile.gettempdir()


def _single_line(value: Any, maximum: int = 100) -> str:
    """Keep user-provided values from creating malformed receipt lines."""

    normalized = " ".join(str(value or "").split())
    return normalized[:maximum]


def _create_private_temp_path() -> str:
    _cleanup_stale_receipts()
    descriptor, file_path = tempfile.mkstemp(
        prefix=_TEMP_PREFIX,
        suffix=".pdf",
    )
    os.close(descriptor)
    try:
        os.chmod(file_path, 0o600)
    except OSError:
        # mkstemp already creates an owner-only file on POSIX. chmod is a
        # best-effort reinforcement on platforms that expose POSIX modes.
        pass
    return file_path


def _cleanup_stale_receipts() -> None:
    """Best-effort cleanup for files orphaned by a terminated worker."""

    temp_directory = tempfile.gettempdir()
    cutoff = time.time() - _STALE_RECEIPT_SECONDS
    try:
        candidates = os.scandir(temp_directory)
    except OSError:
        return

    with candidates:
        for candidate in candidates:
            if not (
                candidate.name.startswith(_TEMP_PREFIX)
                and candidate.name.endswith(".pdf")
            ):
                continue
            try:
                if candidate.is_file(follow_symlinks=False):
                    stat = candidate.stat(follow_symlinks=False)
                    if stat.st_mtime < cutoff:
                        os.remove(candidate.path)
            except (FileNotFoundError, OSError):
                continue


def _remove_temp_receipt(file_path: str | None) -> None:
    if not file_path:
        return
    try:
        os.remove(file_path)
    except FileNotFoundError:
        pass
    except OSError:
        # Cleanup failure must not mask the original generation/database error.
        pass


def generate_pdf_receipt(booking):
    """Generate a fresh private receipt and return its temporary path.

    The public return contract is unchanged. A fresh random path is used for
    every attempt so concurrent retries cannot read or overwrite one another.
    """

    file_path = _create_private_temp_path()
    db = None
    try:
        receipt = canvas.Canvas(file_path, pagesize=A4)
        receipt.setTitle("NyaySetu Payment Receipt")
        receipt.setAuthor("NyaySetu")

        receipt.setFont("Helvetica-Bold", 16)
        receipt.drawString(50, 800, "NyaySetu - Payment Receipt")

        receipt.setFont("Helvetica", 11)
        y = 760
        lines = [
            f"Booking ID: {_single_line(booking.id, 40)}",
            f"Name: {_single_line(booking.name)}",
            f"Category: {_single_line(booking.category)}",
            f"Date: {_single_line(format_date_readable(booking.date), 50)}",
            f"Time: {_single_line(booking.slot_readable, 50)}",
            f"Amount Paid: INR {_single_line(booking.amount, 30)}",
            (
                "Payment ID: "
                f"{_single_line(booking.razorpay_payment_id or 'N/A', 80)}"
            ),
            "Status: PAID",
        ]
        for line in lines:
            receipt.drawString(50, y, line)
            y -= 20

        receipt.showPage()
        receipt.save()

        # Update only the receipt flag. Merging a detached Booking can overwrite
        # newer payment/status fields from another transaction.
        db = SessionLocal()
        updated = (
            db.query(Booking)
            .filter(Booking.id == booking.id)
            .update(
                {Booking.receipt_generated: True},
                synchronize_session=False,
            )
        )
        if updated != 1:
            raise LookupError("booking_not_found")
        db.commit()
        return file_path
    except Exception:
        if db is not None:
            db.rollback()
        _remove_temp_receipt(file_path)
        raise
    finally:
        if db is not None:
            db.close()
