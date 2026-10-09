from __future__ import annotations

import argparse
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
    ".gitattributes",
    "LICENSE",
    "README.md",
    "VERSION",
    "backend/app/main.py",
    "backend/app/engine/runtime/__init__.py",
    "backend/app/engine/runtime/deadlines.py",
    "backend/rules/special_cards.yaml",
    "frontend/e2e/acceptance/production-card-render.spec.ts",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/playwright.config.ts",
    "frontend/playwright.production.config.ts",
    "frontend/tsconfig.json",
    "frontend/vite.config.ts",
    "pytest.ini",
    "requirements.txt",
    "requirements-dev.txt",
    "scripts/package_release.py",
    "scripts/run_tests.sh",
    "scripts/start_backend.sh",
    "scripts/start_frontend_dev.sh",
    "scripts/validate-card-assets.py",
]

EXCLUDED_PARTS = {
    ".cache",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".pytest_tmp",
    ".ruff_cache",
    ".tmp",
    ".venv",
    ".vite",
    "__pycache__",
    "coverage",
    "dist",
    "htmlcov",
    "inputs",
    "node_modules",
    "playwright-report",
    "reference",
    "test-results",
    "venv",
}

EXCLUDED_NAMES = {
    ".duckdns_token",
    ".env",
    ".npmrc",
    ".pypirc",
}

EXCLUDED_SUFFIXES = {
    ".db",
    ".key",
    ".log",
    ".p12",
    ".pem",
    ".pfx",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite3",
    ".tmp",
}


def should_include(path: Path, root: Path = ROOT) -> bool:
    relative = path.relative_to(root)
    parts = relative.parts
    if parts and parts[0] in {"runtime", "data"}:
        return False
    if any(part in EXCLUDED_PARTS for part in parts):
        return False
    name = path.name.lower()
    if name in EXCLUDED_NAMES or (
        name.startswith(".env.")
        and name not in {".env.example", ".env.sample", ".env.template"}
    ):
        return False
    return path.suffix.lower() not in EXCLUDED_SUFFIXES


def iter_release_files(root: Path = ROOT) -> list[Path]:
    files: list[Path] = []
    for entry in INCLUDE_PATHS:
        path = root / entry
        if not path.exists():
            continue
        if path.is_file():
            if path.is_symlink():
                continue
            if should_include(path, root):
                files.append(path)
            continue
        for child in path.rglob("*"):
            if child.is_symlink():
                continue
            if child.is_file() and should_include(child, root):
                files.append(child)
    return sorted(set(files))


def validate_required_files(files: list[Path], root: Path = ROOT) -> None:
    selected = {path.relative_to(root).as_posix() for path in files}
    missing = [item for item in REQUIRED_PATHS if item not in selected]
    if missing:
        raise RuntimeError(f"required release files missing: {', '.join(missing)}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_mode(path: Path) -> int:
    return 0o755 if path.suffix == ".sh" else 0o644


def build_archives(root: Path, output_dir: Path, basename: str) -> tuple[Path, Path, list[Path]]:
    root = root.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    package_path = output_dir / f"{basename}.zip"
    tar_path = output_dir / f"{basename}_modes.tar.gz"
    files = iter_release_files(root)
    validate_required_files(files, root)
    with ZipFile(package_path, "w", ZIP_DEFLATED) as archive:
        for path in files:
            arcname = path.relative_to(root).as_posix()
            archive.write(path, arcname)
            info = archive.getinfo(arcname)
            info.create_system = 3
            info.external_attr = (0o100000 | archive_mode(path)) << 16
    with tarfile.open(tar_path, "w:gz") as archive:
        for path in files:
            arcname = path.relative_to(root).as_posix()
            info = archive.gettarinfo(str(path), arcname=arcname)
            info.mode = archive_mode(path)
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            with path.open("rb") as handle:
                archive.addfile(info, handle)
    return package_path, tar_path, files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build matching ZIP and mode-preserving TAR source archives."
    )
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=DIST)
    parser.add_argument(
        "--basename",
        default=f"suicardgame-rebuild-{datetime.now():%Y%m%d-%H%M%S}",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    package_path, tar_path, files = build_archives(
        args.source_root, args.output_dir, args.basename
    )
    print(f"{package_path}")
    print(f"sha256={sha256_file(package_path)}")
    print(f"{tar_path}")
    print(f"sha256={sha256_file(tar_path)}")
    print(f"members={len(files)}")


if __name__ == "__main__":
    main()
