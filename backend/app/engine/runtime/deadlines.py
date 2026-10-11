from __future__ import annotations

from backend.app.domain.room import GameState, Prompt, PromptKind


TURN_TIMEOUT_SECONDS = 180.0
MULTI_CARD_TIMEOUT_SECONDS = 180.0
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
_MULTI_CARD_RESPONSES = frozenset({"submit_cards", "restart", "chi", "peng", "gang"})


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


def prompt_timeout_seconds(prompt: Prompt) -> float:
    """Return the timeout for both a new prompt and a resumed prompt."""
    if prompt.default_action == "decline_challenge" or (
        prompt.kind in _CHALLENGE_KINDS and prompt.default_action != "give_card"
    ):
        return CHALLENGE_TIMEOUT_SECONDS
    if _MULTI_CARD_RESPONSES.intersection(prompt.legal_responses):
        return MULTI_CARD_TIMEOUT_SECONDS
    if is_required_prompt(prompt):
        return REQUIRED_TIMEOUT_SECONDS
    return OPTIONAL_TIMEOUT_SECONDS


def resumed_prompt_timeout_seconds(prompt: Prompt) -> float:
    """Return the full timeout granted when a paused step is resumed."""
    return prompt_timeout_seconds(prompt)
