from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from time import time

import pytest
from fastapi.testclient import TestClient

import backend.app.main as main
from backend.app.domain.room import GameStatus, Prompt, PromptKind, Room, RoomPhase, new_player
from backend.app.engine.command_handler import (
    Command,
    CommandError,
    _require_safe_test_fixture,
    expire_generic_response_window,
    expire_wild_draw_four_challenge,
    pause_expired_step,
    process_command,
    recover_runtime_state,
)
from backend.app.engine.runtime import resumed_prompt_timeout_seconds
from backend.app.repositories.json_store import JsonSnapshotStore, room_from_snapshot, room_to_snapshot
from backend.app.domain.cards import Card, SPECIAL_BY_KIND


def _command(room: Room, player_id: str, action_id: str, command_type: str, payload: dict | None = None):
    return process_command(room, Command(
        action_id=action_id,
        room_id=room.room_id,
        player_id=player_id,
        command_type=command_type,
        payload=payload or {},
        game_id=room.active_game.game_id if room.active_game else None,
        game_epoch=room.active_game.game_epoch if room.active_game else None,
    ))


def _started_room() -> tuple[Room, str, str]:
    host = new_player("host", 0, is_host=True)
    guest = new_player("guest", 1)
    room = Room(room_id="RT001", host_player_id=host.player_id, players=[host, guest])
    _command(room, host.player_id, "ready-host", "READY")
    _command(room, guest.player_id, "ready-guest", "READY")
    _command(room, host.player_id, "start", "START_GAME", {"seed": 17})
    return room, host.player_id, guest.player_id


def test_turn_expiry_pauses_without_drawing_and_resume_restarts_90_seconds():
    room, host_id, guest_id = _started_room()
    game = room.active_game
    assert game is not None and game.turn_deadline_at is not None
    assert 89 <= game.turn_deadline_at - time() <= 90
    before = [(player.player_id, len(player.hand)) for player in room.players]
    sequence = game.turn_sequence

    assert pause_expired_step(room, prompt_id=None, now=game.turn_deadline_at)
    assert game.pause_state is not None
    assert game.pause_state.step_kind == PromptKind.TURN_MAIN.value
    assert [(player.player_id, len(player.hand)) for player in room.players] == before
    assert game.current_player_id == host_id
    with pytest.raises(CommandError, match="暂停"):
        _command(room, guest_id, "draw-while-paused", "DRAW_CARD")

    response = _command(room, host_id, "continue", "CONTINUE_WAITING")
    assert response["ok"] is True
    assert game.pause_state is None
    assert game.turn_sequence == sequence + 1
    assert 89 <= game.turn_deadline_at - time() <= 90
    assert _command(room, host_id, "continue", "CONTINUE_WAITING") == response


def test_mandatory_prompt_pause_preserves_effect_and_rotates_prompt_id_on_resume():
    room, host_id, guest_id = _started_room()
    game = room.active_game
    assert game is not None
    now = time()
    prompt = Prompt(
        prompt_id="mandatory-1",
        kind=PromptKind.NIAN_TURN_END_DISCARD,
        source_player_id=host_id,
        source_card_id=None,
        responder_ids=[host_id],
        legal_responses=["discard_card"],
        created_at=now,
        deadline_at=now + 30,
        default_action="discard_card",
        state_version=room.state_version,
        required=True,
    )
    game.current_prompt = prompt
    game.turn_deadline_at = None
    game.effect_queue.append({"type": "nian_turn_end_discard", "prompt_id": prompt.prompt_id, "source_player_id": host_id})
    before_hand = list(room.player(host_id).hand)

    assert pause_expired_step(room, prompt_id=prompt.prompt_id, now=prompt.deadline_at)
    restored = room_from_snapshot(room_to_snapshot(room))
    assert restored.active_game.pause_state.prompt_id == "mandatory-1"
    assert restored.active_game.current_prompt.required
    assert restored.active_game.effect_queue[0]["prompt_id"] == "mandatory-1"

    _command(room, host_id, "continue", "CONTINUE_WAITING")
    assert prompt.prompt_id != "mandatory-1"
    assert game.effect_queue[0]["prompt_id"] == prompt.prompt_id
    assert 29 <= prompt.deadline_at - time() <= 30
    assert room.player(host_id).hand == before_hand
    with pytest.raises(CommandError) as exc:
        _command(room, host_id, "old-response", "RESPOND_TO_PROMPT", {"prompt_id": "mandatory-1", "response": "discard_card"})
    assert exc.value.code == "STALE_PROMPT"


def test_abort_is_host_only_has_no_winner_and_rematch_requires_new_ready():
    room, host_id, guest_id = _started_room()
    game = room.active_game
    assert game is not None and game.turn_deadline_at is not None
    assert pause_expired_step(room, prompt_id=None, now=game.turn_deadline_at)
    with pytest.raises(CommandError) as exc:
        _command(room, guest_id, "guest-abort", "ABORT_GAME")
    assert exc.value.code == "HOST_REQUIRED"
    response = _command(room, host_id, "abort", "ABORT_GAME")
    assert response["game_status"] == GameStatus.ABORTED_BY_ROOM_RESET.value
    assert room.phase == RoomPhase.ROUND_RESULT
    assert room.active_game.winner_player_id is None
    assert _command(room, host_id, "abort", "ABORT_GAME") == response
    _command(room, host_id, "rematch", "REMATCH")
    assert room.phase == RoomPhase.LOBBY
    assert all(not player.ready for player in room.players)


def test_avatar_roundtrip_defaults_for_old_snapshot():
    room, _, _ = _started_room()
    room.players[0].avatar_id = "wang"
    snapshot = room_to_snapshot(room)
    assert room_from_snapshot(snapshot).players[0].avatar_id == "wang"
    del snapshot["players"][1]["avatar_id"]
    assert room_from_snapshot(snapshot).players[1].avatar_id == "default"


def test_scheduler_expires_normal_turn_without_advancing(tmp_path, monkeypatch):
    room, host_id, _ = _started_room()
    game = room.active_game
    assert game is not None
    monkeypatch.setattr(main, "snapshot_store", JsonSnapshotStore(tmp_path))
    game.turn_deadline_at = time() - 0.01

    async def run():
        main._schedule_prompt_expiry(room)
        assert len(main.prompt_expiry_tasks) == 1
        await asyncio.sleep(0.05)
        assert game.pause_state is not None
        assert game.current_player_id == host_id
        assert not main.prompt_expiry_tasks

    asyncio.run(run())
    assert main.snapshot_store.load_room_snapshots()[0].active_game.pause_state is not None


def test_plus_four_expiry_schedules_successor_window(tmp_path, monkeypatch):
    room, host_id, guest_id = _started_room()
    game = room.active_game
    assert game is not None
    room.player(host_id).hand.append(Card.from_spec(SPECIAL_BY_KIND["ji"]))
    monkeypatch.setattr(main, "snapshot_store", JsonSnapshotStore(tmp_path))
    now = time()
    prompt = Prompt(
        prompt_id="plus-four-expiry",
        kind=PromptKind.WILD_DRAW_FOUR_CHALLENGE,
        source_player_id=host_id,
        source_card_id=None,
        responder_ids=[guest_id],
        legal_responses=["challenge", "decline_challenge"],
        created_at=now - 10,
        deadline_at=now - 0.01,
        default_action="decline_challenge",
        state_version=room.state_version,
    )
    game.current_prompt = prompt
    game.current_player_id = guest_id
    game.turn_deadline_at = None
    game.effect_queue.append({
        "type": "wild_draw_four_challenge",
        "prompt_id": prompt.prompt_id,
        "source_player_id": host_id,
        "target_player_id": guest_id,
        "challenge_result": "legal",
        "source_would_win": False,
    })
    before = len(room.player(guest_id).hand)

    async def run():
        main._schedule_prompt_expiry(room)
        assert (room.room_id, prompt.prompt_id) in main.prompt_expiry_tasks
        await asyncio.sleep(0.05)
        assert len(room.player(guest_id).hand) == before + 4
        assert game.current_prompt is not None
        assert game.current_prompt.kind == PromptKind.HAS_SUI_CHALLENGE
        assert (room.room_id, game.current_prompt.prompt_id) in main.prompt_expiry_tasks
        for task in list(main.prompt_expiry_tasks.values()):
            task.cancel()
        main.prompt_expiry_tasks.clear()
        main.prompt_expiry_fingerprints.clear()

    asyncio.run(run())


def test_required_has_sui_delivery_resume_gets_full_30_seconds():
    room, host_id, guest_id = _started_room()
    game = room.active_game
    assert game is not None
    now = time()
    prompt = Prompt(
        prompt_id="has-sui-delivery",
        kind=PromptKind.HAS_SUI_CHALLENGE,
        source_player_id=guest_id,
        source_card_id=None,
        responder_ids=[host_id],
        legal_responses=["give_card"],
        created_at=now,
        deadline_at=now + 30,
        default_action="give_card",
        state_version=room.state_version,
        required=True,
    )
    game.current_prompt = prompt
    game.turn_deadline_at = None
    game.effect_queue.append({"type": "has_sui_challenge", "prompt_id": prompt.prompt_id})
    assert resumed_prompt_timeout_seconds(prompt) == 30
    assert pause_expired_step(room, prompt_id=prompt.prompt_id, now=prompt.deadline_at)

    _command(room, host_id, "resume-has-sui-delivery", "CONTINUE_WAITING")

    assert game.pause_state is None
    assert 29 <= prompt.deadline_at - time() <= 30
    assert prompt.game_id == game.game_id
    assert prompt.game_epoch == game.game_epoch


def test_optional_window_expires_to_default_without_pausing():
    room, host_id, guest_id = _started_room()
    game = room.active_game
    assert game is not None
    now = time()
    prompt = Prompt(
        prompt_id="optional-window",
        kind=PromptKind.GENERIC_RESPONSE_WINDOW,
        source_player_id=host_id,
        source_card_id=None,
        responder_ids=[guest_id],
        legal_responses=["accept", "decline"],
        created_at=now - 15,
        deadline_at=now,
        default_action="decline",
        state_version=room.state_version,
        game_id=game.game_id,
        game_epoch=game.game_epoch,
    )
    game.current_prompt = prompt
    game.turn_deadline_at = None
    game.effect_queue.append({"type": "generic_response_window", "prompt_id": prompt.prompt_id})

    assert expire_generic_response_window(room, prompt.prompt_id, now=now)
    assert game.pause_state is None
    assert game.current_prompt is None
    assert game.last_prompt is prompt
    assert prompt.default_applied_count == 1


def test_recover_runtime_state_backfills_clock_identity_and_pauses_required():
    room, host_id, guest_id = _started_room()
    game = room.active_game
    assert game is not None
    game.turn_deadline_at = None
    sequence = game.turn_sequence

    assert recover_runtime_state(room, now=1_000)
    assert game.turn_sequence == sequence + 1
    assert game.turn_deadline_at == 1_090

    prompt = Prompt(
        prompt_id="recovered-required",
        kind=PromptKind.HAS_SUI_CHALLENGE,
        source_player_id=guest_id,
        source_card_id=None,
        responder_ids=[host_id],
        legal_responses=["give_card"],
        created_at=900,
        deadline_at=930,
        default_action="give_card",
        state_version=room.state_version,
    )
    game.current_prompt = prompt
    game.turn_deadline_at = 1_090

    assert recover_runtime_state(room, now=1_000)
    assert game.pause_state is not None
    assert game.pause_state.prompt_id == prompt.prompt_id
    assert game.turn_deadline_at is None
    assert prompt.required is True
    assert prompt.game_id == game.game_id
    assert prompt.game_epoch == game.game_epoch


def test_snapshot_store_restart_marks_sessions_offline(tmp_path):
    room, _, _ = _started_room()
    store = JsonSnapshotStore(tmp_path)
    store.save_room(room)

    restored = store.load_room_snapshots()[0]

    assert all(not player.online for player in restored.players)


def test_old_turn_timer_is_cancelled_and_reset_game_cannot_be_paused(tmp_path, monkeypatch):
    room, host_id, _ = _started_room()
    game = room.active_game
    assert game is not None
    monkeypatch.setattr(main, "snapshot_store", JsonSnapshotStore(tmp_path))

    async def run():
        game.turn_deadline_at = time() + 0.03
        main._schedule_prompt_expiry(room)
        old_tasks = list(main.prompt_expiry_tasks.values())
        assert len(old_tasks) == 1

        game.turn_sequence += 1
        game.turn_deadline_at = time() + 0.20
        main._schedule_prompt_expiry(room)
        await asyncio.sleep(0)
        assert old_tasks[0].cancelled()
        await asyncio.sleep(0.06)
        assert game.pause_state is None

        _command(room, host_id, "reset-before-new-deadline", "RESET_ROOM")
        main._schedule_prompt_expiry(room)
        await asyncio.sleep(0.02)
        assert room.active_game is None
        assert not main.prompt_expiry_tasks

    asyncio.run(run())


def test_five_seats_all_online_ready_and_sixth_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "snapshot_store", JsonSnapshotStore(tmp_path))
    with main.rooms_lock:
        main.rooms.clear()
    with TestClient(main.app) as client:
        host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
        members = [host]
        for index in range(1, 5):
            response = client.post(
                f"/api/v1/rooms/{host['room_code']}/join",
                json={"nickname": f"p{index}"},
            )
            assert response.status_code == 200
            members.append(response.json())
        blocked = client.post(
            f"/api/v1/rooms/{host['room_code']}/join",
            json={"nickname": "sixth"},
        )
        assert blocked.status_code == 409
        assert blocked.json()["detail"] == "ROOM_FULL"

        for index, member in enumerate(members):
            ready = client.post(
                f"/api/v1/rooms/{host['room_code']}/commands",
                headers={"Authorization": f"Bearer {member['session_id']}"},
                json={
                    "action_id": f"ready-{index}",
                    "player_id": member["player_id"],
                    "command_type": "READY",
                    "payload": {"ready": True},
                },
            )
            assert ready.status_code == 200

        room = main.rooms[host["room_code"]]
        room.players[-1].online = False
        start_payload = {
            "player_id": host["player_id"],
            "command_type": "START_GAME",
            "payload": {"seed": 17},
        }
        not_online = client.post(
            f"/api/v1/rooms/{host['room_code']}/commands",
            headers={"Authorization": f"Bearer {host['session_id']}"},
            json={"action_id": "start-offline", **start_payload},
        )
        assert not_online.status_code == 400
        assert not_online.json()["detail"]["error"] == "PLAYERS_NOT_READY"

        room.players[-1].online = True
        started = client.post(
            f"/api/v1/rooms/{host['room_code']}/commands",
            headers={"Authorization": f"Bearer {host['session_id']}"},
            json={"action_id": "start-all-online", **start_payload},
        )
        assert started.status_code == 200

    with main.rooms_lock:
        main.rooms.clear()


def test_response_fixture_accepts_unique_directory_under_system_temp(monkeypatch):
    isolated = Path(tempfile.gettempdir()).resolve() / "suicardgame-step8-runtime-test" / "rooms"
    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.setenv("SUICARDGAME_DATA_DIR", str(isolated))

    _require_safe_test_fixture()


def test_response_fixture_rejects_directory_outside_system_temp(monkeypatch):
    unsafe = Path.cwd().resolve() / "suicardgame-step8-not-system-temp" / "rooms"
    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.setenv("SUICARDGAME_DATA_DIR", str(unsafe))

    with pytest.raises(CommandError) as exc:
        _require_safe_test_fixture()

    assert exc.value.code == "TEST_DATA_DIR_UNSAFE"
