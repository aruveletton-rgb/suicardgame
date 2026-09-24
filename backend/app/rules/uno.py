from __future__ import annotations

from dataclasses import dataclass

from backend.app.domain.cards import Card, CardCategory, CardColor


@dataclass(frozen=True)
class PlayCheck:
    allowed: bool
    reason: str | None = None
    requires_color_choice: bool = False


def hand_has_color(hand: list[Card], color: CardColor | None) -> bool:
    if color is None:
        return False
    return any(card.color == color and card.category in {CardCategory.NUMBER, CardCategory.ACTION} for card in hand)


def can_play_card(
    *,
    top_card: Card | None,
    current_color: CardColor | None,
    hand: list[Card],
    candidate: Card,
) -> PlayCheck:
    if candidate.category == CardCategory.SUI:
        return PlayCheck(True)
    if candidate.category == CardCategory.FIELD:
        return PlayCheck(False, "场地牌不能作为手牌打出")
    if candidate.kind == "wild":
        return PlayCheck(True, requires_color_choice=True)
    if candidate.kind == "wild_draw_four":
        return PlayCheck(True, requires_color_choice=True)
    if top_card is None:
        return PlayCheck(True)
    if current_color is not None and candidate.color == current_color:
        return PlayCheck(True)
    if candidate.category == CardCategory.NUMBER and top_card.category == CardCategory.NUMBER and candidate.value == top_card.value:
        return PlayCheck(True)
    if candidate.category == CardCategory.ACTION and top_card.category == CardCategory.ACTION and candidate.kind == top_card.kind:
        return PlayCheck(True)
    return PlayCheck(False, "必须匹配颜色、数字或动作符号")


def wild_draw_four_challenge_result(previous_color: CardColor | None, played_by_hand_before_play: list[Card]) -> str:
    return "illegal" if hand_has_color(played_by_hand_before_play, previous_color) else "legal"
