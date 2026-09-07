"""Tests for the production process and Render deployment contract."""

from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _render_service_block(blueprint: str, service_name: str) -> str:
    marker = f"    name: {service_name}\n"
    marker_index = blueprint.index(marker)
    start = blueprint.rfind("\n  - type:", 0, marker_index)
    start = 0 if start == -1 else start + 1
    end = blueprint.find("\n  - type:", marker_index)
    return blueprint[start:] if end == -1 else blueprint[start:end]


def test_config_rejects_unknown_environment(monkeypatch):
    monkeypatch.setenv("ENV", "prod")

    with pytest.raises(ValueError, match="ENV must be one of"):
        runpy.run_path(str(PROJECT_ROOT / "config.py"))


def test_config_rejects_unknown_log_level(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LOG_LEVEL", "VERBOSE")

    with pytest.raises(ValueError, match="LOG_LEVEL must be one of"):
        runpy.run_path(str(PROJECT_ROOT / "config.py"))


def test_staging_disables_automatic_schema_creation_by_default(monkeypatch):
    monkeypatch.setenv("ENV", "staging")
    monkeypatch.delenv("AUTO_CREATE_SCHEMA", raising=False)

    config = runpy.run_path(str(PROJECT_ROOT / "config.py"))

    assert config["AUTO_CREATE_SCHEMA"] is False


def test_email_notifications_are_disabled_by_default(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.delenv("EMAIL_NOTIFICATIONS_ENABLED", raising=False)

    config = runpy.run_path(str(PROJECT_ROOT / "config.py"))

    assert config["EMAIL_NOTIFICATIONS_ENABLED"] is False


def test_document_studio_daily_capacity_must_be_positive(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("DOCUMENT_STUDIO_DAILY_CAPACITY", "0")

    with pytest.raises(
        ValueError,
        match="DOCUMENT_STUDIO_DAILY_CAPACITY must be at least 1",
    ):
        runpy.run_path(str(PROJECT_ROOT / "config.py"))


def _gunicorn_config(monkeypatch):
    monkeypatch.setenv("PORT", "12345")
    return runpy.run_path(str(PROJECT_ROOT / "gunicorn.conf.py"))


def test_gunicorn_config_is_single_process_and_query_safe(monkeypatch):
    config = _gunicorn_config(monkeypatch)

    assert config["bind"] == "0.0.0.0:12345"
    assert config["workers"] == 1
    assert config["worker_class"] == "gthread"
    assert 1 <= config["threads"] <= 16
    assert config["timeout"] == 60
    assert config["graceful_timeout"] == 30
    assert config["max_requests"] == 1_000
    assert config["max_requests_jitter"] == 100
    assert config["accesslog"] == "-"
    assert config["errorlog"] == "-"

    access_format = config["access_log_format"]
    assert "%(U)s" in access_format
    assert "%(q)s" not in access_format
    assert "%(r)s" not in access_format
    assert "%(f)s" not in access_format


def test_gunicorn_config_rejects_worker_override(monkeypatch):
    config = _gunicorn_config(monkeypatch)
    on_starting = config["on_starting"]

    on_starting(SimpleNamespace(cfg=SimpleNamespace(workers=1)))
    with pytest.raises(RuntimeError, match="exactly one Gunicorn worker"):
        on_starting(SimpleNamespace(cfg=SimpleNamespace(workers=2)))


def test_deployment_commands_and_render_release_controls_exist():
    procfile = (PROJECT_ROOT / "Procfile").read_text(encoding="utf-8")
    blueprint = (PROJECT_ROOT / "render.yaml").read_text(encoding="utf-8")

    assert (
        "release: python -m alembic -c alembic.ini upgrade head"
        in procfile
    )
    assert "web: gunicorn --config gunicorn.conf.py app:app" in procfile

    assert "preDeployCommand: python -m alembic -c alembic.ini upgrade head" in (
        blueprint
    )
    assert "startCommand: gunicorn --config gunicorn.conf.py app:app" in blueprint
    assert blueprint.count("region: singapore") == 5
    assert blueprint.count("autoDeployTrigger: off") == 5
    assert blueprint.count(
        "- key: AUTO_CREATE_SCHEMA\n        value: \"false\""
    ) == 5
    assert blueprint.count(
        "- key: MAINTENANCE_MODE\n        value: \"false\""
    ) == 1
    assert blueprint.count(
        "- key: WEB_CONCURRENCY\n        value: \"1\""
    ) == 1
    assert blueprint.count(
        "- key: GUNICORN_CMD_ARGS\n        value: \"--workers 1\""
    ) == 1
    assert (
        "- key: LEGAL_CONTENT_REVIEWED_VERSION\n        sync: false"
        in blueprint
    )
    assert "- key: ADMIN_PASSWORD\n        sync: false" in blueprint
    assert "- key: SECRET_KEY\n        generateValue: true" in blueprint
    assert (
        '- key: DOCUMENT_STUDIO_ENABLED\n        value: "false"'
        in blueprint
    )
    assert (
        "- key: DOCUMENT_STUDIO_PRODUCT_ALLOWLIST\n"
        "        value: mh_residential_leave_licence_11m_self_service"
        in blueprint
    )
    assert "DOCUMENT_STUDIO_UAT_ONLY" not in blueprint
    assert "DOCUMENT_STUDIO_TESTER_WA_IDS" not in blueprint
    assert "- key: DOCUMENT_STUDIO_PRICE_INR" in blueprint
    assert (
        '- key: DOCUMENT_STUDIO_DAILY_CAPACITY\n        value: "10"'
        in blueprint
    )
    assert "- key: DOCUMENT_STUDIO_S3_BUCKET" in blueprint


def test_render_only_schedules_existing_operational_modules():
    blueprint = (PROJECT_ROOT / "render.yaml").read_text(encoding="utf-8")

    assert (PROJECT_ROOT / "jobs" / "process_outbox.py").is_file()
    assert (PROJECT_ROOT / "jobs" / "maintenance.py").is_file()
    assert (PROJECT_ROOT / "jobs" / "reconcile_payments.py").is_file()
    assert (PROJECT_ROOT / "jobs" / "consultation_reminders.py").is_file()
    assert "python -m jobs.process_outbox" in blueprint
    assert (
        "python -m jobs.maintenance --batch-size 500 --fail-on-risk"
        in blueprint
    )
    assert "python -m jobs.reconcile_payments --limit 100" in blueprint
    assert "python -m jobs.consultation_reminders" in blueprint
    assert 'schedule: "*/5 * * * *"' in blueprint
    assert 'schedule: "*/10 * * * *"' in blueprint


def test_render_pins_operational_policy_for_maintenance():
    blueprint = (PROJECT_ROOT / "render.yaml").read_text(encoding="utf-8")

    expected_web_values = {
        "WEBHOOK_REPLAY_WINDOW_SECONDS": "0",
        "WEBHOOK_EVENT_TTL_DAYS": "30",
        "PROCESSED_MESSAGE_TTL_DAYS": "30",
        "CASE_BRIEF_UNATTACHED_TTL_DAYS": "7",
        "DOCUMENT_STUDIO_DAILY_CAPACITY": "10",
        "ANALYTICS_EVENT_TTL_DAYS": "90",
        "OUTBOX_COMPLETED_TTL_DAYS": "30",
        "PAYMENT_LINK_TTL_MINUTES": "16",
        "PAYMENT_RECONCILIATION_LOOKBACK_DAYS": "14",
        "SUPPORT_SLA_HOURS": "24",
    }
    for key, value in expected_web_values.items():
        assert f"- key: {key}\n        value: \"{value}\"" in blueprint

    expected_reference_counts = {
        "PROCESSED_MESSAGE_TTL_DAYS": 1,
        "CASE_BRIEF_UNATTACHED_TTL_DAYS": 1,
        "DOCUMENT_STUDIO_DRAFT_TTL_DAYS": 1,
        "DOCUMENT_STUDIO_DOWNLOAD_TTL_SECONDS": 2,
        "DOCUMENT_STUDIO_FINAL_TTL_DAYS": 1,
        "DOCUMENT_STUDIO_PRICE_INR": 1,
        "DOCUMENT_STUDIO_S3_BUCKET": 3,
        "DOCUMENT_STUDIO_S3_REGION": 3,
        "DOCUMENT_STUDIO_S3_ACCESS_KEY_ID": 3,
        "DOCUMENT_STUDIO_S3_SECRET_ACCESS_KEY": 3,
        "DOCUMENT_STUDIO_S3_ENDPOINT_URL": 3,
        "ANALYTICS_EVENT_TTL_DAYS": 1,
        "OUTBOX_COMPLETED_TTL_DAYS": 1,
        "PAYMENT_LINK_TTL_MINUTES": 1,
        "PAYMENT_RECONCILIATION_LOOKBACK_DAYS": 2,
        "SUPPORT_SLA_HOURS": 1,
        "EMAIL_NOTIFICATIONS_ENABLED": 2,
        "CONSULTATION_REMINDER_CATCHUP_MINUTES": 2,
    }
    for key, count in expected_reference_counts.items():
        assert blueprint.count(f"envVarKey: {key}") == count

    outbox = _render_service_block(blueprint, "nyaysetu-outbox")
    for key in {
        "DOCUMENT_STUDIO_DOWNLOAD_TTL_SECONDS",
        "DOCUMENT_STUDIO_S3_BUCKET",
        "DOCUMENT_STUDIO_S3_REGION",
        "DOCUMENT_STUDIO_S3_ACCESS_KEY_ID",
        "DOCUMENT_STUDIO_S3_SECRET_ACCESS_KEY",
        "DOCUMENT_STUDIO_S3_ENDPOINT_URL",
    }:
        assert f"- key: {key}\n        fromService:" in outbox
        assert f"envVarKey: {key}" in outbox

    reconciliation = _render_service_block(
        blueprint, "nyaysetu-payment-reconciliation"
    )
    for key in {
        "DOCUMENT_STUDIO_PRICE_INR",
        "DOCUMENT_STUDIO_FINAL_TTL_DAYS",
        "DOCUMENT_STUDIO_DOWNLOAD_TTL_SECONDS",
        "DOCUMENT_STUDIO_S3_BUCKET",
        "DOCUMENT_STUDIO_S3_REGION",
        "DOCUMENT_STUDIO_S3_ACCESS_KEY_ID",
        "DOCUMENT_STUDIO_S3_SECRET_ACCESS_KEY",
        "DOCUMENT_STUDIO_S3_ENDPOINT_URL",
    }:
        assert f"- key: {key}\n        fromService:" in reconciliation
        assert f"envVarKey: {key}" in reconciliation

    maintenance = _render_service_block(blueprint, "nyaysetu-maintenance")
    for key in {
        "DOCUMENT_STUDIO_DRAFT_TTL_DAYS",
        "DOCUMENT_STUDIO_S3_BUCKET",
        "DOCUMENT_STUDIO_S3_REGION",
        "DOCUMENT_STUDIO_S3_ACCESS_KEY_ID",
        "DOCUMENT_STUDIO_S3_SECRET_ACCESS_KEY",
        "DOCUMENT_STUDIO_S3_ENDPOINT_URL",
    }:
        assert f"- key: {key}\n        fromService:" in maintenance
        assert f"envVarKey: {key}" in maintenance


def test_render_formally_disables_email_without_ses_credentials():
    blueprint = (PROJECT_ROOT / "render.yaml").read_text(encoding="utf-8")
    web = _render_service_block(blueprint, "nyaysetu-bot-backend")
    outbox = _render_service_block(blueprint, "nyaysetu-outbox")
    reconciliation = _render_service_block(
        blueprint, "nyaysetu-payment-reconciliation"
    )

    assert "SENDGRID" not in blueprint
    assert "    name: nyaysetu-bot-backend\n" in web
    assert "    domains:\n      - api.nyaysetu.in\n" in web
    assert (
        '- key: EMAIL_NOTIFICATIONS_ENABLED\n        value: "false"'
        in web
    )

    operator_supplied = {
        "BOOKING_PRICE",
        "WHATSAPP_APP_SECRET_PREVIOUS",
        "RAZORPAY_WEBHOOK_SECRET_PREVIOUS",
    }
    for key in operator_supplied:
        assert f"- key: {key}\n        sync: false" in web

    for service in (outbox, reconciliation):
        assert (
            "- key: EMAIL_NOTIFICATIONS_ENABLED\n        fromService:"
            in service
        )
        assert "envVarKey: EMAIL_NOTIFICATIONS_ENABLED" in service

    disabled_email_variables = {
        "SES_REGION",
        "SES_FROM_EMAIL",
        "SES_CONFIGURATION_SET",
        "SES_CONNECT_TIMEOUT_SECONDS",
        "SES_READ_TIMEOUT_SECONDS",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "BOOKING_NOTIFICATION_EMAILS",
        "PAYMENT_RECONCILIATION_EMAILS",
        "SUPPORT_NOTIFICATION_EMAILS",
    }
    for key in disabled_email_variables:
        assert f"- key: {key}" not in blueprint
        assert f"envVarKey: {key}" not in blueprint
