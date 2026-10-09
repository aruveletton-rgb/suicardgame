from __future__ import annotations

import pytest

from backend.app.engine.special_effects import activate_special, respond_special_prompt
from backend.app.main import _serialize_room_state
from backend.tests.test_special_card_resolvers import make_started_room, special, uno


@pytest.mark.parametrize(
    ("source_kind", "source_hand", "activation_payload", "response_card_kind", "expected_action"),
    [
        (
            "yi",
            lambda: [special("yi"), uno("uno_red_2"), uno("uno_blue_6")],
            lambda cards: {"card_id": cards[0].card_id, "pair_card_ids": [cards[1].card_id, cards[2].card_id]},
            "zuole",
            "use_zuole",
        ),
        (
            "ling",
            lambda: [special("ling"), uno("uno_red_1")],
            lambda cards: {"card_id": cards[0].card_id},
            "wang",
            "evade",
        ),
        (
            "shu",
            lambda: [special("shu"), uno("uno_red_1"), uno("uno_red_2")],
            lambda cards: {"card_id": cards[0].card_id, "chosen_color": "red"},
            "ling",
            "evade",
        ),
    ],
)
def test_sui_reaction_snapshot_separates_actions_from_private_card_options(
    source_kind,
    source_hand,
    activation_payload,
    response_card_kind,
    expected_action,
):
    room, players, game = make_started_room()
    cards = source_hand()
    response_card = special(response_card_kind)
    players[0].hand = cards
    players[1].hand = []
    players[2].hand = [response_card]

    activate_special(room, players[0].player_id, activation_payload(cards))
    assert game.current_prompt is not None
    assert game.current_prompt.kind.value == "SUI_REACTION"
    assert game.current_prompt.responder_ids == [players[1].player_id]

    no_card_view = _serialize_room_state(room, players[1].player_id)["active_game"]["pending_action"]
    assert no_card_view["can_respond"] is True
    assert no_card_view["default_action"] == "pass"
    assert no_card_view["legal_responses"] == ["pass"]
    assert "private_option_card_ids" not in no_card_view

    public_view = _serialize_room_state(room)["active_game"]["pending_action"]
    waiting_view = _serialize_room_state(room, players[2].player_id)["active_game"]["pending_action"]
    assert public_view["legal_responses"] == []
    assert "private_option_card_ids" not in public_view
    assert waiting_view["can_respond"] is False
    assert waiting_view["legal_responses"] == []
    assert "private_option_card_ids" not in waiting_view
    assert response_card.card_id not in str(public_view)

    prompt = game.current_prompt
    respond_special_prompt(room, players[1].player_id, prompt.prompt_id, "pass", {})

    own_view = _serialize_room_state(room, players[2].player_id)["active_game"]["pending_action"]
    former_responder_view = _serialize_room_state(room, players[1].player_id)["active_game"]["pending_action"]
    public_view = _serialize_room_state(room)["active_game"]["pending_action"]
    assert own_view["can_respond"] is True
    assert own_view["legal_responses"] == ["pass", expected_action]
    assert own_view["private_option_card_ids"] == [response_card.card_id]
    assert former_responder_view["legal_responses"] == []
    assert "private_option_card_ids" not in former_responder_view
    assert "private_option_card_ids" not in public_view
    assert response_card.card_id not in str(former_responder_view)
    assert response_card.card_id not in str(public_view)
