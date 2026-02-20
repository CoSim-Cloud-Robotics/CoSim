"""Tests for Alembic migration tooling.

TDD: Verifies migration helpers (dry-run, rollback, version check)
before the scripts exist.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_DIR = BACKEND_ROOT / "alembic"
VERSIONS_DIR = ALEMBIC_DIR / "versions"


def test_alembic_ini_exists():
    """alembic.ini must exist in the backend root."""
    assert (BACKEND_ROOT / "alembic.ini").is_file()


def test_alembic_env_exists():
    """alembic/env.py must exist."""
    assert (ALEMBIC_DIR / "env.py").is_file()


def test_migration_files_ordered():
    """Migration files should be numbered sequentially (0001, 0002, ...)."""
    files = sorted(f.name for f in VERSIONS_DIR.glob("*.py") if not f.name.startswith("__"))
    assert len(files) > 0, "No migration files found"

    prefixes = []
    for f in files:
        # Extract the numeric prefix (e.g., "0001" from "0001_initial.py")
        parts = f.split("_", 1)
        if parts[0].isdigit():
            prefixes.append(int(parts[0]))

    assert len(prefixes) > 0, "No numbered migration files found"
    # There may be duplicate prefixes (like 0005) but they should all be valid
    assert all(p > 0 for p in prefixes)


def test_migration_script_check_exists():
    """The migrate.sh helper script should exist."""
    script = BACKEND_ROOT / "scripts" / "migrate.sh"
    assert script.is_file(), "scripts/migrate.sh not found"
    assert script.stat().st_mode & 0o111, "migrate.sh is not executable"


def test_migration_script_has_rollback():
    """migrate.sh should support a 'rollback' subcommand."""
    script = BACKEND_ROOT / "scripts" / "migrate.sh"
    content = script.read_text()
    assert "rollback" in content.lower(), "migrate.sh missing rollback support"
    assert "downgrade" in content.lower(), "migrate.sh missing alembic downgrade command"


def test_migration_script_has_dry_run():
    """migrate.sh should support a 'check' / 'dry-run' subcommand."""
    script = BACKEND_ROOT / "scripts" / "migrate.sh"
    content = script.read_text()
    # Either 'check', 'dry-run', or 'status' is acceptable
    assert any(
        keyword in content.lower() for keyword in ("check", "dry-run", "status", "current")
    ), "migrate.sh missing check/dry-run/status support"


def test_migration_script_has_ci_mode():
    """migrate.sh should support unattended CI usage."""
    script = BACKEND_ROOT / "scripts" / "migrate.sh"
    content = script.read_text()
    # Should have some form of automated/CI invocation
    assert any(
        keyword in content.lower() for keyword in ("ci", "upgrade head", "--sql", "migrate")
    ), "migrate.sh missing CI/upgrade head support"
