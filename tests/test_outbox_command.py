"""Operational contract tests for the bounded Render outbox command."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from jobs import process_outbox
from models import OutboxJob


def _health(**overrides: int) -> dict[str, int]:
    health = {
        "backlog_count": 0,
        "ready_count": 0,
        "deferred_count": 0,
        "running_count": 0,
        "dead_count": 0,
        "oldest_age_seconds": 0,
    }
    health.update(overrides)
    return health


def test_command_does_not_fail_for_a_scheduled_retry(monkeypatch, capsys):
    monkeypatch.setattr(
        process_outbox,
        "process_pending_jobs",
        lambda: (0, 1),
    )
    monkeypatch.setattr(
        process_outbox,
        "get_outbox_health",
        lambda: _health(
            backlog_count=1,
            deferred_count=1,
            oldest_age_seconds=12,
        ),
    )

    assert process_outbox.main() == 0
    output = capsys.readouterr().out
    assert "outbox_status=deferred" in output
    assert "outbox_deferred=1" in output


@pytest.mark.parametrize(
    "health",
    [
        _health(backlog_count=1, ready_count=1),
        _health(backlog_count=1, dead_count=1),
    ],
)
def test_command_fails_when_operator_attention_is_required(
    monkeypatch,
    capsys,
    health,
):
    monkeypatch.setattr(
        process_outbox,
        "process_pending_jobs",
        lambda: (0, 0),
    )
    monkeypatch.setattr(
        process_outbox,
        "get_outbox_health",
        lambda: health,
    )

    assert process_outbox.main() == process_outbox.CRITICAL_EXIT_CODE
    assert "outbox_status=critical" in capsys.readouterr().out


def test_render_module_command_runs_from_clean_project_root(tmp_path):
    """Execute Render's module path without injecting the project root."""

    project_root = Path(__file__).resolve().parents[1]
    assert (
        "startCommand: python -m jobs.process_outbox"
        in (project_root / "render.yaml").read_text(encoding="utf-8")
    )

    database_path = tmp_path / "outbox-command.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url)
    try:
        OutboxJob.__table__.create(engine)
    finally:
        engine.dispose()

    environment = os.environ.copy()
    # Preserve dependency locations used by non-venv test installations, but
    # prove that the command resolves ``jobs`` from its clean working directory
    # rather than a project-root PYTHONPATH entry.
    dependency_paths = [
        entry
        for entry in sys.path
        if entry and Path(entry).resolve() != project_root
    ]
    environment["PYTHONPATH"] = os.pathsep.join(dependency_paths)
    environment.update(
        {
            "ENV": "test",
            "DATABASE_URL": database_url,
            "LOG_LEVEL": "WARNING",
        }
    )

    result = subprocess.run(
        [sys.executable, "-m", "jobs.process_outbox"],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "outbox_status=healthy" in result.stdout
    assert "outbox_backlog=0" in result.stdout
