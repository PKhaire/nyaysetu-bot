"""Tests for the production process and Render deployment contract."""

from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_config_rejects_unknown_environment(monkeypatch):
    monkeypatch.setenv("ENV", "prod")

    with pytest.raises(ValueError, match="ENV must be one of"):
        runpy.run_path(str(PROJECT_ROOT / "config.py"))


def test_staging_disables_automatic_schema_creation_by_default(monkeypatch):
    monkeypatch.setenv("ENV", "staging")
    monkeypatch.delenv("AUTO_CREATE_SCHEMA", raising=False)

    config = runpy.run_path(str(PROJECT_ROOT / "config.py"))

    assert config["AUTO_CREATE_SCHEMA"] is False


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
    assert (
        "- key: LEGAL_CONTENT_REVIEWED_VERSION\n        sync: false"
        in blueprint
    )


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
        "ANALYTICS_EVENT_TTL_DAYS": 1,
        "OUTBOX_COMPLETED_TTL_DAYS": 1,
        "PAYMENT_LINK_TTL_MINUTES": 1,
        "PAYMENT_RECONCILIATION_LOOKBACK_DAYS": 2,
        "SUPPORT_SLA_HOURS": 1,
        "SUPPORT_NOTIFICATION_EMAILS": 2,
        "CONSULTATION_REMINDER_CATCHUP_MINUTES": 2,
    }
    for key, count in expected_reference_counts.items():
        assert blueprint.count(f"envVarKey: {key}") == count
