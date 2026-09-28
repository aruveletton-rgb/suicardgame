import pytest

from backend.app.domain.cards import build_core_uno_deck
from backend.app.domain.room import PromptKind, Room, new_player
from backend.app.engine.command_handler import Command, CommandError, process_command
from backend.app.repositories.json_store import room_from_snapshot, room_to_snapshot
from backend.tests.ready_helpers import decline_has_sui_prompts


def card(asset_key):
    return next(item for item in build_core_uno_deck() if item.asset_key == asset_key)


def make_started_room():
    host = new_player("host", 0, is_host=True)
    players = [host, new_player("p1", 1), new_player("p2", 2)]
    room = Room(room_id="WDF001", host_player_id=host.player_id, players=players)
    for player in players:
        process_command(
            room,
            Command(
                action_id=f"ready-{player.player_id}",
                room_id=room.room_id,
                player_id=player.player_id,
                command_type="READY",
            ),
        )
    process_command(
        room,
        Command(
            action_id="start",
            room_id=room.room_id,
            player_id=host.player_id,
            command_type="START_GAME",
            payload={"seed": 7},
        ),
    )
    game = room.active_game
    assert game is not None
    for player in players:
        player.hand = []
    game.current_player_id = host.player_id
    game.discard_pile = [card("uno_red_5")]
    game.current_color = game.discard_pile[-1].color
    game.current_prompt = None
    game.effect_queue = []
    game.direction = 1
    return room, players, game


def play_wild_draw_four(room, source, *, extra_hand=None):
    game = room.active_game
    assert game is not None
    wild_draw_four = card("uno_wild_draw_four")
    source.hand = [wild_draw_four, *(extra_hand or [])]
    result = process_command(
        room,
        Command(
            action_id=f"play-{wild_draw_four.card_id}",
            room_id=room.room_id,
            player_id=source.player_id,
            command_type="PLAY_CARD",
            payload={"card_id": wild_draw_four.card_id, "chosen_color": "blue"},
        ),
    )
    assert game.current_prompt is not None
    return result, game.current_prompt.prompt_id


def respond(room, player, prompt_id, response, action_id):
    return process_command(
        room,
        Command(
            action_id=action_id,
            room_id=room.room_id,
            player_id=player.player_id,
            command_type="RESPOND_TO_PROMPT",
            payload={"prompt_id": prompt_id, "response": response},
        ),
    )


def test_decline_challenge_draws_four_and_skips_target():
    room, players, game = make_started_room()
    game.deck = [card("uno_blue_1"), card("uno_green_2"), card("uno_yellow_3"), card("uno_red_4")]
    _, prompt_id = play_wild_draw_four(room, players[0], extra_hand=[card("uno_green_9")])

    assert game.current_prompt.kind == PromptKind.WILD_DRAW_FOUR_CHALLENGE
    assert game.current_prompt.responder_ids == [players[1].player_id]
    assert game.current_player_id == players[1].player_id
    assert players[1].hand == []

    result = respond(room, players[1], prompt_id, "decline_challenge", "decline")
    decline_has_sui_prompts(room, action_prefix="decline-after-wdf")

    assert result["challenge_result"] == "declined"
    assert result["drawn_count"] == 4
    assert len(players[1].hand) == 4
    assert game.current_player_id == players[2].player_id
    assert game.current_prompt is None


def test_successful_challenge_penalizes_illegal_source_and_keeps_target_turn():
    room, players, game = make_started_room()
    game.deck = [card("uno_blue_1"), card("uno_green_2"), card("uno_yellow_3"), card("uno_red_4")]
    _, prompt_id = play_wild_draw_four(room, players[0], extra_hand=[card("uno_red_7")])

    result = respond(room, players[1], prompt_id, "challenge", "challenge-success")

    assert result["challenge_result"] == "illegal"
    assert result["penalty_player_id"] == players[0].player_id
    assert result["drawn_count"] == 4
    assert len(players[0].hand) == 5
    assert players[1].hand == []
    assert game.current_player_id == players[1].player_id


def test_failed_challenge_draws_six_and_skips_challenger():
    room, players, game = make_started_room()
    game.deck = [
        card("uno_blue_1"),
        card("uno_green_2"),
        card("uno_yellow_3"),
        card("uno_red_4"),
        card("uno_blue_5"),
        card("uno_green_6"),
    ]
    _, prompt_id = play_wild_draw_four(room, players[0], extra_hand=[card("uno_green_9")])

    result = respond(room, players[1], prompt_id, "challenge", "challenge-failed")
    decline_has_sui_prompts(room, action_prefix="decline-after-failed-challenge")

    assert result["challenge_result"] == "legal"
    assert result["penalty_player_id"] == players[1].player_id
    assert result["drawn_count"] == 6
    assert len(players[1].hand) == 6
    assert game.current_player_id == players[2].player_id


def test_challenge_pending_action_round_trips_through_snapshot():
    room, players, _game = make_started_room()
    room.active_game.deck = [card("uno_blue_1")]
    _, prompt_id = play_wild_draw_four(room, players[0], extra_hand=[card("uno_green_9")])

    restored = room_from_snapshot(room_to_snapshot(room))

    assert restored.active_game is not None
    assert restored.active_game.current_prompt is not None
    assert restored.active_game.current_prompt.prompt_id == prompt_id
    assert restored.active_game.current_prompt.kind == PromptKind.WILD_DRAW_FOUR_CHALLENGE
    assert restored.active_game.effect_queue[0]["prompt_id"] == prompt_id


def test_non_target_player_cannot_challenge():
    room, players, game = make_started_room()
    game.deck = [card("uno_blue_1")]
    _, prompt_id = play_wild_draw_four(room, players[0], extra_hand=[card("uno_green_9")])

    with pytest.raises(CommandError) as exc_info:
        respond(room, players[2], prompt_id, "challenge", "wrong-player")

    assert exc_info.value.code == "NOT_PROMPT_RESPONDER"
    assert game.current_prompt is not None


def test_challenge_window_is_single_use():
    room, players, game = make_started_room()
    game.deck = [card("uno_blue_1"), card("uno_green_2"), card("uno_yellow_3"), card("uno_red_4")]
    _, prompt_id = play_wild_draw_four(room, players[0], extra_hand=[card("uno_green_9")])
    respond(room, players[1], prompt_id, "decline_challenge", "first-response")

    with pytest.raises(CommandError) as exc_info:
        respond(room, players[1], prompt_id, "challenge", "second-response")

    assert exc_info.value.code == "STALE_PROMPT"
    assert game.current_prompt is not None
    assert game.current_prompt.prompt_id != prompt_id
    assert game.current_prompt.kind == PromptKind.HAS_SUI_CHALLENGE
    decline_has_sui_prompts(room, action_prefix="decline-after-single-use-check")
