from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app import main
from backend.tests.test_response_window_security import clear_rooms, command, make_started_room, open_window


def test_public_summary_has_no_responder_identity_private_options_or_hands(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.setenv("SUICARDGAME_DATA_DIR", f"/tmp/suicardgame-step8-privacy-{uuid4().hex}")
    clear_rooms()
    client = TestClient(main.app)
    host, responder, outsider = make_started_room(client)
    private_option = "private_acceptance"
    open_window(
        client,
        host,
        [responder["player_id"]],
        options={responder["player_id"]: [private_option, "decline"]},
    )
    public = client.get(f"/api/v1/rooms/{host['room_code']}/state").json()
    prompt = public["active_game"]["pending_action"]
    assert "responder_ids" not in prompt
    assert prompt["can_respond"] is False
    assert prompt["legal_responses"] == []
    assert prompt["default_action"] is None
    assert private_option not in str(prompt)
    assert all("hand" not in player for player in public["players"])
    assert responder["player_id"] not in str(prompt)
    assert outsider["player_id"] not in str(prompt)
    clear_rooms()


def test_each_private_snapshot_contains_only_its_own_options(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.setenv("SUICARDGAME_DATA_DIR", f"/tmp/suicardgame-step8-privacy-{uuid4().hex}")
    clear_rooms()
    client = TestClient(main.app)
    host, responder_a, responder_b = make_started_room(client)
    option_a = "option_for_a"
    option_b = "option_for_b"
    open_window(
        client,
        host,
        [responder_a["player_id"], responder_b["player_id"]],
        options={
            responder_a["player_id"]: [option_a, "decline"],
            responder_b["player_id"]: [option_b, "decline"],
        },
    )
    with main.rooms_lock:
        room = main.rooms[host["room_code"]]
        private_a = main._private_snapshot(room, responder_a["player_id"])
        private_b = main._private_snapshot(room, responder_b["player_id"])
        private_host = main._private_snapshot(room, host["player_id"])
    prompt_a = private_a["state"]["active_game"]["pending_action"]
    prompt_b = private_b["state"]["active_game"]["pending_action"]
    prompt_host = private_host["state"]["active_game"]["pending_action"]
    assert prompt_a["legal_responses"] == [option_a, "decline"]
    assert option_b not in str(prompt_a)
    assert prompt_b["legal_responses"] == [option_b, "decline"]
    assert option_a not in str(prompt_b)
    assert prompt_host["legal_responses"] == []
    assert option_a not in str(prompt_host) and option_b not in str(prompt_host)
    assert all("hand" not in player for player in private_a["state"]["players"])
    assert "hand" in private_a["you"]
    clear_rooms()


def test_resolved_public_summary_does_not_reveal_response_content(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.setenv("SUICARDGAME_DATA_DIR", f"/tmp/suicardgame-step8-privacy-{uuid4().hex}")
    clear_rooms()
    client = TestClient(main.app)
    host, responder, _outsider = make_started_room(client)
    private_response = "secret_choice"
    prompt_id = open_window(
        client,
        host,
        [responder["player_id"]],
        options={responder["player_id"]: [private_response, "decline"]},
    )
    response = command(
        client,
        host["room_code"],
        responder,
        "RESPOND_TO_PROMPT",
        {"prompt_id": prompt_id, "response": private_response},
    )
    assert response.status_code == 200
    public = client.get(f"/api/v1/rooms/{host['room_code']}/state").json()
    prompt = public["active_game"]["pending_action"]
    assert prompt["status"] == "resolved"
    assert private_response not in str(prompt)
    assert "response_records" not in prompt
    clear_rooms()


def test_auth_errors_do_not_echo_tokens_or_full_hand_payloads(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.setenv("SUICARDGAME_DATA_DIR", f"/tmp/suicardgame-step8-privacy-{uuid4().hex}")
    clear_rooms()
    client = TestClient(main.app)
    host, responder, outsider = make_started_room(client)
    prompt_id = open_window(client, host, [responder["player_id"]])
    invalid_token = "invalid-sensitive-session-value"
    response = command(
        client,
        host["room_code"],
        outsider,
        "RESPOND_TO_PROMPT",
        {"prompt_id": prompt_id, "response": "accept", "hand": ["private-card-a", "private-card-b"]},
        authorization=invalid_token,
    )
    body = response.text
    assert response.status_code == 403
    assert invalid_token not in body
    assert "private-card-a" not in body
    assert host["session_id"] not in body
    assert responder["reconnect_token"] not in body
    clear_rooms()
