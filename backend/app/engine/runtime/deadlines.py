from __future__ import annotations

from backend.app.domain.room import GameState, Prompt, PromptKind


TURN_TIMEOUT_SECONDS = 90.0
REQUIRED_TIMEOUT_SECONDS = 30.0
OPTIONAL_TIMEOUT_SECONDS = 15.0
CHALLENGE_TIMEOUT_SECONDS = 10.0

_REQUIRED_DEFAULT_ACTIONS = frozenset({
    "choose_color",
    "choose_target",
    "discard_card",
    "give_card",
    "submit_cards",
    "transfer_card",
})
_CHALLENGE_KINDS = frozenset({
    PromptKind.WILD_DRAW_FOUR_CHALLENGE,
    PromptKind.CHONGYUE_CHALLENGE,
    PromptKind.HAS_SUI_CHALLENGE,
})


def is_required_prompt(prompt: Prompt) -> bool:
    """Return the mandatory/optional classification persisted on the prompt."""
    return (
        prompt.required
        or prompt.kind == PromptKind.NIAN_TURN_END_DISCARD
        or prompt.default_action in _REQUIRED_DEFAULT_ACTIONS
    )


def normalize_prompt_runtime_fields(game: GameState, prompt: Prompt) -> bool:
    """Backfill authoritative prompt identity and mandatory classification."""
    changed = False
    if prompt.game_id != game.game_id:
        prompt.game_id = game.game_id
        changed = True
    if prompt.game_epoch != game.game_epoch:
        prompt.game_epoch = game.game_epoch
        changed = True
    required = is_required_prompt(prompt)
    if prompt.required != required:
        prompt.required = required
        changed = True
    return changed


def resumed_prompt_timeout_seconds(prompt: Prompt) -> float:
    """Return the full timeout granted when a paused step is resumed."""
    if is_required_prompt(prompt):
        return REQUIRED_TIMEOUT_SECONDS
    if prompt.kind in _CHALLENGE_KINDS:
        return CHALLENGE_TIMEOUT_SECONDS
    return OPTIONAL_TIMEOUT_SECONDS
