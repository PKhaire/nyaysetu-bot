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
            Advocate.district == booking.district.lower(),
            Advocate.active == True
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
            Advocate.active == True
        )
        .first()
    )

    if not advocate:
        logger.warning(
            "No advocate found | booking_id=%s | category=%s | district=%s",
            booking.id,
            booking.category,
            booking.district
        )

    return advocate
