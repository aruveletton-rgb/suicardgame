from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from tempfile import mkdtemp
from uuid import uuid4

import pytest

from backend.app.domain.room import PromptKind, PromptStatus, Room
from backend.app.engine.command_handler import Command, CommandError, process_command
from backend.app.domain.room import new_player
from backend.tests.ready_helpers import ready_all


def make_started_room(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.setenv("SUICARDGAME_DATA_DIR", mkdtemp(prefix="suicardgame-step8-unit-"))
    host = new_player("host", 0, is_host=True)
    responder_a = new_player("a", 1)
    responder_b = new_player("b", 2)
    outsider = new_player("outsider", 3)
    room = Room(room_id="S8TEST", host_player_id=host.player_id, players=[host, responder_a, responder_b, outsider])
    ready_all(room)
    process_command(
        room,
        Command(action_id="start", room_id=room.room_id, player_id=host.player_id, command_type="START_GAME", payload={"seed": 808}),
    )
    return room, host, responder_a, responder_b, outsider


def open_window(room, host, responders, *, policy="first_wins", timeout=10, options=None, action_id=None):
    result = process_command(
        room,
        Command(
            action_id=action_id or f"open-{uuid4().hex}",
            room_id=room.room_id,
            player_id=host.player_id,
            command_type="TEST_OPEN_RESPONSE_WINDOW",
            payload={
                "responder_ids": [player.player_id for player in responders],
                "resolution_policy": policy,
                "timeout_seconds": timeout,
                "private_options_by_responder": options or {},
            },
            game_id=room.active_game.game_id,
            game_epoch=room.active_game.game_epoch,
        ),
    )
    return result["prompt_id"]


def respond(room, player, prompt_id, response="accept", *, action_id=None, expected_state_version=None):
    return process_command(
        room,
        Command(
            action_id=action_id or f"respond-{uuid4().hex}",
            room_id=room.room_id,
            player_id=player.player_id,
            command_type="RESPOND_TO_PROMPT",
            payload={"prompt_id": prompt_id, "response": response},
            game_id=room.active_game.game_id,
            game_epoch=room.active_game.game_epoch,
            expected_state_version=expected_state_version,
        ),
    )


def test_generic_prompt_identity_and_metadata_are_card_agnostic(monkeypatch):
    room, host, responder_a, responder_b, _outsider = make_started_room(monkeypatch)
    first_id = open_window(room, host, [responder_a, responder_b])
    prompt = room.active_game.current_prompt
    assert prompt.prompt_id == first_id
    assert prompt.kind == PromptKind.GENERIC_RESPONSE_WINDOW
    assert prompt.status == PromptStatus.OPEN
    assert prompt.source_card_id is None
    assert prompt.game_id == room.active_game.game_id
    assert prompt.game_epoch == room.active_game.game_epoch
    respond(room, responder_a, first_id)
    second_id = open_window(room, host, [responder_a, responder_b])
    assert second_id != first_id
    assert all(card_key not in repr(room.active_game.current_prompt).lower() for card_key in ("ji", "yu", "zuole", "sui_xiang", "chongyue", "fuzhou"))


def test_first_wins_consumes_once_and_resumes_once(monkeypatch):
    room, host, responder_a, responder_b, _outsider = make_started_room(monkeypatch)
    prompt_id = open_window(room, host, [responder_a, responder_b])
    result = respond(room, responder_a, prompt_id)
    assert result["prompt_status"] == "resolved"
    assert room.active_game.current_prompt is None
    assert room.active_game.last_prompt.resolved_by_player_id == responder_a.player_id
    assert room.active_game.last_prompt.resume_count == 1
    assert room.active_game.special_state["response_window_fixture"] == {
        "resolution_count": 1,
        "default_count": 0,
        "resume_count": 1,
    }
    assert not room.active_game.effect_queue
    with pytest.raises(CommandError) as exc_info:
        respond(room, responder_b, prompt_id)
    assert exc_info.value.code == "PROMPT_RESOLVED"
    assert room.active_game.last_prompt.resume_count == 1


def test_first_wins_is_atomic_under_room_lock(monkeypatch):
    room, host, responder_a, responder_b, _outsider = make_started_room(monkeypatch)
    prompt_id = open_window(room, host, [responder_a, responder_b])

    def submit(player):
        try:
            with room.lock:
                respond(room, player, prompt_id)
            return "ok"
        except CommandError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(submit, [responder_a, responder_b]))
    assert outcomes.count("ok") == 1
    assert outcomes.count("PROMPT_RESOLVED") == 1
    assert len(room.active_game.last_prompt.response_records) == 1
    assert room.active_game.special_state["response_window_fixture"]["resume_count"] == 1


def test_sequential_policy_enforces_order_and_completes_once(monkeypatch):
    room, host, responder_a, responder_b, _outsider = make_started_room(monkeypatch)
    prompt_id = open_window(room, host, [responder_a, responder_b], policy="sequential")
    with pytest.raises(CommandError) as exc_info:
        respond(room, responder_b, prompt_id)
    assert exc_info.value.code == "NOT_CURRENT_PROMPT_RESPONDER"
    first = respond(room, responder_a, prompt_id)
    assert first["prompt_status"] == "open"
    assert room.active_game.current_prompt.next_responder_index == 1
    second = respond(room, responder_b, prompt_id)
    assert second["prompt_status"] == "resolved"
    assert room.active_game.last_prompt.resume_count == 1


def test_all_policy_waits_for_every_responder(monkeypatch):
    room, host, responder_a, responder_b, _outsider = make_started_room(monkeypatch)
    prompt_id = open_window(room, host, [responder_a, responder_b], policy="all")
    first = respond(room, responder_b, prompt_id)
    assert first["prompt_status"] == "open"
    assert room.active_game.current_prompt is not None
    with pytest.raises(CommandError) as exc_info:
        respond(room, responder_b, prompt_id)
    assert exc_info.value.code == "DUPLICATE_PROMPT_RESPONSE"
    final = respond(room, responder_a, prompt_id)
    assert final["prompt_status"] == "resolved"
    assert len(room.active_game.last_prompt.response_records) == 2


def test_action_id_replay_is_idempotent_after_prompt_consumption(monkeypatch):
    room, host, responder_a, responder_b, _outsider = make_started_room(monkeypatch)
    prompt_id = open_window(room, host, [responder_a, responder_b])
    action_id = "same-action-id"
    first = respond(room, responder_a, prompt_id, action_id=action_id)
    second = respond(room, responder_a, prompt_id, action_id=action_id)
    assert second == first
    assert room.active_game.special_state["response_window_fixture"]["resolution_count"] == 1
    assert room.active_game.last_prompt.resume_count == 1


def test_stale_expected_state_version_rejects_without_mutation(monkeypatch):
    room, host, responder_a, responder_b, _outsider = make_started_room(monkeypatch)
    prompt_id = open_window(room, host, [responder_a, responder_b])
    before_version = room.state_version
    before_records = dict(room.active_game.current_prompt.response_records)
    with pytest.raises(CommandError) as exc_info:
        respond(room, responder_a, prompt_id, expected_state_version=before_version - 1)
    assert exc_info.value.code == "BAD_STATE_VERSION"
    assert room.state_version == before_version
    assert room.active_game.current_prompt.response_records == before_records
