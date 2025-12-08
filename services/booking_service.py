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

def generate_dates_calendar(num_days: int = 7) -> List[Dict]:
    """
    Build WhatsApp 'list' sections for the next `num_days` dates.

    Returns a list of sections compatible with send_list_picker():
    [
      {
        "title": "Available dates",
        "rows": [
          {"id": "date_2025-12-07", "title": "07 Dec (Sun)", "description": "..."},
          ...
        ]
      }
    ]
    """
    today = datetime.now().date()
    rows = []

    for i in range(num_days):
        d = today + timedelta(days=i)
        row_id = f"date_{d.isoformat()}"          # e.g. "date_2025-12-07"
        title = d.strftime("%d %b (%a)")          # e.g. "07 Dec (Sun)"
        rows.append({
            "id": row_id,
            "title": title,
            "description": "Tap to select this date"
        })

    sections = [
        {
            "title": "Available dates",
            "rows": rows
        }
    ]
    return sections


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

def generate_slots_calendar() -> List[Dict]:
    """
    Build WhatsApp 'list' sections for time slots.

    Returns:
    [
      {
        "title": "Available time slots",
        "rows": [
          {"id": "slot_morning", "title": "10:00 – 11:00 AM", "description": "..."},
          ...
        ]
      }
    ]
    """
    # You can tweak these labels as you like.
    slots = [
        ("slot_morning", "10:00 – 11:00 AM"),
        ("slot_afternoon", "2:00 – 3:00 PM"),
        ("slot_evening", "6:00 – 7:00 PM"),
    ]

    rows = [
        {
            "id": slot_id,
            "title": label,
            "description": "Tap to select this time"
        }
        for slot_id, label in slots
    ]

    sections = [
        {
            "title": "Available time slots",
            "rows": rows
        }
    ]
    return sections


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

def create_booking_temp(user, chosen_date_iso: str, slot_code: str) -> Booking:
    """
    Create a temporary booking in DB with status='pending_payment'.

    - user: SQLAlchemy User object (already loaded in app.py)
    - chosen_date_iso: 'YYYY-MM-DD' string
    - slot_code: e.g. 'slot_morning'
    """
    from models import Booking  # local import to avoid circular issues

    slot_label = parse_slot_selection(slot_code)

    db = next(get_db())
    try:
        booking = Booking(
            whatsapp_id=getattr(user, "whatsapp_id", None),
            case_id=getattr(user, "case_id", None),
            date=chosen_date_iso,
            slot=slot_label,
            amount=CONSULTATION_PRICE,
            status="pending_payment",
            created_at=datetime.utcnow()
        )
        db.add(booking)
        db.commit()
        db.refresh(booking)
        return booking
    finally:
        db.close()


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
