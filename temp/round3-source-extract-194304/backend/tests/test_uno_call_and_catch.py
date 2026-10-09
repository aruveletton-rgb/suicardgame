import pytest

import backend.app.main as main
from backend.app.domain.cards import build_core_uno_deck
from backend.app.domain.room import Room, new_player
from backend.app.engine.command_handler import Command, CommandError, process_command
from backend.app.repositories.json_store import room_from_snapshot, room_to_snapshot
from backend.tests.ready_helpers import decline_has_sui_prompts, ready_all


def card(asset_key):
    return next(item for item in build_core_uno_deck() if item.asset_key == asset_key)


def make_started_room():
    host = new_player("host", 0, is_host=True)
    players = [host, new_player("p1", 1), new_player("p2", 2)]
    room = Room(room_id="UNO001", host_player_id=host.player_id, players=players)
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
            payload={"seed": 11},
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


def play_to_one_card(room, player, *, declare_uno=False):
    played = card("uno_red_7")
    player.hand = [played, card("uno_blue_9")]
    return process_command(
        room,
        Command(
            action_id=f"play-{played.card_id}",
            room_id=room.room_id,
            player_id=player.player_id,
            command_type="PLAY_CARD",
            payload={"card_id": played.card_id, "declare_uno": declare_uno},
        ),
    )


def catch_uno(room, catcher, target, action_id="catch"):
    return process_command(
        room,
        Command(
            action_id=action_id,
            room_id=room.room_id,
            player_id=catcher.player_id,
            command_type="CATCH_UNO",
            payload={"target_player_id": target.player_id},
        ),
    )


def test_undeclared_player_can_be_caught_and_draws_two():
    room, players, game = make_started_room()
    game.deck = [card("uno_green_1"), card("uno_yellow_2")]
    play_result = play_to_one_card(room, players[0])

    assert play_result["uno_pending_player_id"] == players[0].player_id
    assert game.uno_pending_player_id == players[0].player_id

    result = catch_uno(room, players[1], players[0])

    assert result["caught"] is True
    assert result["penalty_count"] == 2
    assert len(players[0].hand) == 3
    assert game.uno_pending_player_id is None


def test_inline_uno_declaration_prevents_catch():
    room, players, game = make_started_room()
    game.deck = [card("uno_green_1"), card("uno_yellow_2")]
    result = play_to_one_card(room, players[0], declare_uno=True)

    assert result["uno_declared"] is True
    assert game.uno_pending_player_id is None

    with pytest.raises(CommandError) as exc_info:
        catch_uno(room, players[1], players[0])

    assert exc_info.value.code == "UNO_CATCH_INVALID"
    assert len(players[0].hand) == 1


def test_explicit_uno_declaration_closes_open_window():
    room, players, game = make_started_room()
    game.deck = [card("uno_green_1"), card("uno_yellow_2")]
    play_to_one_card(room, players[0])

    result = process_command(
        room,
        Command(
            action_id="declare-uno",
            room_id=room.room_id,
            player_id=players[0].player_id,
            command_type="DECLARE_UNO",
        ),
    )

    assert result["uno_declared"] is True
    assert game.uno_pending_player_id is None
    with pytest.raises(CommandError) as exc_info:
        catch_uno(room, players[1], players[0])
    assert exc_info.value.code == "UNO_CATCH_INVALID"


def test_other_player_cannot_declare_uno_for_pending_player():
    room, players, game = make_started_room()
    game.deck = [card("uno_green_1"), card("uno_yellow_2")]
    play_to_one_card(room, players[0])
    state_version = room.state_version

    with pytest.raises(CommandError) as exc_info:
        process_command(
            room,
            Command(
                action_id="declare-for-other",
                room_id=room.room_id,
                player_id=players[1].player_id,
                command_type="DECLARE_UNO",
            ),
        )

    assert exc_info.value.code == "UNO_DECLARE_INVALID"
    assert game.uno_pending_player_id == players[0].player_id
    assert room.state_version == state_version


def test_duplicate_uno_declare_action_is_idempotent():
    room, players, game = make_started_room()
    game.deck = [card("uno_green_1"), card("uno_yellow_2")]
    play_to_one_card(room, players[0])

    command = Command(
        action_id="same-declare",
        room_id=room.room_id,
        player_id=players[0].player_id,
        command_type="DECLARE_UNO",
    )
    first = process_command(room, command)
    state_version = room.state_version
    second = process_command(room, command)

    assert first == second
    assert game.uno_pending_player_id is None
    assert room.state_version == state_version


def test_reset_clears_uno_window_and_new_round_starts_clean():
    room, players, game = make_started_room()
    game.deck = [card("uno_green_1"), card("uno_yellow_2")]
    play_to_one_card(room, players[0])
    assert game.uno_pending_player_id == players[0].player_id

    reset = process_command(
        room,
        Command(
            action_id="reset-after-uno-window",
            room_id=room.room_id,
            player_id=players[0].player_id,
            command_type="RESET_ROOM",
        ),
    )
    assert reset["room_phase"] == "LOBBY"
    assert room.active_game is None
    assert all(not player.hand for player in players)

    ready_all(room, action_prefix="ready-after-uno-reset")
    process_command(
        room,
        Command(
            action_id="start-after-uno-reset",
            room_id=room.room_id,
            player_id=players[0].player_id,
            command_type="START_GAME",
            payload={"seed": 12},
        ),
    )
    assert room.active_game is not None
    assert room.active_game.uno_pending_player_id is None
    assert room.active_game.uno_catchable_by == []


def test_completed_next_player_action_closes_catch_window():
    room, players, game = make_started_room()
    game.deck = [card("uno_green_1"), card("uno_yellow_2"), card("uno_blue_3")]
    play_to_one_card(room, players[0])
    decline_has_sui_prompts(room, action_prefix="decline-before-next-action")

    process_command(
        room,
        Command(
            action_id="next-player-draw",
            room_id=room.room_id,
            player_id=players[1].player_id,
            command_type="DRAW_CARD",
        ),
    )

    assert game.uno_pending_player_id is None
    with pytest.raises(CommandError) as exc_info:
        catch_uno(room, players[2], players[0])
    assert exc_info.value.code == "UNO_CATCH_INVALID"
    assert len(players[0].hand) == 1


def test_invalid_catch_does_not_mutate_state():
    room, players, game = make_started_room()
    game.deck = [card("uno_green_1"), card("uno_yellow_2")]
    play_to_one_card(room, players[0])
    state_version = room.state_version
    hand_ids = [item.card_id for item in players[0].hand]

    with pytest.raises(CommandError) as exc_info:
        catch_uno(room, players[0], players[0], "self-catch")

    assert exc_info.value.code == "UNO_CATCH_INVALID"
    assert room.state_version == state_version
    assert [item.card_id for item in players[0].hand] == hand_ids
    assert game.uno_pending_player_id == players[0].player_id


def test_uno_pending_state_round_trips_and_is_player_scoped():
    room, players, game = make_started_room()
    game.deck = [card("uno_green_1"), card("uno_yellow_2")]
    play_to_one_card(room, players[0])

    restored = room_from_snapshot(room_to_snapshot(room))
    assert restored.active_game is not None
    assert restored.active_game.uno_pending_player_id == players[0].player_id
    assert restored.active_game.uno_catchable_by == [players[1].player_id, players[2].player_id]

    source_view = main._private_snapshot(room, players[0].player_id)
    catcher_view = main._private_snapshot(room, players[1].player_id)
    assert source_view["you"]["uno"]["must_declare"] is True
    assert source_view["you"]["uno"]["can_catch_player_id"] is None
    assert catcher_view["you"]["uno"]["must_declare"] is False
    assert catcher_view["you"]["uno"]["can_catch_player_id"] == players[0].player_id
