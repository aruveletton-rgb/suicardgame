from __future__ import annotations

import hashlib
import tarfile
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"

INCLUDE_PATHS = [
    "backend",
    "frontend",
    "docs",
    "deploy_templates",
    "scripts",
    ".gitattributes",
    "LICENSE",
    "README.md",
    "VERSION",
    "pytest.ini",
    "requirements.txt",
    "requirements-dev.txt",
]

REQUIRED_PATHS = [
    "backend/app/engine/runtime/__init__.py",
    "backend/app/engine/runtime/deadlines.py",
    "deploy_templates/deploy_checklist.md",
    "deploy_templates/nginx-suicardgame.conf.template",
    "deploy_templates/rollback_checklist.md",
    "deploy_templates/suicardgame.service.template",
    "frontend/package.json",
    "frontend/package-lock.json",
    "pytest.ini",
    "requirements.txt",
    "requirements-dev.txt",
    "scripts/run_tests.sh",
]

EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".pytest_tmp",
    ".ruff_cache",
    ".tmp",
    "__pycache__",
    "dist",
    "inputs",
    "node_modules",
    "reference",
    "test-results",
}

EXCLUDED_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
}

EXCLUDED_SUFFIXES = {
    ".db",
    ".log",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite3",
    ".tmp",
}


def should_include(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    parts = relative.parts
    if parts and parts[0] in {"runtime", "data"}:
        return False
    if any(part in EXCLUDED_PARTS for part in parts):
        return False
    if path.name in EXCLUDED_NAMES:
        return False
    return path.suffix not in EXCLUDED_SUFFIXES


def iter_release_files() -> list[Path]:
    files: list[Path] = []
    for entry in INCLUDE_PATHS:
        path = ROOT / entry
        if not path.exists():
            continue
        if path.is_file():
            if should_include(path):
                files.append(path)
            continue
        for child in path.rglob("*"):
            if child.is_file() and should_include(child):
                files.append(child)
    return sorted(set(files))


def validate_required_files(files: list[Path]) -> None:
    selected = {path.relative_to(ROOT).as_posix() for path in files}
    missing = [item for item in REQUIRED_PATHS if item not in selected]
    if missing:
        raise RuntimeError(f"required release files missing: {', '.join(missing)}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    DIST.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    package_path = DIST / f"suicardgame-rebuild-{stamp}.zip"
    tar_path = DIST / f"suicardgame-rebuild-{stamp}_modes.tar.gz"
    files = iter_release_files()
    validate_required_files(files)
    with ZipFile(package_path, "w", ZIP_DEFLATED) as archive:
        for path in files:
            arcname = path.relative_to(ROOT).as_posix()
            archive.write(path, arcname)
            info = archive.getinfo(arcname)
            info.create_system = 3
            info.external_attr = (0o100755 if path.suffix == ".sh" else 0o100644) << 16
    with tarfile.open(tar_path, "w:gz") as archive:
        for path in files:
            archive.add(path, arcname=path.relative_to(ROOT).as_posix(), recursive=False)
    print(f"{package_path}")
    print(f"sha256={sha256_file(package_path)}")
    print(f"{tar_path}")
    print(f"sha256={sha256_file(tar_path)}")
    print(f"members={len(files)}")


if __name__ == "__main__":
    main()
