from __future__ import annotations

import pytest

import backend.app.main as main
from backend.app.domain.cards import CardColor, build_core_uno_deck
from backend.app.domain.room import PromptKind, Room, new_player
from backend.app.engine.command_handler import Command, CommandError, process_command
from backend.app.engine.invariants import assert_room_invariants


def card(asset_key: str):
    return next(item for item in build_core_uno_deck() if item.asset_key == asset_key)


def make_started_room():
    host = new_player("host", 0, is_host=True)
    players = [host, new_player("p1", 1), new_player("p2", 2)]
    room = Room(room_id="WILD01", host_player_id=host.player_id, players=players)
    process_command(
        room,
        Command(
            action_id="start",
            room_id=room.room_id,
            player_id=host.player_id,
            command_type="START_GAME",
            payload={"seed": 202},
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
    assert_room_invariants(room)
    return room, players, game


def play(room: Room, player, item, *, action_id: str, **payload):
    return process_command(
        room,
        Command(
            action_id=action_id,
            room_id=room.room_id,
            player_id=player.player_id,
            command_type="PLAY_CARD",
            payload={"card_id": item.card_id, **payload},
        ),
    )


def respond(room: Room, player, prompt_id: str, response: str, *, action_id: str):
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


def collect_strings(value) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        found: set[str] = set()
        for item in value.values():
            found.update(collect_strings(item))
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for item in value:
            found.update(collect_strings(item))
        return found
    return set()


def hand_ids(player) -> set[str]:
    return {item.card_id for item in player.hand}


def assert_no_other_hand_leak(room: Room) -> None:
    public_snapshot = main._public_snapshot(room)
    for player in room.players:
        if "hand" in next(item for item in public_snapshot["state"]["players"] if item["player_id"] == player.player_id):
            raise AssertionError("public snapshot exposed a full hand")
    public_strings = collect_strings(public_snapshot)
    for player in room.players:
        if public_strings & hand_ids(player):
            raise AssertionError("public snapshot exposed a private hand card")
    for viewer in room.players:
        private_snapshot = main._private_snapshot(room, viewer.player_id)
        assert all("hand" not in item for item in private_snapshot["state"]["players"])
        other_ids = set().union(*(hand_ids(player) for player in room.players if player.player_id != viewer.player_id))
        if collect_strings(private_snapshot) & other_ids:
            raise AssertionError("private snapshot exposed another player's hand")


def test_wild_requires_valid_color_and_chosen_color_controls_next_match():
    room, players, game = make_started_room()
    wild = card("uno_wild")
    players[0].hand = [wild, card("uno_red_9")]

    with pytest.raises(CommandError) as missing_color:
        play(room, players[0], wild, action_id="wild-missing-color")
    assert missing_color.value.code == "COLOR_REQUIRED"

    with pytest.raises(CommandError) as bad_color:
        play(room, players[0], wild, action_id="wild-bad-color", chosen_color="purple")
    assert bad_color.value.code == "COLOR_REQUIRED"

    result = play(room, players[0], wild, action_id="wild-blue", chosen_color="blue")

    assert result["ok"] is True
    assert game.current_color == CardColor.BLUE
    assert game.current_player_id == players[1].player_id

    wrong_color = card("uno_red_7")
    right_color = card("uno_blue_9")
    players[1].hand = [wrong_color, right_color]

    with pytest.raises(CommandError) as rejected:
        play(room, players[1], wrong_color, action_id="red-after-blue-wild")
    assert rejected.value.code == "ILLEGAL_PLAY"

    play(room, players[1], right_color, action_id="blue-after-blue-wild")
    assert game.discard_pile[-1] is right_color


def test_wild_play_action_id_is_idempotent_without_replaying_color_choice():
    room, players, game = make_started_room()
    wild = card("uno_wild")
    players[0].hand = [wild, card("uno_red_9")]

    first = play(room, players[0], wild, action_id="same-wild", chosen_color="green")
    before_counts = (len(players[0].hand), len(game.discard_pile), game.current_color, game.current_player_id)
    second = play(room, players[0], wild, action_id="same-wild", chosen_color="blue")

    assert first == second
    assert before_counts == (len(players[0].hand), len(game.discard_pile), game.current_color, game.current_player_id)


def test_wild_draw_four_opens_challenge_prompt_and_duplicate_play_has_no_side_effect():
    room, players, game = make_started_room()
    wild_draw_four = card("uno_wild_draw_four")
    players[0].hand = [wild_draw_four, card("uno_green_9")]
    game.deck = [card("uno_blue_1"), card("uno_green_2"), card("uno_yellow_3"), card("uno_red_4")]

    first = play(room, players[0], wild_draw_four, action_id="same-wdf", chosen_color="blue")
    before_counts = (
        len(players[0].hand),
        len(players[1].hand),
        len(game.deck),
        len(game.discard_pile),
        len(game.effect_queue),
        game.current_player_id,
        game.current_color,
    )
    second = play(room, players[0], wild_draw_four, action_id="same-wdf", chosen_color="green")

    assert first == second
    assert game.current_prompt is not None
    assert game.current_prompt.kind == PromptKind.WILD_DRAW_FOUR_CHALLENGE
    assert before_counts == (
        len(players[0].hand),
        len(players[1].hand),
        len(game.deck),
        len(game.discard_pile),
        len(game.effect_queue),
        game.current_player_id,
        game.current_color,
    )


def test_wild_draw_four_decline_challenge_draws_four_and_skips_target():
    room, players, game = make_started_room()
    wild_draw_four = card("uno_wild_draw_four")
    players[0].hand = [wild_draw_four, card("uno_green_9")]
    game.deck = [card("uno_blue_1"), card("uno_green_2"), card("uno_yellow_3"), card("uno_red_4")]
    play(room, players[0], wild_draw_four, action_id="wdf-decline-play", chosen_color="blue")
    prompt_id = game.current_prompt.prompt_id

    result = respond(room, players[1], prompt_id, "decline_challenge", action_id="wdf-decline")

    assert result["challenge_result"] == "declined"
    assert result["penalty_player_id"] == players[1].player_id
    assert result["drawn_count"] == 4
    assert len(players[1].hand) == 4
    assert game.current_player_id == players[2].player_id
    assert game.current_prompt is None


def test_wild_draw_four_challenge_success_and_failure_paths():
    room, players, game = make_started_room()
    illegal_wdf = card("uno_wild_draw_four")
    players[0].hand = [illegal_wdf, card("uno_red_7")]
    game.deck = [card("uno_blue_1"), card("uno_green_2"), card("uno_yellow_3"), card("uno_red_4")]
    play(room, players[0], illegal_wdf, action_id="illegal-wdf-play", chosen_color="blue")

    result = respond(room, players[1], game.current_prompt.prompt_id, "challenge", action_id="challenge-success")

    assert result["challenge_result"] == "illegal"
    assert result["penalty_player_id"] == players[0].player_id
    assert result["drawn_count"] == 4
    assert len(players[0].hand) == 5
    assert len(players[1].hand) == 0
    assert game.current_player_id == players[1].player_id

    room, players, game = make_started_room()
    legal_wdf = card("uno_wild_draw_four")
    players[0].hand = [legal_wdf, card("uno_green_9")]
    game.deck = [
        card("uno_blue_1"),
        card("uno_green_2"),
        card("uno_yellow_3"),
        card("uno_red_4"),
        card("uno_blue_5"),
        card("uno_green_6"),
    ]
    play(room, players[0], legal_wdf, action_id="legal-wdf-play", chosen_color="blue")

    result = respond(room, players[1], game.current_prompt.prompt_id, "challenge", action_id="challenge-fail")

    assert result["challenge_result"] == "legal"
    assert result["penalty_player_id"] == players[1].player_id
    assert result["drawn_count"] == 6
    assert len(players[1].hand) == 6
    assert game.current_player_id == players[2].player_id


def test_wild_draw_four_prompt_rejects_wrong_responder_reuse_and_hides_hands():
    room, players, game = make_started_room()
    wild_draw_four = card("uno_wild_draw_four")
    players[0].hand = [wild_draw_four, card("uno_red_7")]
    game.deck = [card("uno_blue_1"), card("uno_green_2"), card("uno_yellow_3"), card("uno_red_4")]
    play(room, players[0], wild_draw_four, action_id="wdf-private-play", chosen_color="blue")
    prompt_id = game.current_prompt.prompt_id

    with pytest.raises(CommandError) as wrong_player:
        respond(room, players[2], prompt_id, "challenge", action_id="wrong-challenger")
    assert wrong_player.value.code == "NOT_PROMPT_RESPONDER"
    assert_no_other_hand_leak(room)

    respond(room, players[1], prompt_id, "decline_challenge", action_id="first-wdf-response")
    with pytest.raises(CommandError) as reused:
        respond(room, players[1], prompt_id, "challenge", action_id="second-wdf-response")
    assert reused.value.code == "NO_ACTIVE_PROMPT"
