from datetime import datetime
from zoneinfo import ZoneInfo

from config import APP_TIMEZONE
from db import SessionLocal
from models import Booking, BookingStatus
from services.email_service import send_email


def run_daily_appointments_email():
    db = SessionLocal()
    try:
        today = datetime.now(ZoneInfo(APP_TIMEZONE)).date()

        bookings = (
            db.query(Booking)
            .filter(
                Booking.status == BookingStatus.PAID,
                Booking.date == today
            )
            .order_by(Booking.slot_code)
            .all()
        )

        if not bookings:
            body = "No appointments scheduled for today."
        else:
            lines = []
            for b in bookings:
                lines.append(
                    f"{b.slot_readable} | Booking #{b.id}"
                )

            body = (
                "Appointments for today:\n\n"
                + "\n".join(lines)
                + "\n\nOpen the authenticated NyaySetu operations "
                "interface for contact and case details."
            )

        if (
            send_email(
                subject=f"NyaySetu appointments for {today}",
                body=body,
            )
            is not True
        ):
            raise RuntimeError("daily_appointments_email_not_sent")

    finally:
        db.close()


if __name__ == "__main__":
    run_daily_appointments_email()
