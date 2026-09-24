from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.domain.cards import SPECIAL_CARD_SPECS, asset_manifest  # noqa: E402


def project_path(public_path: str) -> Path:
    if public_path.startswith("/") and len(public_path) > 2 and public_path[2] == ":":
        raise AssertionError(f"absolute local path is forbidden: {public_path}")
    if not public_path.startswith("/assets/"):
        raise AssertionError(f"asset path must be project-public: {public_path}")
    return ROOT / "frontend" / "public" / public_path.removeprefix("/")


def validate() -> None:
    manifest = asset_manifest()
    seen_special_files: dict[str, str] = {}
    for asset_key, public_path in manifest.items():
        path = project_path(public_path)
        if not path.exists():
            raise AssertionError(f"missing asset for {asset_key}: {path}")
        if path.suffix.lower() == ".jpg":
            with Image.open(path) as image:
                if image.width <= 0 or image.height <= 0:
                    raise AssertionError(f"zero-size image: {path}")
        elif path.suffix.lower() == ".svg":
            text = path.read_text(encoding="utf-8")
            if "<svg" not in text:
                raise AssertionError(f"invalid svg: {path}")
        else:
            raise AssertionError(f"unsupported asset type: {path}")
        if asset_key.startswith("sui_") or asset_key.startswith("field_"):
            if public_path in seen_special_files:
                raise AssertionError(f"special cards share image: {asset_key} and {seen_special_files[public_path]}")
            seen_special_files[public_path] = asset_key

    expected_special = {spec.asset_key for spec in SPECIAL_CARD_SPECS}
    missing_special = expected_special - set(manifest)
    if missing_special:
        raise AssertionError(f"missing special asset keys: {sorted(missing_special)}")

    manifest_path = ROOT / "frontend" / "src" / "data" / "cardManifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"validated {len(manifest)} assets")


if __name__ == "__main__":
    validate()

