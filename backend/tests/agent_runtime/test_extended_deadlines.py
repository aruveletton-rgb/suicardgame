from __future__ import annotations

from time import time

import pytest

from backend.app.domain.room import GameState, PromptKind, Room, new_player
from backend.app.engine.command_handler import Command, pause_expired_step, process_command
from backend.app.engine.runtime import resumed_prompt_timeout_seconds
from backend.app.engine.special_effects import _new_prompt
from backend.app.repositories.json_store import room_from_snapshot, room_to_snapshot


@pytest.mark.parametrize(
    ("kind", "legal_responses", "default_action", "expected"),
    [
        (PromptKind.SUI_PLAYER_RESPONSE, ["submit_cards", "pass"], "pass", 180),
        (PromptKind.SUI_PLAYER_RESPONSE, ["restart", "stop"], "stop", 180),
        (PromptKind.NIAN_CLAIM_WINDOW, ["chi", "peng", "gang", "pass"], "pass", 180),
        (PromptKind.SUI_PLAYER_RESPONSE, ["give_card"], "give_card", 30),
        (PromptKind.SUI_PLAYER_RESPONSE, ["choose_target"], "choose_target", 30),
        (PromptKind.SUI_PLAYER_RESPONSE, ["decline"], "decline", 15),
        (PromptKind.CHONGYUE_CHALLENGE, ["challenge", "decline"], "decline", 10),
        (PromptKind.HAS_SUI_CHALLENGE, ["give_card"], "give_card", 30),
    ],
)
def test_prompt_creation_and_resume_use_same_timeout(kind, legal_responses, default_action, expected):
    player = new_player("host", 0, is_host=True)
    game = GameState(game_id="deadline-test", game_epoch=1)
    room = Room(room_id="DEADLN", host_player_id=player.player_id, players=[player], active_game=game)
    effect = {"type": "deadline-test", "source_player_id": player.player_id, "eligible_card_ids": []}

    before = time()
    _new_prompt(
        room, game, effect,
        kind=kind,
        responder_id=player.player_id,
        legal_responses=legal_responses,
        default_action=default_action,
    )
    prompt = game.current_prompt
    assert prompt is not None
    assert before + expected <= prompt.deadline_at <= time() + expected
    assert resumed_prompt_timeout_seconds(prompt) == expected

    restored = room_from_snapshot(room_to_snapshot(room)).active_game
    assert restored is not None and restored.current_prompt is not None
    assert resumed_prompt_timeout_seconds(restored.current_prompt) == expected


def test_multi_card_prompt_resume_grants_fresh_180_seconds():
    host = new_player("host", 0, is_host=True)
    guest = new_player("guest", 1)
    room = Room(room_id="DEADLN", host_player_id=host.player_id, players=[host, guest])
    for index, player in enumerate((host, guest)):
        process_command(room, Command(f"ready-{index}", room.room_id, player.player_id, "READY"))
    process_command(room, Command("start", room.room_id, host.player_id, "START_GAME", {"seed": 42}))
    game = room.active_game
    assert game is not None
    effect = {"type": "deadline-test", "source_player_id": host.player_id}
    game.effect_queue.append(effect)
    _new_prompt(
        room, game, effect,
        kind=PromptKind.SUI_PLAYER_RESPONSE,
        responder_id=host.player_id,
        legal_responses=["submit_cards", "pass"],
        default_action="submit_cards",
    )
    game.turn_deadline_at = None
    prompt = game.current_prompt
    assert prompt is not None
    old_prompt_id = prompt.prompt_id
    assert pause_expired_step(room, prompt_id=old_prompt_id, now=prompt.deadline_at)

    before = time()
    process_command(room, Command("resume", room.room_id, host.player_id, "CONTINUE_WAITING"))
    assert prompt.prompt_id != old_prompt_id
    assert before + 180 <= prompt.deadline_at <= time() + 180
    assert effect["prompt_id"] == prompt.prompt_id
