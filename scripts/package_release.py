from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"

INCLUDE_PATHS = [
    "backend",
    "frontend",
    "docs",
    "scripts",
    ".gitattributes",
    "LICENSE",
    "README.md",
    "VERSION",
    "pytest.ini",
    "requirements.txt",
    "requirements-dev.txt",
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
    "runtime",
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
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    if path.name in EXCLUDED_NAMES:
        return False
    return path.suffix not in EXCLUDED_SUFFIXES


def iter_release_files():
    for entry in INCLUDE_PATHS:
        path = ROOT / entry
        if not path.exists():
            continue
        if path.is_file():
            if should_include(path):
                yield path
            continue
        for child in path.rglob("*"):
            if child.is_file() and should_include(child):
                yield child


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
    with ZipFile(package_path, "w", ZIP_DEFLATED) as archive:
        for path in sorted(iter_release_files()):
            arcname = path.relative_to(ROOT).as_posix()
            archive.write(path, arcname)
            info = archive.getinfo(arcname)
            info.create_system = 3
            info.external_attr = (0o100755 if path.suffix == ".sh" else 0o100644) << 16
    print(f"{package_path}")
    print(f"sha256={sha256_file(package_path)}")


if __name__ == "__main__":
    main()
