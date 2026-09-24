from __future__ import annotations

from time import time

import backend.app.main as main
from backend.app.domain.room import Room, new_player


def clear_rooms() -> None:
    with main.rooms_lock:
        main.rooms.clear()


def make_room(n: int = 2) -> Room:
    host = new_player("host", 0, is_host=True)
    players = [host]
    for index in range(1, n):
        players.append(new_player(f"p{index}", index))
    return Room(room_id="IDLE01", host_player_id=host.player_id, players=players)


def test_room_with_online_player_is_not_idle():
    clear_rooms()
    room = make_room(2)
    # host 在线，guest 离线很久
    room.players[0].online = True
    room.players[0].last_seen_at = time()
    room.players[1].online = False
    room.players[1].last_seen_at = time() - 999999
    assert main._room_is_idle(room, time()) is False
    clear_rooms()


def test_room_all_offline_recently_is_not_idle():
    clear_rooms()
    room = make_room(2)
    now = time()
    for p in room.players:
        p.online = False
        p.last_seen_at = now - 60  # 1 分钟前离线
    assert main._room_is_idle(room, now) is False
    clear_rooms()


def test_room_all_offline_beyond_timeout_is_idle():
    clear_rooms()
    room = make_room(2)
    now = time()
    for p in room.players:
        p.online = False
        p.last_seen_at = now - main.ROOM_IDLE_TIMEOUT_SECONDS - 1
    assert main._room_is_idle(room, now) is True
    clear_rooms()


def test_empty_room_is_idle():
    clear_rooms()
    room = Room(room_id="IDLE00", host_player_id="", players=[])
    assert main._room_is_idle(room, time()) is True
    clear_rooms()


def test_delete_room_removes_snapshot_file(tmp_path):
    from backend.app.repositories.json_store import JsonSnapshotStore
    store = JsonSnapshotStore(tmp_path)
    store.save("ABC123", {"room_id": "ABC123"})
    assert (tmp_path / "ABC123.json").exists()
    store.delete_room("ABC123")
    assert not (tmp_path / "ABC123.json").exists()
    # 删除不存在的房间不抛错
    store.delete_room("NOPE")
