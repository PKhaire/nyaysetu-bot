# services/booking_service.py

from datetime import datetime, timedelta
from typing import List, Dict, Optional

from db import get_db
from models import Booking
from services.whatsapp_service import send_buttons

# Single fixed price – if you want to move to config, you can later.
CONSULTATION_PRICE = 499


# ---------------------------------------------------------------------------
# 1. DATE CALENDAR (for WhatsApp list picker)
# ---------------------------------------------------------------------------
def generate_dates_calendar(num_days: int = 7):
    today = datetime.now().date()
    rows = []
    for i in range(num_days):
        d = today + timedelta(days=i)
        rows.append({
            "id": f"date_{d.isoformat()}",
            "title": d.strftime("%d %b (%a)"),
            "description": "Select this date"
        })
    return rows



def parse_date_selection(selection_id: str) -> str:
    """
    Convert row id like 'date_2025-12-07' → '2025-12-07' (ISO string).
    """
    if selection_id.startswith("date_"):
        return selection_id[len("date_"):]
    return selection_id


# ---------------------------------------------------------------------------
# 2. TIME SLOT CALENDAR (for WhatsApp list picker)
# ---------------------------------------------------------------------------

def generate_slots_calendar(selected_date: str):
    """
    Return time slot rows formatted for WhatsApp list picker.
    Must match WhatsApp format: id, title, description.
    """

    # INDIA lawyer consultation realistic timing
    slot_labels = [
        ("slot_10_11", "10:00 AM – 11:00 AM"),
        ("slot_12_1", "12:00 PM – 1:00 PM"),
        ("slot_3_4", "3:00 PM – 4:00 PM"),
        ("slot_6_7", "6:00 PM – 7:00 PM"),
        ("slot_8_9", "8:00 PM – 9:00 PM"),
    ]

    rows = []
    for slot_id, label in slot_labels:
        rows.append({
            "id": slot_id,
            "title": label,
            "description": f"Available on {selected_date}"
        })

    return rows


def parse_slot_selection(selection_id: str) -> str:
    """
    Map row id (slot_xxx) → human-friendly label.
    """
    mapping = {
        "slot_morning": "10:00 – 11:00 AM",
        "slot_afternoon": "2:00 – 3:00 PM",
        "slot_evening": "6:00 – 7:00 PM",
    }
    return mapping.get(selection_id, selection_id)


# ---------------------------------------------------------------------------
# 3. BOOKING HELPERS (DB)
# ---------------------------------------------------------------------------

create_booking_temp
def confirm_booking_after_payment(booking_id: int) -> Optional[Booking]:
    """
    Mark booking as 'paid' after successful payment.
    """
    from models import Booking  # local import
    db = next(get_db())
    try:
        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            return None
        booking.status = "paid"
        booking.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(booking)
        return booking
    finally:
        db.close()

def mark_booking_completed(booking_id: int) -> Optional[Booking]:
    """
    Mark booking as 'completed' after the consultation call.
    """
    from models import Booking  # local import
    db = next(get_db())
    try:
        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if not booking:
            return None
        booking.status = "completed"
        booking.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(booking)
        return booking
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 4. RATING FLOW
# ---------------------------------------------------------------------------

def ask_rating_buttons(wa_id: str) -> None:
    """
    Send rating options after the call is done.
    """
    send_buttons(
        wa_id,
        "How was your consultation? Please rate your experience:",
        [
            {"id": "rating_5", "title": "⭐⭐⭐⭐⭐ Excellent"},
            {"id": "rating_4", "title": "⭐⭐⭐⭐ Good"},
            {"id": "rating_3", "title": "⭐⭐⭐ Okay"},
        ]
    )
