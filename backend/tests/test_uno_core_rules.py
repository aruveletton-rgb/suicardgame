from __future__ import annotations

import pytest

from backend.app.domain.cards import build_core_uno_deck
from backend.app.domain.room import Room, new_player
from backend.app.engine.command_handler import Command, CommandError, process_command
from backend.app.engine.invariants import assert_room_invariants


def card(asset_key: str):
    return next(item for item in build_core_uno_deck() if item.asset_key == asset_key)


def make_started_room(player_count: int = 3):
    host = new_player("host", 0, is_host=True)
    players = [host]
    for index in range(1, player_count):
        players.append(new_player(f"p{index}", index))
    room = Room(room_id="CORE01", host_player_id=host.player_id, players=players)
    process_command(
        room,
        Command(
            action_id="start",
            room_id=room.room_id,
            player_id=host.player_id,
            command_type="START_GAME",
            payload={"seed": 101},
        ),
    )
    return room, players, room.active_game


def set_state(room: Room, players, *, current_index=0, hand=None, discard=None, deck=None):
    game = room.active_game
    assert game is not None
    for player in players:
        player.hand = []
    players[current_index].hand = list(hand or [])
    game.current_player_id = players[current_index].player_id
    game.discard_pile = list(discard or [card("uno_red_5")])
    game.current_color = game.discard_pile[-1].color
    game.deck = list(deck or [])
    game.current_prompt = None
    game.effect_queue = []
    game.direction = 1
    assert_room_invariants(room)
    return game


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


def draw(room: Room, player, *, action_id: str):
    return process_command(
        room,
        Command(
            action_id=action_id,
            room_id=room.room_id,
            player_id=player.player_id,
            command_type="DRAW_CARD",
        ),
    )


def compact_state(room: Room):
    game = room.active_game
    assert game is not None
    return (
        room.phase,
        room.state_version,
        game.current_player_id,
        game.direction,
        game.current_color,
        len(game.deck),
        len(game.discard_pile),
        tuple(len(player.hand) for player in room.seats_in_order()),
    )


def assert_compact_state_unchanged(before, after) -> None:
    if before != after:
        raise AssertionError("command unexpectedly changed compact game state")


def test_color_and_number_matches_update_hand_discard_and_turn():
    room, players, _game = make_started_room()
    red_7 = card("uno_red_7")
    game = set_state(room, players, hand=[red_7, card("uno_blue_9")])

    result = play(room, players[0], red_7, action_id="play-color-match")

    assert result["ok"] is True
    assert len(players[0].hand) == 1
    assert game.discard_pile[-1] is red_7
    assert game.current_color == red_7.color
    assert game.current_player_id == players[1].player_id

    blue_5 = card("uno_blue_5")
    game = set_state(room, players, hand=[blue_5, card("uno_green_9")])

    result = play(room, players[0], blue_5, action_id="play-number-match")

    assert result["ok"] is True
    assert len(players[0].hand) == 1
    assert game.discard_pile[-1] is blue_5
    assert game.current_color == blue_5.color
    assert game.current_player_id == players[1].player_id


def test_illegal_play_wrong_turn_and_missing_card_are_rejected_without_mutation():
    room, players, _game = make_started_room()
    wrong_turn_card = card("uno_red_7")
    players[1].hand = [wrong_turn_card]
    before = compact_state(room)

    with pytest.raises(CommandError) as wrong_turn:
        play(room, players[1], wrong_turn_card, action_id="wrong-turn")

    assert wrong_turn.value.code == "NOT_YOUR_TURN"
    assert_compact_state_unchanged(before, compact_state(room))

    illegal = card("uno_green_9")
    set_state(room, players, hand=[illegal, card("uno_blue_1")])
    before = compact_state(room)

    with pytest.raises(CommandError) as illegal_play:
        play(room, players[0], illegal, action_id="illegal-play")

    assert illegal_play.value.code == "ILLEGAL_PLAY"
    assert_compact_state_unchanged(before, compact_state(room))

    missing = card("uno_red_9")
    before = compact_state(room)

    with pytest.raises(CommandError) as missing_card:
        play(room, players[0], missing, action_id="missing-card")

    assert missing_card.value.code == "CARD_NOT_IN_HAND"
    assert_compact_state_unchanged(before, compact_state(room))


def test_draw_card_current_player_only_and_draw_ends_turn():
    room, players, _game = make_started_room()
    drawn = card("uno_blue_1")
    game = set_state(room, players, hand=[], deck=[drawn])
    before = compact_state(room)

    with pytest.raises(CommandError) as wrong_player:
        draw(room, players[1], action_id="wrong-player-draw")

    assert wrong_player.value.code == "NOT_YOUR_TURN"
    assert_compact_state_unchanged(before, compact_state(room))

    result = draw(room, players[0], action_id="current-player-draw")

    assert result["drawn_count"] == 1
    assert len(players[0].hand) == 1
    assert len(game.deck) == 0
    assert game.current_player_id == players[1].player_id


def test_skip_reverse_draw_two_effects_and_illegal_action_rejection():
    room, players, _game = make_started_room()
    skip = card("uno_red_skip")
    game = set_state(room, players, hand=[skip, card("uno_blue_9")])
    play(room, players[0], skip, action_id="skip-three")
    assert game.current_player_id == players[2].player_id

    two_player_room, two_players, _ = make_started_room(2)
    two_skip = card("uno_red_skip")
    two_game = set_state(two_player_room, two_players, hand=[two_skip, card("uno_blue_9")])
    play(two_player_room, two_players[0], two_skip, action_id="skip-two")
    assert two_game.current_player_id == two_players[0].player_id

    reverse = card("uno_red_reverse")
    game = set_state(room, players, hand=[reverse, card("uno_blue_9")])
    play(room, players[0], reverse, action_id="reverse-three")
    assert game.direction == -1
    assert game.current_player_id == players[2].player_id

    two_reverse = card("uno_red_reverse")
    two_game = set_state(two_player_room, two_players, hand=[two_reverse, card("uno_blue_9")])
    play(two_player_room, two_players[0], two_reverse, action_id="reverse-two")
    assert two_game.direction == -1
    assert two_game.current_player_id == two_players[0].player_id

    draw_two = card("uno_red_draw_two")
    game = set_state(
        room,
        players,
        hand=[draw_two, card("uno_blue_9")],
        deck=[card("uno_blue_1"), card("uno_green_2")],
    )
    play(room, players[0], draw_two, action_id="draw-two")
    assert len(players[1].hand) == 2
    assert len(game.deck) == 0
    assert game.current_player_id == players[2].player_id

    illegal_skip = card("uno_red_skip")
    set_state(room, players, hand=[illegal_skip, card("uno_yellow_1")], discard=[card("uno_blue_5")])

    with pytest.raises(CommandError) as rejected:
        play(room, players[0], illegal_skip, action_id="illegal-skip")

    assert rejected.value.code == "ILLEGAL_PLAY"
