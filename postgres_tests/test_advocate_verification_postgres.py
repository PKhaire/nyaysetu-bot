"""Concurrent advocate verification on the disposable GitHub Actions database only."""

import base64
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

CI_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/nyaysetu_ci"


def test_postgres_concurrent_verification_commits_exactly_once(monkeypatch):
    if os.environ.get("NYAYSETU_POSTGRES_ADVOCATE_CI") != "1":
        pytest.skip("Run explicitly in the isolated PostgreSQL CI job")
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("DATABASE_URL") != CI_DATABASE_URL:
        pytest.fail("Refusing to run outside the designated disposable CI database")
    for key, value in {
        "ENV": "test", "ADMIN_TOKEN": "synthetic-ci-admin-token", "ALLOW_INSECURE_WEBHOOKS": "false",
        "WHATSAPP_APP_SECRET": "synthetic-ci-secret", "WHATSAPP_VERIFY_TOKEN": "synthetic-ci-verify",
        "WHATSAPP_PHONE_ID": "synthetic-ci-phone", "WHATSAPP_TOKEN": "synthetic-ci-token",
        "RAZORPAY_KEY_ID": "rzp_test_synthetic", "RAZORPAY_KEY_SECRET": "synthetic-ci-secret",
        "RAZORPAY_WEBHOOK_SECRET": "synthetic-ci-webhook", "RAZORPAY_MODE": "test",
    }.items():
        monkeypatch.setenv(key, value)
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import admin
    from app import app
    from models import AdminAuditEvent, AdminOperator, Advocate
    from services.admin_identity_service import begin_operator_enrollment, confirm_operator_enrollment, totp_code

    engine = create_engine(CI_DATABASE_URL)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(admin, "SessionLocal", sessions)
    monkeypatch.setattr(admin, "ADMIN_TOKEN", "synthetic-ci-admin-token")
    app.config.update(TESTING=True, SECRET_KEY="synthetic-ci-session-key-12345678", SESSION_COOKIE_SECURE=False)
    key = base64.urlsafe_b64encode(b"a" * 32).decode("ascii")
    now = datetime.now(timezone.utc)
    db = sessions()
    try:
        assert db.query(Advocate).count() == 0
        assert db.query(AdminOperator).count() == 0
        advocate = Advocate(name="Synthetic CI Advocate", email="synthetic@example.com", category="family", district="Pune", active=True)
        db.add(advocate)
        db.flush()
        advocate_id = advocate.id
        enrolled = begin_operator_enrollment(db, operator_id="synthetic.ci@example.com", display_name="Synthetic CI Admin", role="ADMIN", password="synthetic secure password", encryption_key=key, now=now)
        confirm_operator_enrollment(db, operator_id=enrolled.operator_id, verification_code=totp_code(enrolled.secret, timestamp=now), encryption_key=key, now=now)
        db.commit()
        operator = db.query(AdminOperator).filter_by(operator_id=enrolled.operator_id).one()
        operator_id, version = operator.id, operator.session_version
    finally:
        db.close()
    barrier = threading.Barrier(2)

    def attempt():
        client = app.test_client()
        csrf = "synthetic-csrf-token-value-1234567890"
        with client.session_transaction() as session:
            session.update(admin_authenticated=True, admin_auth_mode="named_mfa", admin_operator_db_id=operator_id,
                           operator_id=enrolled.operator_id, admin_session_version=version,
                           admin_mfa_authenticated=True, admin_csrf_token=csrf)
        barrier.wait(timeout=10)
        return client.post(f"/admin/advocates/{advocate_id}/verify", headers={"X-CSRF-Token": csrf},
                           json={"verification_reference": "synthetic-evidence", "independent_checks_confirmed": True}).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(lambda _index: attempt(), range(2)))
        assert sorted(statuses) == [200, 409]
        db = sessions()
        try:
            assert db.get(Advocate, advocate_id).verification_status == "VERIFIED"
            assert db.query(AdminAuditEvent).filter_by(action="advocate.verify", target_type="advocate", target_id=str(advocate_id)).count() == 1
        finally:
            db.close()
    finally:
        engine.dispose()
