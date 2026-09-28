from fastapi.testclient import TestClient

import backend.app.main as main


def _command(client: TestClient, room_code: str, session: dict, command_type: str, action_id: str, payload=None):
    return client.post(
        f"/api/v1/rooms/{room_code}/commands",
        json={
            "action_id": action_id,
            "player_id": session["player_id"],
            "command_type": command_type,
            "payload": payload or {},
        },
        headers={"Authorization": f"Bearer {session['session_id']}"},
    )


def test_sixth_player_is_rejected_and_fifth_player_can_join():
    with main.rooms_lock:
        main.rooms.clear()
    client = TestClient(main.app)
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    guests = [
        client.post(f"/api/v1/rooms/{host['room_code']}/join", json={"nickname": f"p{index}"})
        for index in range(1, 5)
    ]
    assert all(response.status_code == 200 for response in guests)
    sixth = client.post(f"/api/v1/rooms/{host['room_code']}/join", json={"nickname": "sixth"})
    assert sixth.status_code == 409
    assert sixth.json()["detail"] == "ROOM_FULL"


def test_start_requires_every_seated_player_to_be_ready():
    with main.rooms_lock:
        main.rooms.clear()
    client = TestClient(main.app)
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    guest = client.post(f"/api/v1/rooms/{host['room_code']}/join", json={"nickname": "guest"}).json()
    _command(client, host["room_code"], guest, "READY", "ready-guest", {"ready": True})
    blocked = _command(client, host["room_code"], host, "START_GAME", "start-blocked", {"seed": 1})
    assert blocked.status_code == 400
    assert blocked.json()["detail"]["error"] == "PLAYERS_NOT_READY"
    _command(client, host["room_code"], host, "READY", "ready-host", {"ready": True})
    started = _command(client, host["room_code"], host, "START_GAME", "start-ready", {"seed": 1})
    assert started.status_code == 200
