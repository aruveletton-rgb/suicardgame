from backend.app.domain.cards import (
    CardCategory,
    SPECIAL_CARD_SPECS,
    asset_manifest,
    build_core_uno_deck,
    build_special_cards,
    required_asset_keys,
    special_counts_for_player_count,
)


def test_core_uno_deck_is_108_four_color_cards():
    deck = build_core_uno_deck()
    assert len(deck) == 108
    assert {card.color for card in deck if card.color} == {"red", "yellow", "green", "blue"}
    assert all(card.color != "white" for card in deck)

    numbers = [card for card in deck if card.category == CardCategory.NUMBER]
    actions = [card for card in deck if card.category == CardCategory.ACTION]
    wilds = [card for card in deck if card.category == CardCategory.WILD]
    assert len(numbers) == 76
    assert len(actions) == 24
    assert len(wilds) == 8


def test_special_count_profiles_match_prompt():
    assert special_counts_for_player_count(2)["yi"] == 2
    assert special_counts_for_player_count(3)["cannot"] == 1
    assert special_counts_for_player_count(4)["ling"] == 2
    assert special_counts_for_player_count(7)["nian"] == 5
    assert special_counts_for_player_count(10)["fuzhou"] == 4


def test_cannot_is_field_card_not_player_deck():
    deck_cards, field_cards = build_special_cards(4)
    assert len(field_cards) == 1
    assert field_cards[0].kind == "cannot"
    assert field_cards[0].category == CardCategory.FIELD
    assert all(card.kind != "cannot" for card in deck_cards)


def test_asset_manifest_covers_all_specs():
    manifest = asset_manifest()
    assert "card_back" in manifest
    for spec in SPECIAL_CARD_SPECS:
        assert spec.asset_key in manifest
    assert required_asset_keys() == set(manifest)

