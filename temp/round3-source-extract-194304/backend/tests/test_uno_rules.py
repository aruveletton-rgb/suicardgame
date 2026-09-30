from backend.app.domain.cards import CardCategory, build_core_uno_deck
from backend.app.rules.uno import can_play_card, wild_draw_four_challenge_result


def by_asset(deck, asset_key):
    return next(card for card in deck if card.asset_key == asset_key)


def test_number_matches_color_or_value():
    deck = build_core_uno_deck()
    red_5 = by_asset(deck, "uno_red_5")
    red_7 = by_asset(deck, "uno_red_7")
    blue_5 = by_asset(deck, "uno_blue_5")
    green_9 = by_asset(deck, "uno_green_9")
    assert can_play_card(top_card=red_5, current_color=red_5.color, hand=[red_7], candidate=red_7).allowed
    assert can_play_card(top_card=red_5, current_color=red_5.color, hand=[blue_5], candidate=blue_5).allowed
    assert not can_play_card(top_card=red_5, current_color=red_5.color, hand=[green_9], candidate=green_9).allowed


def test_wild_draw_four_legality_is_resolved_by_challenge():
    deck = build_core_uno_deck()
    red_5 = by_asset(deck, "uno_red_5")
    wild_draw_four = next(card for card in deck if card.kind == "wild_draw_four")
    assert can_play_card(top_card=red_5, current_color=red_5.color, hand=[red_5, wild_draw_four], candidate=wild_draw_four).allowed
    assert can_play_card(top_card=red_5, current_color=red_5.color, hand=[wild_draw_four], candidate=wild_draw_four).allowed
    assert wild_draw_four_challenge_result(red_5.color, [red_5]) == "illegal"
    assert wild_draw_four_challenge_result(red_5.color, []) == "legal"


def test_no_penalty_stacking_rule_surface():
    deck = build_core_uno_deck()
    draw_two_cards = [card for card in deck if card.category == CardCategory.ACTION and card.kind == "draw_two"]
    assert len(draw_two_cards) == 8
    assert not any(hasattr(card, "penalty_stack") for card in draw_two_cards)
