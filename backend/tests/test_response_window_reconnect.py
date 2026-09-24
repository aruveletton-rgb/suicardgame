from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app import main
from backend.app.engine.command_handler import expire_generic_response_window
from backend.tests.test_response_window_security import clear_rooms, command, make_started_room, open_window


def test_legal_responder_reconnect_restores_same_open_prompt(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.setenv("SUICARDGAME_DATA_DIR", f"/tmp/suicardgame-step8-reconnect-{uuid4().hex}")
    clear_rooms()
    client = TestClient(main.app)
    host, responder, _outsider = make_started_room(client)
    prompt_id = open_window(client, host, [responder["player_id"]])
    response = client.post(
        f"/api/v1/rooms/{host['room_code']}/reconnect",
        json={"player_id": responder["player_id"], "reconnect_token": responder["reconnect_token"]},
    )
    assert response.status_code == 200
    prompt = response.json()["private_snapshot"]["state"]["active_game"]["pending_action"]
    assert prompt["prompt_id"] == prompt_id
    assert prompt["status"] == "open"
    assert prompt["can_respond"] is True
    assert prompt["legal_responses"] == ["accept", "decline"]
    with main.rooms_lock:
        room = main.rooms[host["room_code"]]
        assert room.active_game.current_prompt.prompt_id == prompt_id
        assert room.active_game.last_prompt is None
    clear_rooms()


def test_non_responder_reconnect_never_receives_private_options(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.setenv("SUICARDGAME_DATA_DIR", f"/tmp/suicardgame-step8-reconnect-{uuid4().hex}")
    clear_rooms()
    client = TestClient(main.app)
    host, responder, outsider = make_started_room(client)
    private_option = "only_responder_knows"
    prompt_id = open_window(
        client,
        host,
        [responder["player_id"]],
        options={responder["player_id"]: [private_option, "decline"]},
    )
    response = client.post(
        f"/api/v1/rooms/{host['room_code']}/reconnect",
        json={"player_id": outsider["player_id"], "reconnect_token": outsider["reconnect_token"]},
    )
    assert response.status_code == 200
    prompt = response.json()["private_snapshot"]["state"]["active_game"]["pending_action"]
    assert prompt["prompt_id"] == prompt_id
    assert prompt["can_respond"] is False
    assert prompt["legal_responses"] == []
    assert private_option not in str(prompt)
    clear_rooms()


def test_resolved_prompt_reconnect_is_visible_only_as_non_actionable_status(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.setenv("SUICARDGAME_DATA_DIR", f"/tmp/suicardgame-step8-reconnect-{uuid4().hex}")
    clear_rooms()
    client = TestClient(main.app)
    host, responder, _outsider = make_started_room(client)
    prompt_id = open_window(client, host, [responder["player_id"]])
    settled = command(client, host["room_code"], responder, "RESPOND_TO_PROMPT", {"prompt_id": prompt_id, "response": "accept"})
    assert settled.status_code == 200
    response = client.post(
        f"/api/v1/rooms/{host['room_code']}/reconnect",
        json={"player_id": responder["player_id"], "reconnect_token": responder["reconnect_token"]},
    )
    assert response.status_code == 200
    prompt = response.json()["private_snapshot"]["state"]["active_game"]["pending_action"]
    assert prompt["prompt_id"] == prompt_id
    assert prompt["status"] == "resolved"
    assert prompt["can_respond"] is False
    assert prompt["legal_responses"] == []
    with main.rooms_lock:
        assert main.rooms[host["room_code"]].active_game.current_prompt is None
    clear_rooms()


def test_expired_prompt_reconnect_does_not_restore_action(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.setenv("SUICARDGAME_DATA_DIR", f"/tmp/suicardgame-step8-reconnect-{uuid4().hex}")
    clear_rooms()
    client = TestClient(main.app)
    host, responder, _outsider = make_started_room(client)
    prompt_id = open_window(client, host, [responder["player_id"]])
    with main.rooms_lock:
        room = main.rooms[host["room_code"]]
        deadline = room.active_game.current_prompt.deadline_at
        assert expire_generic_response_window(room, prompt_id, now=deadline + 1)
    response = client.post(
        f"/api/v1/rooms/{host['room_code']}/reconnect",
        json={"player_id": responder["player_id"], "reconnect_token": responder["reconnect_token"]},
    )
    prompt = response.json()["private_snapshot"]["state"]["active_game"]["pending_action"]
    assert prompt["status"] == "expired"
    assert prompt["can_respond"] is False
    assert prompt["legal_responses"] == []
    clear_rooms()
