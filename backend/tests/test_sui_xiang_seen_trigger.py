from backend.app.domain.cards import Card, CardCategory, CardSpec, build_game_deck
from backend.app.engine.special_effects import trigger_seen_card
from backend.tests.test_special_card_resolvers import make_started_room


def test_retired_sui_xiang_card_does_not_trigger_seen_effects():
    room, players, game = make_started_room()
    retired_card = Card.from_spec(
        CardSpec(CardCategory.SUI, "sui_xiang", "sui_sui_xiang", display_name="岁相")
    )
    players[0].hand = [retired_card]

    result = trigger_seen_card(
        room,
        observer_player_id=players[1].player_id,
        owner_player_id=players[0].player_id,
        card=retired_card,
        event_id="retired-seen-card",
        source="effect_reveal",
    )

    assert result is None
    assert retired_card in players[0].hand
    assert game.current_prompt is None
    assert game.effect_queue == []
    assert game.special_state.get("sui_xiang_seen_event_ids") is None


def test_retired_sui_xiang_card_is_not_in_current_decks():
    for player_count in (2, 3, 4, 5):
        deck, field = build_game_deck(player_count)
        assert all(card.kind != "sui_xiang" for card in [*deck, *field])
