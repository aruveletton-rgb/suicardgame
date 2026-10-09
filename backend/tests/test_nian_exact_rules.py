import pytest

from backend.app.domain.room import PromptKind
from backend.app.engine.command_handler import Command, CommandError, process_command
from backend.app.repositories.json_store import room_from_snapshot, room_to_snapshot
from backend.tests.test_special_card_resolvers import activate, make_started_room, respond, special, uno


def test_nian_turn_end_discard_then_next_player_draws_and_state_persists():
    room, players, game = make_started_room()
    nian = special("nian")
    discard = uno("uno_blue_1")
    players[0].hand = [nian, discard]
    players[1].hand = [uno("uno_green_1")]
    deck_before = len(game.deck)

    result = activate(room, players[0], nian)

    assert result["special_kind"] == "nian"
    assert result["pending"] is True
    assert game.special_state["nian"]["enabled"] is True
    assert game.current_prompt is not None
    assert game.current_prompt.kind == PromptKind.NIAN_TURN_END_DISCARD
    assert game.current_prompt.responder_ids == [players[0].player_id]

    restored = room_from_snapshot(room_to_snapshot(room))
    assert restored.active_game is not None
    assert restored.active_game.current_prompt is not None
    assert restored.active_game.current_prompt.kind == PromptKind.NIAN_TURN_END_DISCARD

    respond(room, players[0], "discard_card", {"card_id": discard.card_id})

    assert discard not in players[0].hand
    assert game.current_player_id == players[1].player_id
    assert len(players[1].hand) == 2
    assert len(game.deck) == deck_before - 1
    assert game.current_prompt is None


def test_nian_peng_claim_jumps_turn_and_skips_turn_start_draw():
    room, players, game = make_started_room()
    game.special_state["nian"] = {"enabled": True, "seen_claims": []}
    red7 = uno("uno_red_7")
    end_discard = uno("uno_blue_1")
    peng_a = uno("uno_yellow_7")
    peng_b = uno("uno_green_7")
    players[0].hand = [red7, end_discard]
    players[1].hand = [peng_a, peng_b]
    players[2].hand = [uno("uno_blue_2")]
    game.deck = [uno("uno_red_1"), uno("uno_yellow_2"), uno("uno_green_3")]

    process_command(
        room,
        Command(
            action_id="play-red-7",
            room_id=room.room_id,
            player_id=players[0].player_id,
            command_type="PLAY_CARD",
            payload={"card_id": red7.card_id},
        ),
    )

    assert game.current_prompt is not None
    assert game.current_prompt.kind == PromptKind.NIAN_TURN_END_DISCARD
    respond(room, players[0], "discard_card", {"card_id": end_discard.card_id}, action_id="discard-before-claim")

    assert game.current_prompt is not None
    assert game.current_prompt.kind == PromptKind.NIAN_CLAIM_WINDOW
    assert game.current_prompt.responder_ids == [players[1].player_id]

    respond(
        room,
        players[1],
        "peng",
        {"card_ids": [peng_a.card_id, peng_b.card_id]},
        action_id="peng-claim",
    )

    assert game.current_prompt is not None
    assert game.current_prompt.kind == PromptKind.NIAN_CLAIM_WINDOW
    assert game.current_prompt.responder_ids == [players[2].player_id]
    respond(room, players[2], "pass", action_id="pass-after-peng")

    assert game.current_prompt is None
    assert game.current_player_id == players[1].player_id
    assert players[1].hand == []
    assert game.special_state["nian"]["last_claim"]["claim_type"] == "peng"


def test_nian_invalid_claim_is_rejected_without_advancing():
    room, players, game = make_started_room()
    game.special_state["nian"] = {"enabled": True, "seen_claims": []}
    red7 = uno("uno_red_7")
    end_discard = uno("uno_blue_1")
    wrong_a = uno("uno_yellow_6")
    wrong_b = uno("uno_green_7")
    players[0].hand = [red7, end_discard]
    players[1].hand = [wrong_a, wrong_b]

    process_command(
        room,
        Command(
            action_id="play-red-7-invalid-claim",
            room_id=room.room_id,
            player_id=players[0].player_id,
            command_type="PLAY_CARD",
            payload={"card_id": red7.card_id},
        ),
    )
    respond(room, players[0], "discard_card", {"card_id": end_discard.card_id}, action_id="discard-invalid")

    prompt_id = game.current_prompt.prompt_id
    with pytest.raises(CommandError, match="年牌碰需要数字相同的牌"):
        respond(
            room,
            players[1],
            "peng",
            {"card_ids": [wrong_a.card_id, wrong_b.card_id]},
            action_id="bad-peng",
        )

    assert game.current_prompt is not None
    assert game.current_prompt.prompt_id == prompt_id
    assert game.current_player_id == players[0].player_id
