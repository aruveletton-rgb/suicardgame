from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from time import sleep

from fastapi.testclient import TestClient

import backend.app.main as main
from backend.app.domain.room import new_player as make_player


def clear_rooms() -> None:
    with main.rooms_lock:
        main.rooms.clear()


def test_concurrent_join_allocates_unique_seats(monkeypatch):
    clear_rooms()

    def slow_new_player(nickname: str, seat_index: int, *, is_host: bool = False, avatar_id: str = "default"):
        sleep(0.02)
        return make_player(nickname, seat_index, is_host=is_host, avatar_id=avatar_id)

    monkeypatch.setattr(main, "new_player", slow_new_player)
    client = TestClient(main.app)
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    room_code = host["room_code"]

    def join_player(index: int):
        response = client.post(f"/api/v1/rooms/{room_code}/join", json={"nickname": f"p{index}"})
        return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=9) as executor:
        results = list(executor.map(join_player, range(1, 10)))

    successful = [body for status, body in results if status == 200]
    rejected = [body for status, body in results if status == 409]
    assert len(successful) == 4
    assert len(rejected) == 5
    assert all(body["detail"] == "ROOM_FULL" for body in rejected)
    seats = [host["seat_index"], *[body["seat_index"] for body in successful]]
    assert sorted(seats) == list(range(5))

    full_response = client.post(f"/api/v1/rooms/{room_code}/join", json={"nickname": "overflow"})
    assert full_response.status_code == 409
    assert full_response.json()["detail"] == "ROOM_FULL"
    clear_rooms()


def test_room_websocket_sends_public_snapshot_and_pong():
    clear_rooms()
    client = TestClient(main.app)
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    room_code = host["room_code"]

    with client.websocket_connect(f"/api/v1/rooms/{room_code}/ws?player_id={host['player_id']}&session_id={host['session_id']}") as websocket:
        snapshot = websocket.receive_json()
        assert snapshot["event"] == "snapshot"
        assert websocket.receive_json()["event"] == "private_snapshot"
        assert snapshot["room_code"] == room_code
        assert snapshot["state"]["players"][0]["hand_count"] == 0
        assert "hand" not in snapshot["state"]["players"][0]

        websocket.send_json({"event": "ping"})
        pong = websocket.receive_json()
        assert pong["event"] == "pong"
        assert pong["state_version"] == snapshot["state_version"]

        websocket.send_json({"event": "get_state"})
        latest = websocket.receive_json()
        assert latest["event"] == "snapshot"
        assert latest["state"]["phase"] == "LOBBY"
    clear_rooms()


def test_room_websocket_receives_state_patch_after_join():
    clear_rooms()
    client = TestClient(main.app)
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    room_code = host["room_code"]

    with client.websocket_connect(f"/api/v1/rooms/{room_code}/ws?player_id={host['player_id']}&session_id={host['session_id']}") as websocket:
        initial = websocket.receive_json()
        assert initial["event"] == "snapshot"
        assert websocket.receive_json()["event"] == "private_snapshot"
        assert len(initial["state"]["players"]) == 1

        join_response = client.post(f"/api/v1/rooms/{room_code}/join", json={"nickname": "guest"})
        assert join_response.status_code == 200

        patch = websocket.receive_json()
        assert patch["event"] == "state_patch"
        assert patch["state_version"] == initial["state_version"] + 1
        assert [player["seat_index"] for player in patch["state"]["players"]] == [0, 1]
        assert all("hand" not in player for player in patch["state"]["players"])
    clear_rooms()


def test_room_websocket_command_returns_result_and_broadcasts_patch():
    clear_rooms()
    client = TestClient(main.app)
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    room_code = host["room_code"]

    with client.websocket_connect(f"/api/v1/rooms/{room_code}/ws?player_id={host['player_id']}&session_id={host['session_id']}") as websocket:
        snapshot = websocket.receive_json()
        assert snapshot["event"] == "snapshot"
        assert websocket.receive_json()["event"] == "private_snapshot"

        websocket.send_json({"event": "command", "action_id": "ws-ready-1", "command_type": "READY", "payload": {"ready": True}})
        result = websocket.receive_json()
        assert result["event"] == "command_result"
        assert result["action_id"] == "ws-ready-1"
        assert result["result"]["ready"] is True

        patch = websocket.receive_json()
        assert patch["event"] == "state_patch"
        assert patch["state"]["players"][0]["ready"] is True
        assert "hand" not in patch["state"]["players"][0]
    clear_rooms()


def test_room_websocket_command_validation_error():
    clear_rooms()
    client = TestClient(main.app)
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    room_code = host["room_code"]

    with client.websocket_connect(f"/api/v1/rooms/{room_code}/ws?player_id={host['player_id']}&session_id={host['session_id']}") as websocket:
        assert websocket.receive_json()["event"] == "snapshot"
        assert websocket.receive_json()["event"] == "private_snapshot"
        websocket.send_json({"event": "command", "action_id": "bad-command", "payload": {}})
        error = websocket.receive_json()
        assert error["event"] == "error"
        assert error["error"] == "COMMAND_TYPE_REQUIRED"
        assert error["action_id"] == "bad-command"
    clear_rooms()
