"""Optional isolated browser exercise; never connects to external services."""

import os
import threading
from datetime import datetime, timezone

import pytest
from werkzeug.serving import make_server

from models import Advocate
from services.admin_identity_service import (
    begin_operator_enrollment,
    confirm_operator_enrollment,
    totp_code,
)
from test_admin_operations import ADMIN_MFA_KEY, _seed_operations, admin_db  # noqa: F401


@pytest.mark.skipif(not os.environ.get("NYAYSETU_TEST_BROWSER_PATH"), reason="Optional local browser")
def test_advocate_management_browser(app_module, request):
    playwright = pytest.importorskip("playwright.sync_api")
    playwright.expect.set_options(timeout=20000)
    session_factory = request.getfixturevalue("admin_db")
    _seed_operations(session_factory)
    db = session_factory()
    now = datetime.now(timezone.utc)
    try:
        db.add(Advocate(name="Synthetic Browser Advocate", email="synthetic@example.com", phone="919900001235", bar_registration_number="SYNTHETIC/456", category="family", district="Pune", active=True))
        db.add(Advocate(name="Synthetic Incomplete Advocate", email="incomplete@example.com", category="family", district="Pune", active=True))
        account = begin_operator_enrollment(db, operator_id="synthetic.admin@example.com", display_name="Synthetic Admin", role="ADMIN", password="synthetic browser password", encryption_key=ADMIN_MFA_KEY, now=now)
        confirm_operator_enrollment(db, operator_id=account.operator_id, verification_code=totp_code(account.secret, timestamp=now), encryption_key=ADMIN_MFA_KEY, now=now)
        db.commit()
    finally:
        db.close()
    server = make_server("127.0.0.1", 0, app_module.app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with playwright.sync_playwright() as tools:
            browser = tools.chromium.launch(executable_path=os.environ["NYAYSETU_TEST_BROWSER_PATH"], headless=True, args=["--disable-background-networking", "--disable-extensions"])
            try:
                page = browser.new_page()
                base = f"http://127.0.0.1:{server.server_port}"
                page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(base + "/") else route.abort())
                page.goto(base + "/admin/login")
                page.locator("#operator_id").fill(account.operator_id)
                page.locator("#password").fill("synthetic browser password")
                page.locator('input[name="verification_code"]').fill(totp_code(account.secret, timestamp=datetime.now(timezone.utc)))
                page.get_by_role("button", name="Sign in securely").click()
                page.locator("#advocate-directory-panel summary").click()
                playwright.expect(page.locator("#advocate-directory-results")).to_contain_text("Synthetic Browser Advocate")
                page.locator('#advocate-directory-filters input[name="district"]').fill("Pune")
                page.locator('#advocate-directory-filters input[name="search"]').fill("Synthetic Browser Advocate")
                page.get_by_role("button", name="Apply filters").click()
                playwright.expect(page.locator("#advocate-directory-count")).to_contain_text("1 matching")
                playwright.expect(page.locator("#advocate-filter-state")).to_contain_text("search:")
                page.get_by_role("button", name="View details for Synthetic Browser Advocate").click()
                if os.environ.get("NYAYSETU_SYNTHETIC_DETAIL_PREVIEW"):
                    page.locator("#advocate-detail-dialog").screenshot(path=os.environ["NYAYSETU_SYNTHETIC_DETAIL_PREVIEW"])
                page.get_by_label("Non-sensitive verification evidence reference").fill("synthetic-evidence")
                page.get_by_label("I independently checked this advocate's credentials and eligibility.").check()
                page.on("dialog", lambda dialog: dialog.accept())
                page.get_by_role("button", name="Record verification").click()
                playwright.expect(page.locator("#advocate-directory-results")).to_contain_text("VERIFIED")
                playwright.expect(page.locator("#advocate-directory-success")).to_contain_text("Verification recorded")
                page.get_by_role("button", name="View details for Synthetic Browser Advocate").click()
                page.get_by_role("button", name="Show registration and verification history").click()
                playwright.expect(page.locator("#advocate-detail-content")).to_contain_text("advocate.verify")
                page.get_by_role("button", name="Close advocate details").click()
                page.locator('#advocate-directory-filters select[name="status"]').select_option("PENDING")
                playwright.expect(page.locator("#advocate-filter-state")).to_contain_text("Filters changed")
                playwright.expect(page.locator("#advocate-directory-count")).to_contain_text("1 matching")
                page.get_by_role("button", name="Apply filters").click()
                playwright.expect(page.locator("#advocate-directory-count")).to_contain_text("0 matching")
                page.get_by_role("button", name="Clear filters").click()
                playwright.expect(page.locator("#advocate-directory-count")).to_contain_text("3 matching")
                page.get_by_role("button", name="View details for Synthetic Incomplete Advocate").click()
                playwright.expect(page.locator("#advocate-detail-content")).to_contain_text("Verification unavailable")
                assert page.get_by_role("button", name="Record verification").count() == 0
                page.get_by_role("button", name="Close advocate details").click()
                page.set_viewport_size({"width": 390, "height": 844})
                overflowing = page.evaluate("""() => [...document.querySelectorAll('body *')].filter(e => !e.closest('.table-wrap') && e.getBoundingClientRect().right > innerWidth + 1 && getComputedStyle(e).position !== 'fixed').slice(0, 10).map(e => [e.tagName, e.id, e.className, Math.round(e.getBoundingClientRect().right)])""")
                dimensions = page.evaluate("""() => ({root: document.documentElement.scrollWidth, body: document.body.scrollWidth, viewport: innerWidth, panel: document.querySelector('#advocate-directory-panel').scrollWidth, panelWidth: document.querySelector('#advocate-directory-panel').clientWidth})""")
                assert dimensions["panel"] <= dimensions["panelWidth"] + 1, (dimensions, overflowing)
                assert not overflowing, (dimensions, overflowing)
                assert dimensions["root"] <= dimensions["viewport"], dimensions
                playwright.expect(page.locator(".table-wrap .visually-hidden")).to_have_text("Actions")
                page.set_viewport_size({"width": 320, "height": 720})
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.get_by_role("button", name="View details for Synthetic Incomplete Advocate").click()
                playwright.expect(page.locator("#advocate-detail-content")).to_contain_text("Verification unavailable")
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.get_by_role("button", name="Close advocate details").click()
                if os.environ.get("NYAYSETU_SYNTHETIC_MOBILE_PREVIEW"):
                    page.locator("#advocate-directory-panel").screenshot(path=os.environ["NYAYSETU_SYNTHETIC_MOBILE_PREVIEW"])
                if os.environ.get("NYAYSETU_SYNTHETIC_PREVIEW"):
                    page.set_viewport_size({"width": 1280, "height": 900})
                    page.evaluate("document.querySelector('.topbar').remove()")
                    page.locator("#advocate-directory-panel").screenshot(path=os.environ["NYAYSETU_SYNTHETIC_PREVIEW"])
                page.get_by_role("button", name="Refresh", exact=True).click()
                playwright.expect(page.get_by_role("button", name="Refresh", exact=True)).to_be_enabled()
                playwright.expect(page.locator("#appointment-rows")).to_contain_text("Admin Test User")
                page.locator("#appointment-rows").get_by_role("button", name="Update").click()
                playwright.expect(page.locator("#dialog-advocate")).to_contain_text("Synthetic Browser Advocate")
            finally:
                browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
