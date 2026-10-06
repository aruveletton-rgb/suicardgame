from __future__ import annotations

import pytest

from backend.app.domain.room import GameStatus, PromptStatus, RoomPhase
from backend.app.engine.command_handler import (
    Command,
    CommandError,
    _finish_game,
    expire_generic_response_window,
    process_command,
)
from backend.tests.test_response_window_foundation import make_started_room, open_window, respond
from backend.tests.ready_helpers import ready_all


def test_expiry_applies_default_and_resume_exactly_once(monkeypatch):
    room, host, responder_a, responder_b, _outsider = make_started_room(monkeypatch)
    prompt_id = open_window(room, host, [responder_a, responder_b], timeout=0.25)
    deadline = room.active_game.current_prompt.deadline_at
    assert expire_generic_response_window(room, prompt_id, now=deadline + 1)
    assert not expire_generic_response_window(room, prompt_id, now=deadline + 2)
    prompt = room.active_game.last_prompt
    assert prompt.status == PromptStatus.EXPIRED
    assert prompt.default_applied_count == 1
    assert prompt.resume_count == 1
    assert room.active_game.special_state["response_window_fixture"] == {
        "resolution_count": 0,
        "default_count": 1,
        "resume_count": 1,
    }
    with pytest.raises(CommandError) as exc_info:
        respond(room, responder_a, prompt_id)
    assert exc_info.value.code == "PROMPT_EXPIRED"


def test_response_at_or_after_deadline_is_rejected(monkeypatch):
    room, host, responder_a, _responder_b, _outsider = make_started_room(monkeypatch)
    prompt_id = open_window(room, host, [responder_a], timeout=0.25)
    room.active_game.current_prompt.deadline_at = 0
    with pytest.raises(CommandError) as exc_info:
        respond(room, responder_a, prompt_id)
    assert exc_info.value.code == "DEADLINE_EXPIRED"
    assert room.active_game.current_prompt.response_records == {}


def test_reset_invalidates_old_prompt_and_old_game_command(monkeypatch):
    room, host, responder_a, _responder_b, _outsider = make_started_room(monkeypatch)
    old_game_id = room.active_game.game_id
    old_epoch = room.active_game.game_epoch
    prompt_id = open_window(room, host, [responder_a])
    process_command(room, Command(action_id="reset", room_id=room.room_id, player_id=host.player_id, command_type="RESET_ROOM"))
    assert room.phase == RoomPhase.LOBBY
    assert room.active_game is None
    with pytest.raises(CommandError) as exc_info:
        process_command(
            room,
            Command(
                action_id="old-response",
                room_id=room.room_id,
                player_id=responder_a.player_id,
                command_type="RESPOND_TO_PROMPT",
                payload={"prompt_id": prompt_id, "response": "accept"},
                game_id=old_game_id,
                game_epoch=old_epoch,
            ),
        )
    assert exc_info.value.code == "STALE_GAME_COMMAND"


def test_rematch_invalidates_prompt_before_dropping_game(monkeypatch):
    room, host, responder_a, _responder_b, _outsider = make_started_room(monkeypatch)
    open_window(room, host, [responder_a])
    room.phase = RoomPhase.ROUND_RESULT
    room.active_game.status = GameStatus.FINISHED
    process_command(room, Command(action_id="rematch", room_id=room.room_id, player_id=host.player_id, command_type="REMATCH"))
    assert room.phase == RoomPhase.LOBBY
    assert room.active_game is None


def test_close_cancels_open_prompt_and_rejects_future_commands(monkeypatch):
    room, host, responder_a, _responder_b, _outsider = make_started_room(monkeypatch)
    open_window(room, host, [responder_a])
    result = process_command(room, Command(action_id="close", room_id=room.room_id, player_id=host.player_id, command_type="CLOSE_ROOM"))
    assert result["room_phase"] == RoomPhase.CLOSED.value
    assert room.active_game.current_prompt is None
    assert room.active_game.last_prompt.status == PromptStatus.CANCELLED
    assert room.active_game.last_prompt.resolution_reason == "room_closed"
    with pytest.raises(CommandError) as exc_info:
        process_command(room, Command(action_id="ready-after-close", room_id=room.room_id, player_id=responder_a.player_id, command_type="READY"))
    assert exc_info.value.code == "ROOM_CLOSED"


def test_game_finish_cancels_open_prompt(monkeypatch):
    room, host, responder_a, _responder_b, _outsider = make_started_room(monkeypatch)
    open_window(room, host, [responder_a])
    _finish_game(room, room.active_game, host.player_id)
    assert room.active_game.status == GameStatus.FINISHED
    assert room.active_game.current_prompt is None
    assert room.active_game.last_prompt.status == PromptStatus.CANCELLED
    assert room.active_game.last_prompt.resolution_reason == "game_finished"
    assert room.active_game.turn_deadline_at is None
    assert room.active_game.uno_pending_player_id is None
    assert room.active_game.uno_catchable_by == []


def test_new_game_epoch_rejects_old_prompt(monkeypatch):
    room, host, responder_a, _responder_b, _outsider = make_started_room(monkeypatch)
    old_game_id = room.active_game.game_id
    old_epoch = room.active_game.game_epoch
    prompt_id = open_window(room, host, [responder_a])
    process_command(room, Command(action_id="reset-epoch", room_id=room.room_id, player_id=host.player_id, command_type="RESET_ROOM"))
    ready_all(room, action_prefix="ready-new-epoch")
    process_command(room, Command(action_id="start-new", room_id=room.room_id, player_id=host.player_id, command_type="START_GAME", payload={"seed": 809}))
    assert room.active_game.game_epoch > old_epoch
    with pytest.raises(CommandError) as exc_info:
        process_command(
            room,
            Command(
                action_id="old-epoch-response",
                room_id=room.room_id,
                player_id=responder_a.player_id,
                command_type="RESPOND_TO_PROMPT",
                payload={"prompt_id": prompt_id, "response": "accept"},
                game_id=old_game_id,
                game_epoch=old_epoch,
            ),
        )
    assert exc_info.value.code == "STALE_GAME_COMMAND"
