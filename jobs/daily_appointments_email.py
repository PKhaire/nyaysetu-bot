from datetime import date
from db import SessionLocal
from models import Booking
from services.email_service import send_email


def run_daily_appointments_email():
    db = SessionLocal()
    try:
        today = date.today()

        bookings = (
            db.query(Booking)
            .filter(
                Booking.status == "PAID",
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
                    f"{b.slot_code} | {b.name} | {b.category} | {b.district}"
                )

            body = "Appointments for today:\n\n" + "\n".join(lines)

        send_email(
            subject=f"📅 NyaySetu – Appointments for {today}",
            body=body
        )

    finally:
        db.close()


if __name__ == "__main__":
    run_daily_appointments_email()
