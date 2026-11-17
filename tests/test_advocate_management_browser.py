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
    session_factory = request.getfixturevalue("admin_db")
    _seed_operations(session_factory)
    db = session_factory()
    now = datetime.now(timezone.utc)
    try:
        db.add(Advocate(name="Synthetic Browser Advocate", email="synthetic@example.com", category="family", district="Pune", active=True))
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
                page.get_by_role("button", name="Search advocates").click()
                playwright.expect(page.locator("#advocate-directory-count")).to_contain_text("1 matching")
                page.get_by_label("Non-sensitive verification evidence reference").fill("synthetic-evidence")
                page.get_by_label("I independently checked this advocate's credentials and eligibility.").check()
                page.on("dialog", lambda dialog: dialog.accept())
                page.get_by_role("button", name="Record verification").click()
                playwright.expect(page.locator("#advocate-directory-results")).to_contain_text("VERIFIED")
                page.get_by_role("button", name="Show registration and verification history").click()
                playwright.expect(page.locator("#advocate-directory-results")).to_contain_text("advocate.verify")
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
