"""Real READY commands for tests that enter a game.

These helpers deliberately use the same command paths as players, rather than
patching the start-game guard or mutating ``Player.ready`` directly.
"""

from backend.app.domain.room import PromptKind
from backend.app.engine.command_handler import Command, process_command


def ready_all(room, *, action_prefix: str = "ready") -> None:
    for player in room.seats_in_order():
        process_command(
            room,
            Command(
                action_id=f"{action_prefix}-{player.player_id}",
                room_id=room.room_id,
                player_id=player.player_id,
                command_type="READY",
                payload={"ready": True},
            ),
        )


def ready_all_http(client, room_code: str, sessions: list[dict], *, action_prefix: str = "ready") -> None:
    for session in sessions:
        response = client.post(
            f"/api/v1/rooms/{room_code}/commands",
            json={
                "action_id": f"{action_prefix}-{session['player_id']}",
                "player_id": session["player_id"],
                "command_type": "READY",
                "payload": {"ready": True},
            },
            headers={"Authorization": f"Bearer {session['session_id']}"},
        )
        assert response.status_code == 200


def decline_has_sui_prompts(room, *, action_prefix: str = "decline-has-sui") -> None:
    """Finish the optional post-turn HAS_SUI challenge chain through real commands."""

    sequence = 0
    while room.active_game is not None:
        prompt = room.active_game.current_prompt
        if prompt is None or prompt.kind != PromptKind.HAS_SUI_CHALLENGE:
            return
        process_command(
            room,
            Command(
                action_id=f"{action_prefix}-{sequence}-{prompt.prompt_id}",
                room_id=room.room_id,
                player_id=prompt.responder_ids[0],
                command_type="RESPOND_TO_PROMPT",
                payload={"prompt_id": prompt.prompt_id, "response": "decline_challenge"},
            ),
        )
        sequence += 1


def pass_sui_activation_reactions(room, *, action_prefix: str = "pass-sui-reaction") -> dict | None:
    """Pass every optional activation reaction through the real command path."""

    sequence = 0
    last_result = None
    while room.active_game is not None and room.active_game.current_prompt is not None:
        prompt = room.active_game.current_prompt
        effect = next(
            (item for item in room.active_game.effect_queue if item.get("prompt_id") == prompt.prompt_id),
            None,
        )
        effect_type = effect.get("type") if effect is not None else None
        if not isinstance(effect_type, str) or not effect_type.endswith("_reaction"):
            return last_result
        last_result = process_command(
            room,
            Command(
                action_id=f"{action_prefix}-{sequence}-{prompt.prompt_id}",
                room_id=room.room_id,
                player_id=prompt.responder_ids[0],
                command_type="RESPOND_TO_PROMPT",
                payload={"prompt_id": prompt.prompt_id, "response": "pass"},
            ),
        )
        sequence += 1
    return last_result
