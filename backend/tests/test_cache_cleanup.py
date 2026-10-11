import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from scripts import cleanup_cache


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/cleanup_cache.py"


def cached_file(root, relative, *, old=True):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("generated-cache", encoding="utf-8")
    if old:
        timestamp = time.time() - 31 * 86400
        os.utime(path, (timestamp, timestamp))
    return path


def run_cleanup(root, *args):
    result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), *args], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_cache_cleanup_defaults_to_dry_run_and_only_deletes_old_allowlisted_files(tmp_path):
    old = [
        cached_file(tmp_path, "backend/app/__pycache__/main.cpython-311.pyc"),
        cached_file(tmp_path, "frontend/node_modules/.vite/deps/react.js"),
        cached_file(tmp_path, ".pytest_cache/v/cache/nodeids"),
    ]
    preserved = [
        cached_file(tmp_path, "backend/app/__pycache__/recent.pyc", old=False),
        cached_file(tmp_path, "backend/app/__pycache__/user-notes.txt"),
        cached_file(tmp_path, "backend/app/main.py"),
        cached_file(tmp_path, "data/rooms/snapshot.json"),
        cached_file(tmp_path, "runtime/data/rooms/snapshot.json"),
        cached_file(tmp_path, "frontend/dist/assets/old.js"),
        cached_file(tmp_path, "frontend/node_modules/react/index.js"),
        cached_file(tmp_path, "audit/report.json"),
        cached_file(tmp_path, "releases/backup.tar"),
        cached_file(tmp_path, ".pytest_cache/README.md"),
    ]
    dry = run_cleanup(tmp_path)
    assert dry["mode"] == "dry_run"
    assert dry["eligible_files"] == 3
    assert dry["deleted_files"] == 0
    assert all(path.exists() for path in old + preserved)
    applied = run_cleanup(tmp_path, "--apply")
    assert applied["deleted_files"] == 3
    assert applied["errors"] == 0
    assert all(not path.exists() for path in old)
    assert all(path.exists() for path in preserved)
    assert (tmp_path / "backend/app/__pycache__").is_dir()


def test_cache_cleanup_does_not_follow_directory_or_file_symlinks(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    outside = cached_file(tmp_path, "outside/important.pyc")
    parent = root / "backend/app/__pycache__"
    parent.mkdir(parents=True)
    try:
        (parent / "linked.pyc").symlink_to(outside)
        (root / "frontend").symlink_to(outside.parent, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable on this host")
    result = run_cleanup(root, "--apply")
    assert result["deleted_files"] == 0
    assert outside.exists()


def test_cache_cleanup_is_idempotent(tmp_path):
    cached_file(tmp_path, "scripts/__pycache__/helper.pyc")
    assert run_cleanup(tmp_path, "--apply")["deleted_files"] == 1
    result = run_cleanup(tmp_path, "--apply")
    assert result["eligible_files"] == 0
    assert result["deleted_files"] == 0


def test_cache_cleanup_defers_while_a_build_or_test_is_active(tmp_path, monkeypatch):
    old = cached_file(tmp_path, "frontend/node_modules/.vite/deps/react.js")
    monkeypatch.setattr(cleanup_cache, "active_build_or_test", lambda root: True)
    result = cleanup_cache.cleanup(tmp_path, apply=True)
    assert result["skipped_active_build_or_test"] is True
    assert result["deleted_files"] == 0
    assert old.exists()
