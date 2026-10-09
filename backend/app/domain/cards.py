from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable
from uuid import uuid4


class CardCategory(StrEnum):
    NUMBER = "number"
    ACTION = "action"
    WILD = "wild"
    SUI = "sui"
    FIELD = "field"


class CardColor(StrEnum):
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"
    BLUE = "blue"


UNO_COLORS: tuple[CardColor, ...] = (
    CardColor.RED,
    CardColor.YELLOW,
    CardColor.GREEN,
    CardColor.BLUE,
)

COLOR_LABELS: dict[CardColor, str] = {
    CardColor.RED: "红",
    CardColor.YELLOW: "黄",
    CardColor.GREEN: "绿",
    CardColor.BLUE: "蓝",
}

ACTION_KINDS = ("skip", "reverse", "draw_two")
WILD_KINDS = ("wild", "wild_draw_four")


@dataclass(frozen=True)
class CardSpec:
    category: CardCategory
    kind: str
    asset_key: str
    color: CardColor | None = None
    value: int | None = None
    display_name: str | None = None
    source_filename: str | None = None
    source_text: str | None = None


@dataclass
class Card:
    card_id: str
    category: CardCategory
    kind: str
    asset_key: str
    color: CardColor | None = None
    value: int | None = None
    display_name: str | None = None

    @classmethod
    def from_spec(cls, spec: CardSpec) -> "Card":
        return cls(
            card_id=f"{spec.asset_key}-{uuid4().hex}",
            category=spec.category,
            kind=spec.kind,
            asset_key=spec.asset_key,
            color=spec.color,
            value=spec.value,
            display_name=spec.display_name,
        )


SPECIAL_CARD_SPECS: tuple[CardSpec, ...] = (
    CardSpec(CardCategory.SUI, "wang", "sui_wang", display_name="望牌", source_filename="15aefb709c02084fbf08600c51e42d85.jpg", source_text="可在别人无法打出合理的牌时即刻使用；查看其手牌并控制该玩家，直到你的回合开始。"),
    CardSpec(CardCategory.SUI, "yu", "sui_yu", display_name="余牌", source_filename="23db64326534b6478c57bae78d1c1590.jpg", source_text="弃四张颜色各不相同的牌；其他玩家按顺序弃一张本轮未出现颜色的牌；可从放弃玩家重新执行。"),
    CardSpec(CardCategory.SUI, "yi", "sui_yi", display_name="易牌", source_filename="23f1f0c5d35242bc5a52bba759946770.jpg", source_text="弃两张数字和为 8 的牌，令其他玩家各摸一张；本回合可多次执行。"),
    CardSpec(CardCategory.SUI, "zuole", "sui_zuole", display_name="左乐牌", source_filename="2f42240353fbe94ad44e1ee11070299b.jpg", source_text="任何人使用岁牌时响应，选择一名玩家，本回合内该岁牌效果对其无效。"),
    CardSpec(CardCategory.SUI, "xi", "sui_xi", display_name="夕牌", source_filename="3e25cb360344c2f96a7120b0bdc36335.jpg", source_text="当你被动需要牌时使用；可当作任意一张被要求使用的牌，使用后立即弃掉。"),
    CardSpec(CardCategory.SUI, "shu", "sui_shu", display_name="黍牌", source_filename="941e81d9c480f062462aed1364e55ad1.jpg", source_text="当某颜色手牌数大于等于其他玩家数时使用；将该色牌均分给其他玩家，余牌给手牌最少者之一。"),
    CardSpec(CardCategory.SUI, "chongyue", "sui_chongyue", display_name="重岳牌", source_filename="9bf6f1118300add4e001671f90641b5d.jpg", source_text="所有玩家依次展示四张不同颜色手牌；颜色不足则摸并展示，其他玩家阶段后可质疑使用者。"),
    CardSpec(CardCategory.SUI, "ling", "sui_ling", display_name="令牌", source_filename="a096ad301444ccefec6871995adafdef.jpg", source_text="所有玩家将手牌数补至发动时场上单人最高手牌数；自己也得补。"),
    CardSpec(CardCategory.FIELD, "cannot", "field_cannot", display_name="坎诺特牌", source_filename="ddc008e08c2dc031c8a7f115a3832c43.jpg", source_text="场地 NPC；开局前置于场上，周围放 8 张牌作为商品。"),
)

SPECIAL_BY_KIND = {spec.kind: spec for spec in SPECIAL_CARD_SPECS}
SPECIAL_BY_ASSET_KEY = {spec.asset_key: spec for spec in SPECIAL_CARD_SPECS}

SUI_RANK_ORDER: tuple[str, ...] = (
    "chongyue",
    "wang",
    "ling",
    "shu",
    "yi",
    "xi",
    "yu",
    "zuole",
)

SPECIAL_COUNT_PROFILES: dict[str, dict[str, int]] = {
    "small": {"chongyue": 1, "wang": 1, "ling": 1, "shu": 1, "yi": 2, "xi": 2, "yu": 1, "zuole": 2, "cannot": 1},
    "medium": {"chongyue": 1, "wang": 1, "ling": 2, "shu": 2, "yi": 3, "xi": 3, "yu": 2, "zuole": 3, "cannot": 1},
    "large": {"chongyue": 2, "wang": 1, "ling": 2, "shu": 2, "yi": 3, "xi": 4, "yu": 2, "zuole": 4, "cannot": 1},
    "huge": {"chongyue": 2, "wang": 2, "ling": 3, "shu": 3, "yi": 5, "xi": 5, "yu": 3, "zuole": 5, "cannot": 1},
}


def special_profile_for_player_count(player_count: int) -> str:
    if 2 <= player_count <= 3:
        return "small"
    if 4 <= player_count <= 5:
        return "medium"
    if 6 <= player_count <= 7:
        return "large"
    if 8 <= player_count <= 10:
        return "huge"
    raise ValueError("player_count must be between 2 and 10")


def special_counts_for_player_count(player_count: int) -> dict[str, int]:
    return dict(SPECIAL_COUNT_PROFILES[special_profile_for_player_count(player_count)])


def iter_uno_specs() -> Iterable[CardSpec]:
    for color in UNO_COLORS:
        for value in range(10):
            yield CardSpec(
                category=CardCategory.NUMBER,
                kind="number",
                color=color,
                value=value,
                asset_key=f"uno_{color.value}_{value}",
                display_name=f"{COLOR_LABELS[color]}{value}",
            )
        for action in ACTION_KINDS:
            label = {"skip": "禁止", "reverse": "反转", "draw_two": "+2"}[action]
            yield CardSpec(
                category=CardCategory.ACTION,
                kind=action,
                color=color,
                asset_key=f"uno_{color.value}_{action}",
                display_name=f"{COLOR_LABELS[color]}{label}",
            )
    yield CardSpec(CardCategory.WILD, "wild", "uno_wild", display_name="Wild")
    yield CardSpec(CardCategory.WILD, "wild_draw_four", "uno_wild_draw_four", display_name="Wild Draw Four")


def build_core_uno_deck() -> list[Card]:
    deck: list[Card] = []
    specs = {spec.asset_key: spec for spec in iter_uno_specs()}
    for color in UNO_COLORS:
        deck.append(Card.from_spec(specs[f"uno_{color.value}_0"]))
        for value in range(1, 10):
            deck.extend(Card.from_spec(specs[f"uno_{color.value}_{value}"]) for _ in range(2))
        for action in ACTION_KINDS:
            deck.extend(Card.from_spec(specs[f"uno_{color.value}_{action}"]) for _ in range(2))
    deck.extend(Card.from_spec(specs["uno_wild"]) for _ in range(4))
    deck.extend(Card.from_spec(specs["uno_wild_draw_four"]) for _ in range(4))
    return deck


def build_special_cards(player_count: int) -> tuple[list[Card], list[Card]]:
    counts = special_counts_for_player_count(player_count)
    deck_cards: list[Card] = []
    field_cards: list[Card] = []
    for kind, count in counts.items():
        spec = SPECIAL_BY_KIND[kind]
        target = field_cards if spec.category == CardCategory.FIELD else deck_cards
        target.extend(Card.from_spec(spec) for _ in range(count))
    return deck_cards, field_cards


def build_game_deck(player_count: int) -> tuple[list[Card], list[Card]]:
    special_deck, field_cards = build_special_cards(player_count)
    return build_core_uno_deck() + special_deck, field_cards


def asset_manifest() -> dict[str, str]:
    manifest: dict[str, str] = {"card_back": "/assets/cards/generated/card-back.svg"}
    for spec in iter_uno_specs():
        manifest[spec.asset_key] = f"/assets/cards/generated/{spec.asset_key}.svg"
    for spec in SPECIAL_CARD_SPECS:
        if spec.source_filename is not None:
            manifest[spec.asset_key] = f"/assets/cards/sui/{spec.source_filename}"
    return manifest


def required_asset_keys() -> set[str]:
    return set(asset_manifest())

