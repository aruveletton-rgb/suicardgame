from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.domain.cards import COLOR_LABELS, CardCategory, asset_manifest, iter_uno_specs


OUT = ROOT / "frontend" / "public" / "assets" / "cards" / "generated"
DATA_OUT = ROOT / "frontend" / "src" / "data" / "cardManifest.json"

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
    DATA_OUT.write_text(json.dumps(asset_manifest(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    generate()
