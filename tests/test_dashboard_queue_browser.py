"""Optional local browser test; the database and provider credentials are synthetic."""

from __future__ import annotations

import os
import threading
from datetime import date

import pytest
from werkzeug.serving import make_server

from models import Booking, BookingFulfillment, BookingStatus
from test_admin_operations import admin_db  # noqa: F401 - shared fixture


@pytest.mark.skipif(
    not os.environ.get("NYAYSETU_TEST_BROWSER_PATH"),
    reason="Set NYAYSETU_TEST_BROWSER_PATH and install Playwright for browser tests",
)
def test_dashboard_reaches_last_appointment_in_full_queue(app_module, request):
    playwright = pytest.importorskip("playwright.sync_api")
    db = request.getfixturevalue("admin_db")()
    try:
        for index in range(201):
            booking = Booking(
                whatsapp_id=f"919000{index:06d}",
                name=f"Synthetic Queue User {index}",
                phone=f"919000{index:06d}",
                state_name="Maharashtra",
                district_name="Pune",
                category="Family",
                subcategory="Other Family Issue",
                date=date(2099, 8, 3),
                slot_code="10_11",
                slot_readable="10:00 AM - 11:00 AM",
                amount=499,
                status=BookingStatus.PAID,
                payment_token=f"synthetic-browser-{index}",
            )
            db.add(booking)
            db.flush()
            db.add(BookingFulfillment(booking_id=booking.id, status="UNASSIGNED"))
        db.commit()
    finally:
        db.close()

    server = make_server("127.0.0.1", 0, app_module.app)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        with playwright.sync_playwright() as browser_tools:
            browser = browser_tools.chromium.launch(
                executable_path=os.environ["NYAYSETU_TEST_BROWSER_PATH"],
                headless=True,
                args=["--disable-background-networking", "--disable-extensions"],
            )
            try:
                page = browser.new_page()
                base = f"http://127.0.0.1:{server.server_port}"
                page.route(
                    "**/*",
                    lambda route: route.continue_()
                    if route.request.url.startswith(base + "/")
                    else route.abort(),
                )
                page.goto(base + "/admin/login")
                page.locator("#operator_id").fill("browser.test@example.com")
                page.locator("#password").fill("strong-admin-test-password")
                page.get_by_role("button", name="Sign in securely").click()
                playwright.expect(page.locator("#count-unassigned")).to_have_text("201")
                playwright.expect(page.locator("#queue-page")).to_have_text("1–50 of 201")
                for expected in ("51–100 of 201", "101–150 of 201", "151–200 of 201", "201–201 of 201"):
                    page.get_by_role("button", name="Next", exact=True).click()
                    playwright.expect(page.locator("#queue-page")).to_have_text(expected)
                playwright.expect(page.locator("#queue-next")).to_be_disabled()
                playwright.expect(page.locator("#queue-page")).to_have_text("201–201 of 201")
                playwright.expect(page.locator("#appointment-rows")).to_contain_text(
                    "Synthetic Queue User 200"
                )
                page.get_by_role("button", name="Previous", exact=True).click()
                playwright.expect(page.locator("#queue-page")).to_have_text("151–200 of 201")
                page.locator("#queue-search").fill("Synthetic Queue User 200")
                playwright.expect(page.locator("#queue-page")).to_have_text("1–1 of 1")
                playwright.expect(page.locator("#appointment-rows")).to_contain_text(
                    "Synthetic Queue User 200"
                )
                playwright.expect(page.locator("#count-unassigned")).to_have_text("201")
                page.locator("#status-filter").select_option("ASSIGNED")
                playwright.expect(page.locator("#queue-page")).to_have_text("0 results")
                playwright.expect(page.locator("#empty-state")).to_be_visible()
                page.route("**/admin/fulfillments?**", lambda route: route.abort())
                page.get_by_role("button", name="Refresh", exact=True).click()
                playwright.expect(page.locator("#queue-error")).to_be_visible()
                playwright.expect(page.locator("#queue-page")).to_have_text("Queue unavailable")
                playwright.expect(page.locator("#count-unassigned")).to_have_text("—")
            finally:
                browser.close()
    finally:
        server.shutdown()
        server_thread.join(timeout=5)
        server.server_close()
