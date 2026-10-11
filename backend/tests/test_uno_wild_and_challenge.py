import pytest

from backend.app.domain.cards import CardColor, build_core_uno_deck
from backend.app.domain.room import Room, new_player
from backend.app.engine.command_handler import Command, CommandError, process_command
from backend.tests.ready_helpers import ready_all


def card(asset_key):
    return next(item for item in build_core_uno_deck() if item.asset_key == asset_key)


def make_started_room():
    players = [new_player("host", 0, is_host=True), new_player("p1", 1), new_player("p2", 2)]
    room = Room(room_id="WILD01", host_player_id=players[0].player_id, players=players)
    ready_all(room)
    process_command(
        room,
        Command(
            action_id="start",
            room_id=room.room_id,
            player_id=players[0].player_id,
            command_type="START_GAME",
            payload={"seed": 202},
        ),
    )
    game = room.active_game
    assert game is not None
    for player in players:
        player.hand = []
    game.current_player_id = players[0].player_id
    game.discard_pile = [card("uno_red_5")]
    game.current_color = CardColor.RED
    game.current_prompt = None
    game.effect_queue = []
    game.direction = 1
    return room, players, game


def play(room, player, card_to_play, *, action_id, **payload):
    return process_command(
        room,
        Command(
            action_id=action_id,
            room_id=room.room_id,
            player_id=player.player_id,
            command_type="PLAY_CARD",
            payload={"card_id": card_to_play.card_id, **payload},
        ),
    )


def test_wild_requires_a_valid_color_and_sets_the_next_color():
    room, players, game = make_started_room()
    wild = card("uno_wild")
    players[0].hand = [wild, card("uno_red_9")]

    with pytest.raises(CommandError) as missing_color:
        play(room, players[0], wild, action_id="wild-missing-color")
    assert missing_color.value.code == "COLOR_REQUIRED"

    with pytest.raises(CommandError) as invalid_color:
        play(room, players[0], wild, action_id="wild-invalid-color", chosen_color="purple")
    assert invalid_color.value.code == "COLOR_REQUIRED"
    assert wild in players[0].hand
    assert game.current_player_id == players[0].player_id

    play(room, players[0], wild, action_id="wild-blue", chosen_color="blue")

    assert game.current_color == CardColor.BLUE
    assert game.current_player_id == players[1].player_id


def test_wild_action_id_replay_does_not_change_chosen_color_or_state():
    room, players, game = make_started_room()
    wild = card("uno_wild")
    players[0].hand = [wild, card("uno_red_9")]

    first = play(room, players[0], wild, action_id="same-wild", chosen_color="green")
    state = (room.state_version, len(players[0].hand), len(game.discard_pile), game.current_player_id)
    second = play(room, players[0], wild, action_id="same-wild", chosen_color="blue")

    assert second == first
    assert game.current_color == CardColor.GREEN
    assert state == (room.state_version, len(players[0].hand), len(game.discard_pile), game.current_player_id)


def test_wild_draw_four_draws_four_and_skips_the_affected_player():
    room, players, game = make_started_room()
    wild_draw_four = card("uno_wild_draw_four")
    players[0].hand = [wild_draw_four, card("uno_green_9")]
    game.deck = [card("uno_blue_1"), card("uno_green_2"), card("uno_yellow_3"), card("uno_red_4")]

    result = play(room, players[0], wild_draw_four, action_id="wdf-direct", chosen_color="blue")

    assert result["drawn_count"] == 0
    assert game.special_state["action_stack"] == {"kind": "wild_draw_four", "count": 4}
    assert game.current_player_id == players[1].player_id
    accepted = process_command(room, Command("wdf-accept", room.room_id, players[1].player_id, "ACCEPT_STACK"))
    assert accepted["drawn_count"] == 4
    assert len(players[1].hand) == 4
    assert game.current_prompt is None
    assert game.current_player_id == players[1].player_id


def test_wild_draw_four_is_illegal_with_a_matching_color_in_hand():
    room, players, game = make_started_room()
    wild_draw_four = card("uno_wild_draw_four")
    players[0].hand = [wild_draw_four, card("uno_red_7")]

    with pytest.raises(CommandError) as exc_info:
        play(room, players[0], wild_draw_four, action_id="wdf-illegal", chosen_color="blue")

    assert exc_info.value.code == "ILLEGAL_PLAY"
    assert wild_draw_four in players[0].hand
    assert game.current_player_id == players[0].player_id
