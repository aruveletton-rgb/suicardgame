from __future__ import annotations

from fastapi.testclient import TestClient

import backend.app.main as main
from backend.app.engine.bot import choose_bot_command
from backend.app.engine.command_handler import Command, process_command


def auth(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['session_id']}"}


def test_host_can_add_and_remove_bots_in_lobby():
    with main.rooms_lock:
        main.rooms.clear()
    client = TestClient(main.app)
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    room_code = host["room_code"]

    added = client.post(
        f"/api/v1/rooms/{room_code}/bots",
        json={"count": 2},
        headers=auth(host),
    )
    assert added.status_code == 200
    assert added.json()["bot_count"] == 2
    state = client.get(f"/api/v1/rooms/{room_code}/state").json()
    assert [player["is_bot"] for player in state["players"]] == [False, True, True]
    assert all(player["ready"] for player in state["players"][1:])

    removed = client.post(
        f"/api/v1/rooms/{room_code}/bots",
        json={"count": 1},
        headers=auth(host),
    )
    assert removed.status_code == 200
    assert len(removed.json()["state"]["players"]) == 2


def test_bot_turn_uses_authoritative_command_path():
    host = main.new_player("host", 0, is_host=True)
    bot = main.new_player("机器人 1", 1, is_bot=True)
    room = main.Room(room_id="BOT001", host_player_id=host.player_id, players=[host, bot])
    for player in room.players:
        process_command(room, Command(f"ready-{player.player_id}", room.room_id, player.player_id, "READY", {"ready": True}))
    process_command(room, Command("start", room.room_id, host.player_id, "START_GAME", {"seed": 77}))
    assert room.active_game is not None
    room.active_game.current_player_id = bot.player_id

    command = choose_bot_command(room)
    assert command is not None
    assert command.player_id == bot.player_id
    assert command.command_type in {"PLAY_CARD", "ACTIVATE_SPECIAL", "DRAW_CARD"}
    before = room.state_version
    process_command(room, command)
    assert room.state_version > before


def test_all_bot_games_finish_without_rejected_commands():
    """回归：机器人不得因非法岁牌/年牌指令卡死（吃牌非下家、绩牌超限、规避牌辈分不足、误发动普通牌）。"""
    for game_no in range(12):
        count = 2 + game_no % 4
        players = [main.new_player(f"机器人 {i + 1}", i, is_host=(i == 0), is_bot=True) for i in range(count)]
        room = main.Room(room_id=f"SIM{game_no:03d}", host_player_id=players[0].player_id, players=players)
        for player in players:
            process_command(room, Command(f"ready-{player.player_id}", room.room_id, player.player_id, "READY", {"ready": True}))
        process_command(room, Command("start", room.room_id, players[0].player_id, "START_GAME", {"seed": 1000 + game_no}))
        for _ in range(3000):
            if room.active_game.status.name != "ACTIVE":
                break
            command = choose_bot_command(room)
            assert command is not None, f"game {game_no} stalled without a bot command"
            process_command(room, command)  # 任何 CommandError 都视为机器人决策缺陷
        assert room.active_game.status.name == "FINISHED", f"game {game_no} did not finish"
