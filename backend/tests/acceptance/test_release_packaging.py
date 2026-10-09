from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path
from zipfile import ZipFile

from scripts import package_release


ROOT = Path(__file__).resolve().parents[3]
PACKAGER = ROOT / "scripts" / "package_release.py"
RUNTIME_PATHS = (
    "backend/app/engine/runtime/__init__.py",
    "backend/app/engine/runtime/deadlines.py",
)
TEMPLATE_PATHS = (
    "deploy_templates/deploy_checklist.md",
    "deploy_templates/nginx-suicardgame.conf.template",
    "deploy_templates/rollback_checklist.md",
    "deploy_templates/suicardgame.service.template",
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run_packager(source_root: Path, output_dir: Path, basename: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(source_root / "scripts" / "package_release.py"),
            "--source-root",
            str(source_root),
            "--output-dir",
            str(output_dir),
            "--basename",
            basename,
        ],
        cwd=source_root,
        capture_output=True,
        text=True,
        check=False,
    )


def _assert_clean_import(extract_root: Path, data_dir: Path) -> None:
    code = """
import json
from pathlib import Path
import backend.app.main as main
import backend.app.engine.runtime.deadlines as deadlines
print(json.dumps({
    "main": str(Path(main.__file__).resolve()),
    "runtime": str(Path(deadlines.__file__).resolve()),
}))
"""
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["SUICARDGAME_DATA_DIR"] = str(data_dir)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=extract_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    imported = json.loads(result.stdout.strip().splitlines()[-1])
    root = extract_root.resolve()
    assert Path(imported["main"]).is_relative_to(root)
    assert Path(imported["runtime"]).is_relative_to(root)


def test_generated_archives_are_complete_safe_and_clean_importable(tmp_path: Path) -> None:
    seed_output = tmp_path / "seed-output"
    seed_result = subprocess.run(
        [
            sys.executable,
            str(PACKAGER),
            "--source-root",
            str(ROOT),
            "--output-dir",
            str(seed_output),
            "--basename",
            "seed",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert seed_result.returncode == 0, seed_result.stderr

    source_root = tmp_path / "isolated-source"
    with ZipFile(seed_output / "seed.zip") as archive:
        archive.extractall(source_root)

    fake_forbidden = (
        "runtime/data/rooms/FICTIONAL-ROOM.json",
        "data/FICTIONAL-ROOM.json",
        "backend/__pycache__/leak.pyc",
        "backend/.cache/leak.bin",
        "backend/.env.test",
        "backend/fake-private.key",
        "frontend/node_modules/fake/index.js",
        "frontend/dist/old-index.js",
        "frontend/playwright-report/index.html",
    )
    for relative in fake_forbidden:
        target = source_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fictional forbidden content", encoding="utf-8")

    outside = tmp_path / "outside-secret.txt"
    outside.write_text("outside", encoding="utf-8")
    symlink = source_root / "backend" / "outside-secret-link.txt"
    try:
        symlink.symlink_to(outside)
    except OSError:
        symlink = None

    output_dir = tmp_path / "release-output"
    result = _run_packager(source_root, output_dir, "roundtrip")
    assert result.returncode == 0, result.stderr
    zip_path = output_dir / "roundtrip.zip"
    tar_path = output_dir / "roundtrip_modes.tar.gz"
    assert zip_path.is_file() and tar_path.is_file()

    expected_paths = {
        path.relative_to(source_root).as_posix()
        for path in package_release.iter_release_files(source_root)
    }
    with ZipFile(zip_path) as archive:
        zip_infos = {item.filename: item for item in archive.infolist() if not item.is_dir()}
        zip_hashes = {name: _sha256(archive.read(name)) for name in zip_infos}
    with tarfile.open(tar_path, "r:gz") as archive:
        tar_infos = {item.name: item for item in archive.getmembers() if item.isfile()}
        tar_hashes = {
            name: _sha256(archive.extractfile(info).read())
            for name, info in tar_infos.items()
        }

    assert set(zip_infos) == set(tar_infos) == expected_paths
    assert zip_hashes == tar_hashes
    assert all("\\" not in name and not name.startswith(("/", "./")) for name in expected_paths)
    assert all(".." not in Path(name).parts for name in expected_paths)
    assert not (set(fake_forbidden) & expected_paths)
    if symlink is not None:
        assert symlink.relative_to(source_root).as_posix() not in expected_paths

    for relative in RUNTIME_PATHS + TEMPLATE_PATHS:
        assert relative in expected_paths
        source_hash = _sha256((source_root / relative).read_bytes())
        assert zip_hashes[relative] == source_hash
        assert tar_hashes[relative] == source_hash

    for relative, info in zip_infos.items():
        expected_mode = 0o755 if relative.endswith(".sh") else 0o644
        assert stat.S_IMODE(info.external_attr >> 16) == expected_mode
        assert stat.S_IMODE(tar_infos[relative].mode) == expected_mode

    zip_extract = tmp_path / "zip-extract"
    tar_extract = tmp_path / "tar-extract"
    with ZipFile(zip_path) as archive:
        archive.extractall(zip_extract)
    with tarfile.open(tar_path, "r:gz") as archive:
        archive.extractall(tar_extract, filter="data")

    _assert_clean_import(zip_extract, tmp_path / "zip-data")
    _assert_clean_import(tar_extract, tmp_path / "tar-data")
    if os.name == "posix":
        assert os.access(tar_extract / "scripts" / "run_tests.sh", os.X_OK)

    if symlink is not None:
        symlink.unlink()
    missing_root = tmp_path / "missing-required-source"
    shutil.copytree(source_root, missing_root, symlinks=True)
    (missing_root / RUNTIME_PATHS[1]).unlink()
    missing_result = _run_packager(missing_root, tmp_path / "missing-output", "must-fail")
    assert missing_result.returncode != 0
    assert RUNTIME_PATHS[1] in missing_result.stderr
    assert not (tmp_path / "missing-output" / "must-fail.zip").exists()
