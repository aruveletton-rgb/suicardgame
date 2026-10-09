from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.domain.cards import COLOR_LABELS, CardCategory, asset_manifest, iter_uno_specs


OUT = ROOT / "frontend" / "public" / "assets" / "cards" / "generated"
PORTRAIT_OUT = ROOT / "frontend" / "public" / "assets" / "cards" / "portraits"
AVATAR_OUT = ROOT / "frontend" / "public" / "assets" / "avatars"
DATA_OUT = ROOT / "frontend" / "src" / "data" / "cardManifest.json"

# 所有岁牌原图的左侧均为独立卡面。这里保留完整白边、名称和角色插画，
# 避免运行时把整张规则说明缩进手牌区域。坐标基于 1000×1000 原图；
# 非 1000px 素材按比例换算。
SPECIAL_CARD_CROP = (10, 14, 390, 584)

# 头像只裁角色/标志主体，不含右侧规则文字。键名与后端 AVATAR_IDS 一致。
AVATAR_CROPS = {
    "wang": (58, 105, 348, 435),
    "yu": (48, 145, 360, 457),
    "yi": (55, 145, 355, 445),
    "zuole": (45, 150, 365, 470),
    "xi": (48, 115, 352, 459),
    "shu": (42, 78, 358, 394),
    "chongyue": (28, 80, 372, 424),
    "ling": (38, 75, 362, 399),
}

AVATAR_ASSET_KEYS = {
    "wang": "sui_wang",
    "yu": "sui_yu",
    "yi": "sui_yi",
    "zuole": "sui_zuole",
    "xi": "sui_xi",
    "shu": "sui_shu",
    "chongyue": "sui_chongyue",
    "ling": "sui_ling",
}

# 底图文件名（与 generated/ 同目录，SVG 相对引用）
BG = {
    "red": "bg_red.jpg",
    "yellow": "bg_yellow.jpg",
    "green": "bg_green.jpg",
    "blue": "bg_blue.jpg",
    "wild": "bg_wild.jpg",
}


def svg_card(bg_file: str, title: str, subtitle: str = "", fg: str = "#ffffff") -> str:
    """用生成底图铺满卡面，中央程序化精确叠加数字/符号。"""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="360" height="540" viewBox="0 0 360 540" role="img" aria-label="{title}">
  <image href="{bg_file}" x="0" y="0" width="360" height="540" preserveAspectRatio="xMidYMid slice"/>
  <text x="180" y="330" text-anchor="middle" fill="{fg}" stroke="#000000" stroke-opacity="0.55" stroke-width="2" paint-order="stroke" font-family="Arial, Helvetica, sans-serif" font-size="150" font-weight="900">{subtitle or title}</text>
</svg>
"""


def public_asset_path(public_path: str) -> Path:
    if not public_path.startswith("/assets/"):
        raise ValueError(f"not a public asset path: {public_path}")
    return ROOT / "frontend" / "public" / public_path.removeprefix("/")


def scaled_box(box: tuple[int, int, int, int], width: int, height: int) -> tuple[int, int, int, int]:
    scale_x = width / 1000
    scale_y = height / 1000
    left, top, right, bottom = box
    return (
        round(left * scale_x),
        round(top * scale_y),
        round(right * scale_x),
        round(bottom * scale_y),
    )


def generate_special_card_crops(manifest: dict[str, str]) -> None:
    PORTRAIT_OUT.mkdir(parents=True, exist_ok=True)
    AVATAR_OUT.mkdir(parents=True, exist_ok=True)

    for asset_key, public_path in manifest.items():
        if not (asset_key.startswith("sui_") or asset_key.startswith("field_")):
            continue
        source = public_asset_path(public_path)
        with Image.open(source) as image:
            image = image.convert("RGB")
            crop = image.crop(scaled_box(SPECIAL_CARD_CROP, image.width, image.height))
            crop.resize((360, 540), Image.Resampling.LANCZOS).save(
                PORTRAIT_OUT / f"{asset_key}.webp",
                "WEBP",
                quality=90,
                method=6,
            )

    for avatar_id, asset_key in AVATAR_ASSET_KEYS.items():
        source = public_asset_path(manifest[asset_key])
        with Image.open(source) as image:
            image = image.convert("RGB")
            crop = image.crop(scaled_box(AVATAR_CROPS[avatar_id], image.width, image.height))
            crop.resize((256, 256), Image.Resampling.LANCZOS).save(
                AVATAR_OUT / f"{avatar_id}.webp",
                "WEBP",
                quality=88,
                method=6,
            )


def generate() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for spec in iter_uno_specs():
        path = OUT / f"{spec.asset_key}.svg"
        if spec.category == CardCategory.NUMBER:
            bg_file = BG[spec.color.value]
            body = str(spec.value)
        elif spec.category == CardCategory.ACTION:
            bg_file = BG[spec.color.value]
            body = {"skip": "SKIP", "reverse": "REV", "draw_two": "+2"}[spec.kind]
        else:
            bg_file = BG["wild"]
            body = "+4" if spec.kind == "wild_draw_four" else "WILD"
        path.write_text(svg_card(bg_file, body, body), encoding="utf-8")

    # 卡背：直接引用生成的卡背底图
    back = """<svg xmlns="http://www.w3.org/2000/svg" width="360" height="540" viewBox="0 0 360 540" role="img" aria-label="Card back">
  <image href="card_back.jpg" x="0" y="0" width="360" height="540" preserveAspectRatio="xMidYMid slice"/>
</svg>
"""
    (OUT / "card-back.svg").write_text(back, encoding="utf-8")
    manifest = asset_manifest()
    generate_special_card_crops(manifest)
    DATA_OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    generate()
