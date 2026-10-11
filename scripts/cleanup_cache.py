"""Remove aged, regenerable project caches; dry-run unless --apply is given."""

import argparse
import json
import os
import stat
import time
from pathlib import Path


MIN_AGE_SECONDS = 30 * 86400


def safe_path(path, root):
    return path.resolve().is_relative_to(root) and not any(
        parent.is_symlink() for parent in [path, *path.parents] if parent != root.parent
    )


def cache_roots(root):
    for base in [root / "backend", root / "scripts"]:
        if not base.is_dir() or not safe_path(base, root):
            continue
        for parent, dirs, _ in os.walk(base, followlinks=False):
            dirs[:] = [name for name in dirs if not (Path(parent) / name).is_symlink()]
            if "__pycache__" in dirs:
                yield Path(parent) / "__pycache__", "python"
                dirs.remove("__pycache__")
    for relative, kind in [
        (".pytest_cache/v/cache", "pytest"),
        ("frontend/.vite", "vite"),
        ("frontend/node_modules/.vite", "vite"),
    ]:
        path = root / relative
        if path.is_dir() and safe_path(path, root):
            yield path, kind


def active_build_or_test(root):
    proc = Path("/proc")
    if not proc.is_dir():
        return False
    for entry in proc.iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            args = (entry / "cmdline").read_bytes().decode(errors="replace").split("\0")
            command = " ".join(args)
            cwd = (entry / "cwd").resolve()
            in_project = cwd.is_relative_to(root) or str(root) in command
            if in_project and any(word in command for word in ("vite", "pytest", "mypy", "ruff")):
                return True
        except (OSError, RuntimeError):
            continue
    return False


def cleanup(root, *, apply=False):
    root = Path(root).absolute()
    if not root.is_dir() or not safe_path(root, root.resolve()):
        raise ValueError("project root must be an existing directory without symlink ancestors")
    root = root.resolve()
    report = {"mode": "apply" if apply else "dry_run", "minimum_age_days": 30,
              "eligible_files": 0, "eligible_bytes": 0, "deleted_files": 0,
              "deleted_bytes": 0, "errors": 0, "skipped_active_build_or_test": False}
    if active_build_or_test(root):
        report["skipped_active_build_or_test"] = True
        return report
    cutoff = time.time() - MIN_AGE_SECONDS
    for cache, kind in cache_roots(root):
        for parent, dirs, files in os.walk(cache, followlinks=False):
            dirs[:] = [name for name in dirs if not (Path(parent) / name).is_symlink()]
            for name in files:
                path = Path(parent) / name
                if kind == "python" and path.suffix not in {".pyc", ".pyo"}:
                    continue
                if kind == "pytest" and name not in {"nodeids", "lastfailed", "stepwise"}:
                    continue
                if name.endswith(".lock") or not safe_path(path, root):
                    continue
                try:
                    before = path.lstat()
                    if not stat.S_ISREG(before.st_mode) or before.st_mtime > cutoff:
                        continue
                    report["eligible_files"] += 1
                    report["eligible_bytes"] += before.st_size
                    if apply:
                        current = path.lstat()
                        if (current.st_dev, current.st_ino, current.st_mtime_ns, current.st_size) != (
                            before.st_dev, before.st_ino, before.st_mtime_ns, before.st_size
                        ) or not safe_path(path, root):
                            continue
                        path.unlink()
                        report["deleted_files"] += 1
                        report["deleted_bytes"] += before.st_size
                except FileNotFoundError:
                    continue
                except OSError:
                    report["errors"] += 1
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = cleanup(args.root, apply=args.apply)
    print(json.dumps(result))
    raise SystemExit(1 if result["errors"] else 0)
