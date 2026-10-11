from __future__ import annotations

from backend.app.domain.room import GameState


STACK_INCREMENTS = {"draw_two": 2, "wild_draw_four": 4, "skip": 1}


def extend_action_stack(game: GameState, kind: str) -> dict[str, int | str]:
    stack = game.special_state.get("action_stack")
    if stack is not None and stack["kind"] != kind:
        raise ValueError("action stack kind differs from played card")
    extended = {"kind": kind, "count": (stack["count"] if stack else 0) + STACK_INCREMENTS[kind]}
    game.special_state["action_stack"] = extended
    return extended
