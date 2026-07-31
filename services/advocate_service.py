from sqlalchemy import func

from models import Advocate
import logging

logger = logging.getLogger("advocate")

def find_advocate(db, booking):
    """
    Priority:
    1. Category + District
    2. Category + Any district
    """

    # 1️⃣ Exact match
    advocate = (
        db.query(Advocate)
        .filter(
            Advocate.category == booking.category,
            func.lower(Advocate.district) == (booking.district_name or "").lower(),
            Advocate.active.is_(True),
        )
        .first()
    )

    if advocate:
        return advocate

    # 2️⃣ Fallback: category only
    advocate = (
        db.query(Advocate)
        .filter(
            Advocate.category == booking.category,
            Advocate.active.is_(True),
        )
        .first()
    )

    if not advocate:
        logger.warning(
            "No advocate found | booking_id=%s | category=%s | district=%s",
            booking.id,
            booking.category,
            booking.district_name
        )

    return advocate
