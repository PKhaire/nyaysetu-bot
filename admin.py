# admin.py
from flask import Flask, request, render_template_string
from db import SessionLocal
from models import User, Booking
from config import ADMIN_PASSWORD

app = Flask(__name__)

DASH_HTML = """
<html>
  <head><title>NyaySetu Admin</title></head>
  <body>
    <h1>NyaySetu Admin</h1>
    <p>Simple dashboard (demo). Protect with ADMIN_PASSWORD in env.</p>
    <h2>Recent Leads</h2>
    <table border="1" cellpadding="6">
      <tr><th>WhatsApp</th><th>Case ID</th><th>Name</th><th>Language</th><th>Created</th></tr>
      {% for u in users %}
      <tr>
        <td>{{u.whatsapp_id}}</td>
        <td>{{u.case_id}}</td>
        <td>{{u.name or ""}}</td>
        <td>{{u.language}}</td>
        <td>{{u.created_at}}</td>
      </tr>
      {% endfor %}
    </table>

    <h2>Bookings</h2>
    <table border="1" cellpadding="6">
      <tr><th>WhatsApp</th><th>Time</th><th>Confirmed</th><th>Created</th></tr>
      {% for b in bookings %}
      <tr>
        <td>{{b.user_whatsapp_id}}</td>
        <td>{{b.preferred_time}}</td>
        <td>{{b.confirmed}}</td>
        <td>{{b.created_at}}</td>
      </tr>
      {% endfor %}
    </table>
  </body>
</html>
"""

@app.route("/admin")
def admin_dashboard():
    pwd = request.args.get("pwd", "")
    if pwd != ADMIN_PASSWORD:
        return "Forbidden", 403
    db = SessionLocal()
    users = db.query(User).order_by(User.created_at.desc()).limit(100).all()
    bookings = db.query(Booking).order_by(Booking.created_at.desc()).limit(100).all()
    return render_template_string(DASH_HTML, users=users, bookings=bookings)
