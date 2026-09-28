from __future__ import annotations

from fastapi.testclient import TestClient

import backend.app.main as main
from backend.app.repositories.json_store import JsonSnapshotStore


def clear_rooms() -> None:
    with main.rooms_lock:
        main.rooms.clear()


def auth_header(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['session_id']}"}


def test_started_room_survives_memory_reload(monkeypatch, tmp_path):
    store = JsonSnapshotStore(tmp_path)
    monkeypatch.setattr(main, "snapshot_store", store, raising=False)
    clear_rooms()
    client = TestClient(main.app)

    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    room_code = host["room_code"]
    guest = client.post(f"/api/v1/rooms/{room_code}/join", json={"nickname": "guest"}).json()
    client.post(
        f"/api/v1/rooms/{room_code}/commands",
        json={
            "action_id": "host-ready",
            "player_id": host["player_id"],
            "command_type": "READY",
            "payload": {"ready": True},
        },
        headers=auth_header(host),
    )
    client.post(
        f"/api/v1/rooms/{room_code}/commands",
        json={
            "action_id": "guest-ready",
            "player_id": guest["player_id"],
            "command_type": "READY",
            "payload": {"ready": True},
        },
        headers=auth_header(guest),
    )
    start = client.post(
        f"/api/v1/rooms/{room_code}/commands",
        json={
            "action_id": "start",
            "player_id": host["player_id"],
            "command_type": "START_GAME",
            "payload": {"seed": 17},
        },
        headers=auth_header(host),
    )
    assert start.status_code == 200
    game = start.json()

    assert store.path_for_room(room_code).exists()

    clear_rooms()
    main.load_rooms_from_store()

    state = client.get(f"/api/v1/rooms/{room_code}/state")
    assert state.status_code == 200
    public_state = state.json()
    assert public_state["phase"] == "IN_GAME"
    assert public_state["active_game"]["game_id"] == game["game_id"]
    assert public_state["active_game"]["game_epoch"] == game["game_epoch"]
    assert [player["hand_count"] for player in public_state["players"]] == [7, 7]
    assert all("hand" not in player for player in public_state["players"])

    reconnect = client.post(
        f"/api/v1/rooms/{room_code}/reconnect",
        json={"player_id": host["player_id"], "reconnect_token": host["reconnect_token"]},
    )
    assert reconnect.status_code == 200
    private_snapshot = reconnect.json()["private_snapshot"]
    assert private_snapshot["you"]["player_id"] == host["player_id"]
    assert len(private_snapshot["you"]["hand"]) == 7
    assert all("hand" not in player for player in private_snapshot["state"]["players"])

    clear_rooms()


def test_websocket_command_state_survives_memory_reload(monkeypatch, tmp_path):
    store = JsonSnapshotStore(tmp_path)
    monkeypatch.setattr(main, "snapshot_store", store, raising=False)
    clear_rooms()
    client = TestClient(main.app)

    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    room_code = host["room_code"]
    with client.websocket_connect(f"/api/v1/rooms/{room_code}/ws?player_id={host['player_id']}&session_id={host['session_id']}") as websocket:
        assert websocket.receive_json()["event"] == "snapshot"
        assert websocket.receive_json()["event"] == "private_snapshot"
        websocket.send_json({"event": "command", "action_id": "ws-ready", "command_type": "READY", "payload": {"ready": True}})
        assert websocket.receive_json()["event"] == "command_result"
        assert websocket.receive_json()["event"] == "state_patch"

    clear_rooms()
    main.load_rooms_from_store()

    state = client.get(f"/api/v1/rooms/{room_code}/state")
    assert state.status_code == 200
    assert state.json()["players"][0]["ready"] is True

    clear_rooms()
