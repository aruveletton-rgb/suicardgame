from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import backend.app.main as main
from backend.app.domain.cards import Card, SPECIAL_BY_KIND, build_core_uno_deck
from backend.app.domain.room import GameStatus, Room, RoomPhase, new_player
from backend.app.engine.command_handler import Command, CommandError, process_command
from backend.app.engine.invariants import assert_room_invariants
from backend.tests.ready_helpers import ready_all, ready_all_http


def card(asset_key: str):
    return next(item for item in build_core_uno_deck() if item.asset_key == asset_key)


def make_started_room(player_count: int = 3):
    host = new_player("host", 0, is_host=True)
    players = [host]
    for index in range(1, player_count):
        players.append(new_player(f"p{index}", index))
    room = Room(room_id="END01", host_player_id=host.player_id, players=players)
    ready_all(room)
    process_command(
        room,
        Command(
            action_id="start",
            room_id=room.room_id,
            player_id=host.player_id,
            command_type="START_GAME",
            payload={"seed": 303},
        ),
    )
    return room, players, room.active_game


def set_state(room: Room, players, *, current_index=0, hands=None, discard=None, deck=None):
    game = room.active_game
    assert game is not None
    hands = hands or {}
    for index, player in enumerate(players):
        player.hand = list(hands.get(index, []))
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
        Command(action_id=action_id, room_id=room.room_id, player_id=player.player_id, command_type="DRAW_CARD"),
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


def clear_api_rooms() -> None:
    with main.rooms_lock:
        main.rooms.clear()


def assert_snapshot_privacy(room: Room) -> None:
    public_snapshot = main._public_snapshot(room)
    assert all("hand" not in player for player in public_snapshot["state"]["players"])
    public_strings = collect_strings(public_snapshot)
    for player in room.players:
        if public_strings & hand_ids(player):
            raise AssertionError("public snapshot exposed a private hand card")
    for viewer in room.players:
        private_snapshot = main._private_snapshot(room, viewer.player_id)
        assert all("hand" not in player for player in private_snapshot["state"]["players"])
        other_ids = set().union(*(hand_ids(player) for player in room.players if player.player_id != viewer.player_id))
        if collect_strings(private_snapshot) & other_ids:
            raise AssertionError("private snapshot exposed another player's hand")


def test_draw_reshuffles_discard_except_top_and_preserves_card_zones():
    room, players, game = make_started_room(2)
    top = card("uno_green_2")
    set_state(
        room,
        players,
        hands={0: []},
        deck=[],
        discard=[card("uno_red_5"), card("uno_blue_1"), top],
    )

    result = draw(room, players[0], action_id="draw-from-reshuffle")

    assert result["drawn_count"] == 1
    assert len(players[0].hand) == 1
    assert game.discard_pile == [top]
    assert len(game.deck) == 1
    assert_room_invariants(room)


def test_draw_with_empty_deck_and_no_recyclable_discard_finishes_by_hand_count():
    room, players, game = make_started_room(2)
    top = card("uno_green_2")
    # players[0] 手牌 0 张，players[1] 保持开局 7 张
    set_state(room, players, hands={0: []}, deck=[], discard=[top])

    result = draw(room, players[0], action_id="draw-empty")

    # 摸不到牌且无合法动作 -> 按手牌数判胜负，手牌少者（players[0]）获胜
    assert result["ok"] is True
    assert result["drawn_count"] == 0
    assert result["finished_by_deck_exhausted"] is True
    assert room.phase == RoomPhase.ROUND_RESULT
    assert game.status == GameStatus.FINISHED
    assert game.winner_player_id == players[0].player_id


def test_last_card_finishes_game_sets_winner_and_blocks_more_core_actions():
    room, players, game = make_started_room(3)
    winning_card = card("uno_red_7")
    waiting_card = card("uno_blue_9")
    set_state(room, players, hands={0: [winning_card], 1: [waiting_card]}, deck=[card("uno_green_1")])

    result = play(room, players[0], winning_card, action_id="winning-play")

    assert result["ok"] is True
    assert room.phase == RoomPhase.ROUND_RESULT
    assert game.status == GameStatus.FINISHED
    assert game.winner_player_id == players[0].player_id

    with pytest.raises(CommandError) as draw_after_end:
        draw(room, players[1], action_id="draw-after-end")
    assert draw_after_end.value.code == "STALE_GAME_COMMAND"

    with pytest.raises(CommandError) as play_after_end:
        play(room, players[1], waiting_card, action_id="play-after-end")
    assert play_after_end.value.code == "STALE_GAME_COMMAND"
    assert_snapshot_privacy(room)


def test_reset_and_rematch_do_not_conflict_with_new_basic_round():
    room, players, _game = make_started_room(3)
    players[0].hand = [card("uno_red_7"), card("uno_blue_9")]

    reset = process_command(
        room,
        Command(action_id="reset", room_id=room.room_id, player_id=players[0].player_id, command_type="RESET_ROOM"),
    )
    assert reset["room_phase"] == "LOBBY"
    assert room.active_game is None
    assert [len(player.hand) for player in players] == [0, 0, 0]

    ready_all(room, action_prefix="ready-after-reset")
    start = process_command(
        room,
        Command(
            action_id="start-after-reset",
            room_id=room.room_id,
            player_id=players[0].player_id,
            command_type="START_GAME",
            payload={"seed": 304},
        ),
    )
    assert start["ok"] is True
    assert room.phase == RoomPhase.IN_GAME
    assert [len(player.hand) for player in players] == [7, 7, 7]

    winning_card = card("uno_red_7")
    set_state(room, players, hands={0: [winning_card]}, deck=[card("uno_green_1")])
    play(room, players[0], winning_card, action_id="finish-before-rematch")

    rematch = process_command(
        room,
        Command(action_id="rematch", room_id=room.room_id, player_id=players[0].player_id, command_type="REMATCH"),
    )
    assert rematch["room_phase"] == "LOBBY"
    assert room.active_game is None

    ready_all(room, action_prefix="ready-after-rematch")
    start = process_command(
        room,
        Command(
            action_id="start-after-rematch",
            room_id=room.room_id,
            player_id=players[0].player_id,
            command_type="START_GAME",
            payload={"seed": 305},
        ),
    )
    assert start["ok"] is True
    assert room.phase == RoomPhase.IN_GAME
    assert [len(player.hand) for player in players] == [7, 7, 7]


def test_public_private_snapshots_hide_other_hands_after_core_play():
    room, players, _game = make_started_room(3)
    played = card("uno_red_7")
    set_state(
        room,
        players,
        hands={0: [played, card("uno_blue_9")], 1: [card("uno_green_1")], 2: [card("uno_yellow_2")]},
        deck=[card("uno_blue_1")],
    )

    play(room, players[0], played, action_id="snapshot-core-play")

    assert_snapshot_privacy(room)


def test_websocket_snapshot_after_basic_play_matches_state_and_private_scope():
    clear_api_rooms()
    client = TestClient(main.app)
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    room_code = host["room_code"]
    guest = client.post(f"/api/v1/rooms/{room_code}/join", json={"nickname": "p1"}).json()
    ready_all_http(client, room_code, [host, guest])
    client.post(
        f"/api/v1/rooms/{room_code}/commands",
        json={
            "action_id": "start",
            "player_id": host["player_id"],
            "command_type": "START_GAME",
            "payload": {"seed": 306},
        },
        headers={"Authorization": f"Bearer {host['session_id']}"},
    )
    with main.rooms_lock:
        room = main.rooms[room_code]
        players = room.seats_in_order()
        played = card("uno_red_7")
        set_state(room, players, hands={0: [played, Card.from_spec(SPECIAL_BY_KIND["ji"])]}, deck=[card("uno_green_1")])

    with client.websocket_connect(
        f"/api/v1/rooms/{room_code}/ws?player_id={host['player_id']}&session_id={host['session_id']}"
    ) as websocket:
        assert websocket.receive_json()["event"] == "snapshot"
        assert websocket.receive_json()["event"] == "private_snapshot"
        websocket.send_json(
            {
                "event": "command",
                "action_id": "ws-basic-play",
                "command_type": "PLAY_CARD",
                "payload": {"card_id": played.card_id},
            }
        )
        command_result = websocket.receive_json()
        state_patch = websocket.receive_json()
        private_patch = websocket.receive_json()

    assert command_result["event"] == "command_result"
    assert state_patch["event"] == "state_patch"
    assert state_patch["state"]["phase"] == "IN_GAME"
    assert state_patch["state"]["active_game"]["current_player_id"] == host["player_id"]
    prompt = state_patch["state"]["active_game"]["pending_action"]
    assert prompt["kind"] == "HAS_SUI_CHALLENGE"
    assert [player["hand_count"] for player in state_patch["state"]["players"]] == [1, 0]
    assert private_patch["event"] == "private_snapshot"
    assert len(private_patch["you"]["hand"]) == 1
    assert all("hand" not in player for player in private_patch["state"]["players"])

    decline = client.post(
        f"/api/v1/rooms/{room_code}/commands",
        json={
            "action_id": "guest-declines-host-has-sui",
            "player_id": guest["player_id"],
            "command_type": "RESPOND_TO_PROMPT",
            "payload": {"prompt_id": prompt["prompt_id"], "response": "decline_challenge"},
        },
        headers={"Authorization": f"Bearer {guest['session_id']}"},
    )
    assert decline.status_code == 200
    with main.rooms_lock:
        assert main.rooms[room_code].active_game.current_player_id == guest["player_id"]
    clear_api_rooms()
