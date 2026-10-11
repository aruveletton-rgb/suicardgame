import pytest

from backend.app.domain.room import Room, new_player
from backend.app.engine.command_handler import Command, CommandError, process_command
from backend.app.domain.cards import build_core_uno_deck
from backend.tests.ready_helpers import ready_all


def card(asset_key):
    return next(item for item in build_core_uno_deck() if item.asset_key == asset_key)


def make_started_room():
    players = [
        new_player("host", 0, is_host=True),
        new_player("p1", 1),
        new_player("p2", 2),
    ]
    room = Room(room_id="WDF001", host_player_id=players[0].player_id, players=players)
    ready_all(room)
    process_command(
        room,
        Command(
            action_id="start",
            room_id=room.room_id,
            player_id=players[0].player_id,
            command_type="START_GAME",
            payload={"seed": 7},
        ),
    )
    game = room.active_game
    assert game is not None
    for player in players:
        player.hand = []
    game.current_player_id = players[0].player_id
    game.discard_pile = [card("uno_red_5")]
    game.current_color = game.discard_pile[-1].color
    game.current_prompt = None
    game.effect_queue = []
    return room, players, game


def test_wild_draw_four_draws_four_and_skips_the_affected_player():
    room, players, game = make_started_room()
    wild_draw_four = card("uno_wild_draw_four")
    players[0].hand = [wild_draw_four, card("uno_green_9")]
    game.deck = [
        card("uno_blue_1"),
        card("uno_green_2"),
        card("uno_yellow_3"),
        card("uno_red_4"),
    ]

    result = process_command(
        room,
        Command(
            action_id="play-wild-draw-four",
            room_id=room.room_id,
            player_id=players[0].player_id,
            command_type="PLAY_CARD",
            payload={"card_id": wild_draw_four.card_id, "chosen_color": "blue"},
        ),
    )

    assert result["drawn_count"] == 0
    assert game.special_state["action_stack"] == {"kind": "wild_draw_four", "count": 4}
    assert game.current_player_id == players[1].player_id
    accepted = process_command(room, Command("accept-wild-draw-four", room.room_id, players[1].player_id, "ACCEPT_STACK"))
    assert accepted["drawn_count"] == 4
    assert len(players[1].hand) == 4
    assert game.current_prompt is None
    assert game.effect_queue == []
    assert game.current_player_id == players[1].player_id


def test_wild_draw_four_is_rejected_when_source_has_the_current_color():
    room, players, game = make_started_room()
    wild_draw_four = card("uno_wild_draw_four")
    players[0].hand = [wild_draw_four, card("uno_red_9")]
    game.deck = [card("uno_blue_1")]

    with pytest.raises(CommandError) as exc_info:
        process_command(
            room,
            Command(
                action_id="illegal-wild-draw-four",
                room_id=room.room_id,
                player_id=players[0].player_id,
                command_type="PLAY_CARD",
                payload={"card_id": wild_draw_four.card_id, "chosen_color": "blue"},
            ),
        )

    assert exc_info.value.code == "ILLEGAL_PLAY"
    assert wild_draw_four in players[0].hand
    assert game.current_prompt is None
    assert game.current_player_id == players[0].player_id
