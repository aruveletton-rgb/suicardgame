from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import backend.app.main as main


def clear_rooms() -> None:
    with main.rooms_lock:
        main.rooms.clear()


def auth_header(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['session_id']}"}


def make_started_two_player_room(client: TestClient):
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    room_code = host["room_code"]
    guest = client.post(f"/api/v1/rooms/{room_code}/join", json={"nickname": "guest"}).json()
    client.post(
        f"/api/v1/rooms/{room_code}/commands",
        json={"action_id": "host-ready", "player_id": host["player_id"], "command_type": "READY", "payload": {"ready": True}},
        headers=auth_header(host),
    )
    client.post(
        f"/api/v1/rooms/{room_code}/commands",
        json={"action_id": "guest-ready", "player_id": guest["player_id"], "command_type": "READY", "payload": {"ready": True}},
        headers=auth_header(guest),
    )
    start = client.post(
        f"/api/v1/rooms/{room_code}/commands",
        json={"action_id": "start", "player_id": host["player_id"], "command_type": "START_GAME", "payload": {"seed": 91}},
        headers=auth_header(host),
    )
    assert start.status_code == 200
    return room_code, host, guest


def test_reconnect_returns_private_snapshot_and_rotates_session():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, _guest = make_started_two_player_room(client)
    old_session_id = host["session_id"]

    response = client.post(
        f"/api/v1/rooms/{room_code}/reconnect",
        json={"player_id": host["player_id"], "reconnect_token": host["reconnect_token"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["player_id"] == host["player_id"]
    assert body["session_id"] != old_session_id
    # 一次性换设备恢复码：重连后轮换 token
    assert "reconnect_token" in body
    assert body["reconnect_token"] != host["reconnect_token"]

    private_snapshot = body["private_snapshot"]
    assert private_snapshot["event"] == "private_snapshot"
    assert private_snapshot["you"]["player_id"] == host["player_id"]
    assert private_snapshot["you"]["session_id"] == body["session_id"]
    assert len(private_snapshot["you"]["hand"]) == 7
    assert all("asset_key" in card for card in private_snapshot["you"]["hand"])
    assert all("hand" not in player for player in private_snapshot["state"]["players"])

    clear_rooms()


def test_reconnect_rejects_bad_token():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, _guest = make_started_two_player_room(client)

    response = client.post(
        f"/api/v1/rooms/{room_code}/reconnect",
        json={"player_id": host["player_id"], "reconnect_token": "wrong"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "RECONNECT_FAILED"
    clear_rooms()


def test_websocket_authenticated_private_snapshot_is_player_scoped():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, guest = make_started_two_player_room(client)
    host_session = client.post(
        f"/api/v1/rooms/{room_code}/reconnect",
        json={"player_id": host["player_id"], "reconnect_token": host["reconnect_token"]},
    ).json()["session_id"]
    guest_session = client.post(
        f"/api/v1/rooms/{room_code}/reconnect",
        json={"player_id": guest["player_id"], "reconnect_token": guest["reconnect_token"]},
    ).json()["session_id"]

    with client.websocket_connect(f"/api/v1/rooms/{room_code}/ws?player_id={host['player_id']}&session_id={host_session}") as host_ws:
        assert host_ws.receive_json()["event"] == "snapshot"
        host_private = host_ws.receive_json()

    with client.websocket_connect(f"/api/v1/rooms/{room_code}/ws?player_id={guest['player_id']}&session_id={guest_session}") as guest_ws:
        assert guest_ws.receive_json()["event"] == "snapshot"
        guest_private = guest_ws.receive_json()

    assert host_private["event"] == "private_snapshot"
    assert guest_private["event"] == "private_snapshot"
    assert host_private["you"]["player_id"] == host["player_id"]
    assert guest_private["you"]["player_id"] == guest["player_id"]
    host_hand = {card["card_id"] for card in host_private["you"]["hand"]}
    guest_hand = {card["card_id"] for card in guest_private["you"]["hand"]}
    assert len(host_hand) == 7
    assert len(guest_hand) == 7
    assert host_hand.isdisjoint(guest_hand)
    clear_rooms()


def test_websocket_missing_session_is_rejected():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, _guest = make_started_two_player_room(client)

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/api/v1/rooms/{room_code}/ws?player_id={host['player_id']}") as websocket:
            websocket.receive_json()

    clear_rooms()


def test_authenticated_websocket_broadcast_includes_private_snapshot():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, _guest = make_started_two_player_room(client)
    room = main.rooms[room_code]

    class FakeWebSocket:
        def __init__(self):
            self.messages = []

        async def send_json(self, payload):
            self.messages.append(payload)

    async def exercise_hub():
        websocket = FakeWebSocket()
        hub = main.WebSocketHub()
        await hub.connect(room_code, websocket, host["player_id"])
        await hub.broadcast_state_patch(room)
        return websocket.messages

    messages = asyncio.run(exercise_hub())

    assert [message["event"] for message in messages] == ["state_patch", "private_snapshot"]
    assert messages[1]["you"]["player_id"] == host["player_id"]
    assert len(messages[1]["you"]["hand"]) == 7
    clear_rooms()
