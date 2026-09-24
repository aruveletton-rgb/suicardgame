from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app import main


def clear_rooms() -> None:
    with main.rooms_lock:
        main.rooms.clear()


def command(client, room_code, session, command_type, payload=None, *, player_id=None, authorization=None, action_id=None):
    headers = {}
    token = session["session_id"] if authorization is None else authorization
    if token is not False:
        headers["Authorization"] = f"Bearer {token}"
    return client.post(
        f"/api/v1/rooms/{room_code}/commands",
        json={
            "action_id": action_id or uuid4().hex,
            "player_id": player_id or session["player_id"],
            "command_type": command_type,
            "payload": payload or {},
        },
        headers=headers,
    )


def make_started_room(client):
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    responder = client.post(f"/api/v1/rooms/{host['room_code']}/join", json={"nickname": "responder"}).json()
    outsider = client.post(f"/api/v1/rooms/{host['room_code']}/join", json={"nickname": "outsider"}).json()
    response = command(client, host["room_code"], host, "START_GAME", {"seed": 810}, action_id="start-security")
    assert response.status_code == 200
    return host, responder, outsider


def open_window(client, host, responder_ids, *, options=None):
    response = command(
        client,
        host["room_code"],
        host,
        "TEST_OPEN_RESPONSE_WINDOW",
        {
            "responder_ids": responder_ids,
            "resolution_policy": "first_wins",
            "timeout_seconds": 10,
            "private_options_by_responder": options or {},
        },
    )
    assert response.status_code == 200
    return response.json()["prompt_id"]


def test_legal_responder_succeeds_and_non_responder_is_rejected_without_mutation(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.setenv("SUICARDGAME_DATA_DIR", f"/tmp/suicardgame-step8-security-{uuid4().hex}")
    clear_rooms()
    client = TestClient(main.app)
    host, responder, outsider = make_started_room(client)
    prompt_id = open_window(client, host, [responder["player_id"]])
    with main.rooms_lock:
        room = main.rooms[host["room_code"]]
        before_version = room.state_version
        before_records = dict(room.active_game.current_prompt.response_records)
    rejected = command(client, host["room_code"], outsider, "RESPOND_TO_PROMPT", {"prompt_id": prompt_id, "response": "accept"})
    assert rejected.status_code == 400
    assert rejected.json()["detail"]["error"] == "NOT_PROMPT_RESPONDER"
    with main.rooms_lock:
        assert room.state_version == before_version
        assert room.active_game.current_prompt.response_records == before_records
    accepted = command(client, host["room_code"], responder, "RESPOND_TO_PROMPT", {"prompt_id": prompt_id, "response": "accept"})
    assert accepted.status_code == 200
    clear_rooms()


def test_player_id_spoof_missing_and_invalid_sessions_are_rejected(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.setenv("SUICARDGAME_DATA_DIR", f"/tmp/suicardgame-step8-security-{uuid4().hex}")
    clear_rooms()
    client = TestClient(main.app)
    host, responder, outsider = make_started_room(client)
    prompt_id = open_window(client, host, [responder["player_id"]])

    spoof = command(
        client,
        host["room_code"],
        outsider,
        "RESPOND_TO_PROMPT",
        {"prompt_id": prompt_id, "response": "accept"},
        player_id=responder["player_id"],
    )
    assert spoof.status_code == 403
    assert spoof.json()["detail"]["error"] == "AUTH_PLAYER_MISMATCH"
    missing = command(
        client,
        host["room_code"],
        responder,
        "RESPOND_TO_PROMPT",
        {"prompt_id": prompt_id, "response": "accept"},
        authorization=False,
    )
    assert missing.status_code == 401
    assert missing.json()["detail"]["error"] == "AUTH_REQUIRED"
    invalid = command(
        client,
        host["room_code"],
        responder,
        "RESPOND_TO_PROMPT",
        {"prompt_id": prompt_id, "response": "accept"},
        authorization="invalid-session",
    )
    assert invalid.status_code == 403
    assert invalid.json()["detail"]["error"] == "AUTH_FAILED"
    with main.rooms_lock:
        assert main.rooms[host["room_code"]].active_game.current_prompt.response_records == {}
    clear_rooms()


def test_fixture_is_production_blocked_host_only_and_requires_unique_tmp_dir(monkeypatch):
    clear_rooms()
    client = TestClient(main.app)
    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.setenv("SUICARDGAME_DATA_DIR", f"/tmp/suicardgame-step8-security-{uuid4().hex}")
    host, responder, outsider = make_started_room(client)
    payload = {
        "responder_ids": [responder["player_id"]],
        "resolution_policy": "first_wins",
        "timeout_seconds": 10,
    }
    non_host = command(client, host["room_code"], outsider, "TEST_OPEN_RESPONSE_WINDOW", payload)
    assert non_host.status_code == 400
    assert non_host.json()["detail"]["error"] == "HOST_REQUIRED"

    monkeypatch.setenv("TEST_MODE", "0")
    production = command(client, host["room_code"], host, "TEST_OPEN_RESPONSE_WINDOW", payload)
    assert production.status_code == 400
    assert production.json()["detail"]["error"] == "TEST_MODE_DISABLED"

    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.setenv("SUICARDGAME_DATA_DIR", "data/rooms")
    unsafe = command(client, host["room_code"], host, "TEST_OPEN_RESPONSE_WINDOW", payload)
    assert unsafe.status_code == 400
    assert unsafe.json()["detail"]["error"] == "TEST_DATA_DIR_UNSAFE"
    with main.rooms_lock:
        assert main.rooms[host["room_code"]].active_game.current_prompt is None
    clear_rooms()


def test_websocket_public_then_private_delivery_scopes_actionable_prompt(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.setenv("SUICARDGAME_DATA_DIR", f"/tmp/suicardgame-step8-security-{uuid4().hex}")
    clear_rooms()
    client = TestClient(main.app)
    host, responder, outsider = make_started_room(client)
    private_option = "responder_private"
    open_window(
        client,
        host,
        [responder["player_id"]],
        options={responder["player_id"]: [private_option, "decline"]},
    )

    with client.websocket_connect(
        f"/api/v1/rooms/{host['room_code']}/ws?player_id={responder['player_id']}&session_id={responder['session_id']}"
    ) as websocket:
        public_event = websocket.receive_json()
        private_event = websocket.receive_json()
    public_prompt = public_event["state"]["active_game"]["pending_action"]
    responder_prompt = private_event["state"]["active_game"]["pending_action"]
    assert public_prompt["can_respond"] is False
    assert public_prompt["legal_responses"] == []
    assert private_option not in str(public_prompt)
    assert responder_prompt["can_respond"] is True
    assert responder_prompt["legal_responses"] == [private_option, "decline"]

    with client.websocket_connect(
        f"/api/v1/rooms/{host['room_code']}/ws?player_id={outsider['player_id']}&session_id={outsider['session_id']}"
    ) as websocket:
        websocket.receive_json()
        outsider_private = websocket.receive_json()
    outsider_prompt = outsider_private["state"]["active_game"]["pending_action"]
    assert outsider_prompt["can_respond"] is False
    assert outsider_prompt["legal_responses"] == []
    assert private_option not in str(outsider_prompt)
    clear_rooms()
