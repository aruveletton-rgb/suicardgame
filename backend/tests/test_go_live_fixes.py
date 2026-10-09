from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

import backend.app.main as main
from backend.tests.ready_helpers import decline_has_sui_prompts, ready_all_http
from backend.app.domain.cards import Card, SPECIAL_BY_KIND, build_core_uno_deck
from backend.app.engine.special_effects import expire_special_prompt


def clear_rooms() -> None:
    with main.rooms_lock:
        main.rooms.clear()


def auth_header(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['session_id']}"}


def uno(asset_key: str):
    return next(item for item in build_core_uno_deck() if item.asset_key == asset_key)


def special(kind: str) -> Card:
    return Card.from_spec(SPECIAL_BY_KIND[kind])


def command(client: TestClient, room_code: str, session: dict, player_id: str, command_type: str, payload=None, action_id="cmd"):
    return client.post(
        f"/api/v1/rooms/{room_code}/commands",
        json={"action_id": action_id, "player_id": player_id, "command_type": command_type, "payload": payload or {}},
        headers=auth_header(session),
    )


def make_started_room(client: TestClient, player_count: int = 2):
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    players = [host]
    for index in range(1, player_count):
        players.append(client.post(f"/api/v1/rooms/{host['room_code']}/join", json={"nickname": f"p{index}"}).json())
    ready_all_http(client, host["room_code"], players)
    start = command(client, host["room_code"], host, host["player_id"], "START_GAME", {"seed": 806}, "start")
    assert start.status_code == 200
    return host["room_code"], host, players


# ---------------------------------------------------------------------------
# 一次性换设备恢复码
# ---------------------------------------------------------------------------

def test_reconnect_returns_new_token_and_old_token_becomes_invalid():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, _guest = make_started_room(client)
    old_token = host["reconnect_token"]

    first = client.post(
        f"/api/v1/rooms/{room_code}/reconnect",
        json={"player_id": host["player_id"], "reconnect_token": old_token},
    )
    assert first.status_code == 200
    body = first.json()
    new_token = body["reconnect_token"]
    assert new_token and new_token != old_token

    # 旧 token 已失效，不能再次用于顶替
    stale = client.post(
        f"/api/v1/rooms/{room_code}/reconnect",
        json={"player_id": host["player_id"], "reconnect_token": old_token},
    )
    assert stale.status_code == 403
    assert stale.json()["detail"]["error"] == "RECONNECT_FAILED"

    # 新 token 可正常重连
    again = client.post(
        f"/api/v1/rooms/{room_code}/reconnect",
        json={"player_id": host["player_id"], "reconnect_token": new_token},
    )
    assert again.status_code == 200
    assert again.json()["reconnect_token"] != new_token
    clear_rooms()


# ---------------------------------------------------------------------------
# 同一玩家多连接计数
# ---------------------------------------------------------------------------

class FakeWebSocket:
    def __init__(self):
        self.closed = False


def test_hub_disconnect_reports_remaining_connection_for_same_player():
    clear_rooms()
    hub = main.WebSocketHub()
    ws1 = FakeWebSocket()
    ws2 = FakeWebSocket()

    async def exercise():
        await hub.connect("ROOM1", ws1, "playerA")
        await hub.connect("ROOM1", ws2, "playerA")
        still = await hub.disconnect("ROOM1", ws1)
        assert still is True  # 还有 ws2 属于 playerA
        last = await hub.disconnect("ROOM1", ws2)
        assert last is False  # 已无连接

    asyncio.run(exercise())
    clear_rooms()


def test_hub_disconnect_different_player_does_not_count():
    clear_rooms()
    hub = main.WebSocketHub()
    ws_a = FakeWebSocket()
    ws_b = FakeWebSocket()

    async def exercise():
        await hub.connect("ROOM1", ws_a, "playerA")
        await hub.connect("ROOM1", ws_b, "playerB")
        still = await hub.disconnect("ROOM1", ws_a)
        assert still is False  # ws_b 属于 playerB，非 playerA

    asyncio.run(exercise())
    clear_rooms()


# ---------------------------------------------------------------------------
# 断线宽限：特殊牌 prompt 超时默认动作推进
# ---------------------------------------------------------------------------

def test_expire_ji_prompt_advances_turn_and_closes_effect():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, _players = make_started_room(client, 2)
    ji = special("ji")
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        room.player(host["player_id"]).hand = [ji, uno("uno_red_1")]
        game.current_player_id = host["player_id"]
        game.discard_pile = [uno("uno_red_5")]
        game.current_color = game.discard_pile[-1].color
        game.deck = [uno("uno_blue_1"), uno("uno_green_2"), uno("uno_yellow_3")]
        game.current_prompt = None
        game.effect_queue = []

    resp = command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": ji.card_id, "chosen_color": "red"}, "ji-activate")
    assert resp.status_code == 200
    assert resp.json()["pending"] is True

    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game.current_prompt is not None
        prompt_id = game.current_prompt.prompt_id
        deadline = game.current_prompt.deadline_at
        before_current = game.current_player_id

    changed = expire_special_prompt(room, prompt_id, now=deadline + 1)
    assert changed is True
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        decline_has_sui_prompts(room, action_prefix="decline-after-expired-ji")
        assert game.current_prompt is None
        assert game.effect_queue == []
        assert game.current_player_id != before_current  # 回合已推进
    clear_rooms()


def test_expire_special_prompt_before_deadline_is_noop():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, _players = make_started_room(client, 2)
    ji = special("ji")
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        room.player(host["player_id"]).hand = [ji, uno("uno_red_1")]
        game.current_player_id = host["player_id"]
        game.discard_pile = [uno("uno_red_5")]
        game.current_color = game.discard_pile[-1].color
        game.deck = [uno("uno_blue_1"), uno("uno_green_2")]
        game.current_prompt = None
        game.effect_queue = []

    command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": ji.card_id, "chosen_color": "red"}, "ji-activate")
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        prompt_id = game.current_prompt.prompt_id
        deadline = game.current_prompt.deadline_at

    changed = expire_special_prompt(room, prompt_id, now=deadline - 1)
    assert changed is False
    with main.rooms_lock:
        room = main.rooms[room_code]
        assert room.active_game.current_prompt is not None  # 未超时，prompt 仍在
    clear_rooms()


# ---------------------------------------------------------------------------
# EMPTY_DECK：洗混限一次 + 再次空摸 0 张 + 按手牌数判胜负
# ---------------------------------------------------------------------------

def test_reshuffle_discard_happens_at_most_once_per_game():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, _players = make_started_room(client, 2)
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        # 构造 deck 空、discard 有可洗牌（>1 张）
        host_p = room.player(host["player_id"])
        host_p.hand = []
        game.deck = []
        game.discard_pile = [uno("uno_red_5"), uno("uno_blue_3"), uno("uno_green_2")]
        game.current_color = game.discard_pile[-1].color
        game.current_player_id = host["player_id"]
        game.current_prompt = None
        game.effect_queue = []

    # 第一次摸牌触发洗混
    resp1 = command(client, room_code, host, host["player_id"], "DRAW_CARD", {}, "draw-1")
    assert resp1.status_code == 200
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game.reshuffle_count == 1
        assert len(game.discard_pile) == 1  # 只剩顶牌
        assert len(room.player(host["player_id"]).hand) == 2

    clear_rooms()


def test_draw_returns_zero_when_deck_fully_exhausted_then_finish_by_hand_count():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client, 2)
    guest = players[1]
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        # host 手牌 0 张，guest 手牌 1 张；牌库彻底空，reshuffle 已用尽
        room.player(host["player_id"]).hand = []
        room.player(guest["player_id"]).hand = [uno("uno_red_7")]
        game.deck = []
        game.discard_pile = [uno("uno_red_5")]  # 只剩顶牌
        game.reshuffle_count = 1
        game.current_color = game.discard_pile[-1].color
        game.current_player_id = host["player_id"]
        game.current_prompt = None
        game.effect_queue = []

    resp = command(client, room_code, host, host["player_id"], "DRAW_CARD", {}, "draw-exhausted")
    assert resp.status_code == 200
    body = resp.json()
    assert body["drawn_count"] == 0
    assert body["finished_by_deck_exhausted"] is True
    assert body["winner_player_id"] == host["player_id"]  # 手牌少者获胜

    with main.rooms_lock:
        room = main.rooms[room_code]
        assert room.phase.value == "ROUND_RESULT"
        assert room.active_game.status.value == "FINISHED"
    clear_rooms()

