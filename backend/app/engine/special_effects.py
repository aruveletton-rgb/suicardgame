from __future__ import annotations

import random
from pathlib import Path
from time import time
from typing import Any
from uuid import uuid4

import yaml

from backend.app.domain.cards import Card, CardCategory, CardColor
from backend.app.domain.room import GameState, GameStatus, Prompt, PromptKind, PromptStatus, Room, RoomPhase
from backend.app.rules.uno import can_play_card, wild_draw_four_challenge_result
from backend.app.rules.sui.catalog import higher_sui_rank


class SpecialEffectError(ValueError):
    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code


RULES_PATH = Path(__file__).resolve().parents[2] / "rules" / "special_cards.yaml"
with RULES_PATH.open("r", encoding="utf-8") as rules_handle:
    _rules_document = yaml.safe_load(rules_handle)

SPECIAL_RULES = {item["id"]: item for item in _rules_document["special_cards"]}
SUPPORTED_SPECIAL_IDS = {
    "wang",
    "ji",
    "yu",
    "yi",
    "zuole",
    "xi",
    "nian",
    "sui_xiang",
    "shu",
    "chongyue",
    "ling",
    "cannot",
    "fuzhou",
}

PRE_EFFECT_REACTION_KINDS = {"yi", "shu", "chongyue", "wang"}
if set(SPECIAL_RULES) != SUPPORTED_SPECIAL_IDS:
    raise RuntimeError("special_cards.yaml and resolver ids do not match")


def _game(room: Room) -> GameState:
    if room.active_game is None:
        raise SpecialEffectError("当前没有进行中的牌局", code="STALE_GAME_COMMAND")
    return room.active_game


def _ordered_players(room: Room, game: GameState, source_player_id: str, *, include_source: bool) -> list:
    seats = room.seats_in_order()
    source_index = next(index for index, player in enumerate(seats) if player.player_id == source_player_id)
    ordered = [seats[(source_index + game.direction * step) % len(seats)] for step in range(1, len(seats) + 1)]
    if include_source:
        return ordered
    return [player for player in ordered if player.player_id != source_player_id]


def _next_player(room: Room, game: GameState, steps: int = 1):
    seats = room.seats_in_order()
    current_index = next(index for index, player in enumerate(seats) if player.player_id == game.current_player_id)
    return seats[(current_index + game.direction * steps) % len(seats)]


def _advance_turn(room: Room, game: GameState, steps: int = 1, *, skip_nian_draw: bool = False) -> None:
    next_player = _next_player(room, game, steps)
    game.current_player_id = next_player.player_id
    game.shop.bought_this_turn_by.discard(next_player.player_id)
    game.shop.refreshed_this_turn_by.discard(next_player.player_id)
    _apply_nian_turn_start_draw(game, next_player, skipped_by_claim=skip_nian_draw)


def _reshuffle(game: GameState) -> None:
    if game.deck:
        return
    if len(game.discard_pile) <= 1 or game.reshuffle_count >= 1:
        raise SpecialEffectError("当前没有可摸的牌", code="EMPTY_DECK")
    top = game.discard_pile[-1]
    recycled = game.discard_pile[:-1]
    random.shuffle(recycled)
    game.discard_pile = [top]
    game.deck.extend(recycled)
    game.reshuffle_count += 1


def _draw_cards(game: GameState, player, count: int) -> list[Card]:
    drawn: list[Card] = []
    for _ in range(count):
        try:
            _reshuffle(game)
            card = game.deck.pop()
        except SpecialEffectError as exc:
            if exc.code == "EMPTY_DECK":
                break
            raise
        player.hand.append(card)
        drawn.append(card)
    return drawn


def nian_enabled(game: GameState) -> bool:
    state = game.special_state.get("nian")
    return bool(game.special_state.get("nian_rules_enabled") or (isinstance(state, dict) and state.get("enabled")))


def _nian_state(game: GameState) -> dict[str, Any]:
    state = game.special_state.setdefault("nian", {})
    state.setdefault("enabled", True)
    state.setdefault("seen_claims", [])
    return state


def _apply_nian_turn_start_draw(game: GameState, player, *, skipped_by_claim: bool = False) -> int:
    if not nian_enabled(game) or skipped_by_claim:
        return 0
    drawn = _draw_cards(game, player, 1)
    _nian_state(game)["last_turn_start_draw"] = {
        "player_id": player.player_id,
        "drawn_count": len(drawn),
    }
    return len(drawn)


def _card_from_hand(player, card_id: str | None) -> Card:
    card = next((item for item in player.hand if item.card_id == card_id), None)
    if card is None:
        raise SpecialEffectError("所选牌不在你的手牌中", code="CARD_NOT_IN_HAND")
    return card


def _cards_from_hand(player, card_ids: list[str]) -> list[Card]:
    if len(card_ids) != len(set(card_ids)):
        raise SpecialEffectError("不能重复选择同一张牌", code="BAD_CARD_SELECTION")
    return [_card_from_hand(player, card_id) for card_id in card_ids]


def _consume_special(player, game: GameState, card_id: str, expected_kind: str | None = None) -> Card:
    card = _card_from_hand(player, card_id)
    if card.category != CardCategory.SUI:
        raise SpecialEffectError("所选牌不是可发动的岁牌", code="NOT_SPECIAL_CARD")
    if expected_kind is not None and card.kind != expected_kind:
        raise SpecialEffectError("无法识别该岁牌", code="NOT_SPECIAL_CARD")
    player.hand.remove(card)
    game.discard_pile.append(card)
    return card


def _discard_cards(player, game: GameState, cards: list[Card]) -> None:
    for card in cards:
        player.hand.remove(card)
        game.discard_pile.append(card)


def _new_prompt(
    room: Room,
    game: GameState,
    effect: dict[str, Any],
    *,
    kind: PromptKind,
    responder_id: str,
    legal_responses: list[str],
    default_action: str,
) -> None:
    effect_type = effect.get("type")
    if effect_type in {"wild_draw_four_challenge", "wang_wild_draw_four_challenge"} or (
        kind in {PromptKind.CHONGYUE_CHALLENGE, PromptKind.HAS_SUI_CHALLENGE}
        and default_action != "give_card"
    ):
        timeout_seconds = 10
    elif kind == PromptKind.NIAN_CLAIM_WINDOW:
        timeout_seconds = 15
    elif kind == PromptKind.NIAN_TURN_END_DISCARD or (
        effect_type == "has_sui_challenge" and default_action == "give_card"
    ) or (effect_type == "sui_xiang" and "submit_cards" in legal_responses):
        timeout_seconds = 30
    else:
        timeout_seconds = 15
    created_at = time()
    if kind == PromptKind.SUI_PLAYER_RESPONSE and effect_type in {"ji", "yu", "sui_xiang", "fuzhou"} and responder_id != effect.get("source_player_id"):
        legal_responses = [*legal_responses, "evade"]
    prompt = Prompt(
        prompt_id=uuid4().hex,
        kind=kind,
        source_player_id=effect.get("source_player_id"),
        source_card_id=effect.get("source_card_id"),
        responder_ids=[responder_id],
        legal_responses=legal_responses,
        created_at=created_at,
        deadline_at=created_at + timeout_seconds,
        default_action=default_action,
        state_version=room.state_version,
    )
    effect["prompt_id"] = prompt.prompt_id
    if kind == PromptKind.NIAN_TURN_END_DISCARD:
        prompt.required = True
    if kind == PromptKind.HAS_SUI_CHALLENGE and default_action == "give_card":
        prompt.required = True
        prompt.private_options_by_responder[responder_id] = list(effect["eligible_card_ids"])
    if "use_zuole" in legal_responses or "evade" in legal_responses:
        responder = room.player(responder_id)
        private_options = [card.card_id for card in responder.hand if card.kind == "zuole"]
        if (
            "evade" in legal_responses
            and responder_id != effect.get("source_player_id")
            and responder_id in effect.get("affected_player_ids", [responder_id])
        ):
            private_options.extend(
                card.card_id
                for card in responder.hand
                if card.category == CardCategory.SUI
                and higher_sui_rank(card.kind, effect.get("source_card_kind", ""))
            )
        prompt.private_options_by_responder[responder_id] = list(dict.fromkeys(private_options))
    game.current_prompt = prompt


def _open_effect(
    room: Room,
    game: GameState,
    effect: dict[str, Any],
    *,
    kind: PromptKind,
    responder_id: str,
    legal_responses: list[str],
    default_action: str,
) -> None:
    if game.current_prompt is not None:
        raise SpecialEffectError("请先处理当前待响应操作", code="PROMPT_PENDING")
    game.effect_queue.append(effect)
    _new_prompt(
        room,
        game,
        effect,
        kind=kind,
        responder_id=responder_id,
        legal_responses=legal_responses,
        default_action=default_action,
    )


def _replace_prompt(
    room: Room,
    game: GameState,
    effect: dict[str, Any],
    *,
    kind: PromptKind,
    responder_id: str,
    legal_responses: list[str],
    default_action: str,
) -> None:
    _new_prompt(
        room,
        game,
        effect,
        kind=kind,
        responder_id=responder_id,
        legal_responses=legal_responses,
        default_action=default_action,
    )


def _close_effect(game: GameState, effect: dict[str, Any]) -> None:
    game.current_prompt = None
    game.effect_queue = [item for item in game.effect_queue if item is not effect]


def _current_effect(game: GameState, prompt_id: str) -> dict[str, Any]:
    effect = next((item for item in game.effect_queue if item.get("prompt_id") == prompt_id), None)
    if effect is None:
        raise SpecialEffectError("待响应操作缺少结算状态", code="PROMPT_STATE_MISSING")
    return effect


def _color(value: Any) -> CardColor:
    try:
        return CardColor(value)
    except (TypeError, ValueError) as exc:
        raise SpecialEffectError("请选择有效颜色", code="COLOR_REQUIRED") from exc


def _finish_effect_and_advance(room: Room, game: GameState, effect: dict[str, Any]) -> None:
    completed_player_id = effect.get("source_player_id") or game.current_player_id
    parent_wang_source_card_id = effect.get("parent_wang_source_card_id")
    _close_effect(game, effect)
    last_card_candidate = bool(effect.get("last_card_candidate"))
    if parent_wang_source_card_id:
        if last_card_candidate and completed_player_id is not None:
            try:
                if not room.player(completed_player_id).hand:
                    game.special_state["pending_finish_player_id"] = completed_player_id
            except KeyError:
                pass
        _advance_turn(room, game)
        _resume_wang_parent(room, game, parent_wang_source_card_id)
        return
    pending_finish_player_id = game.special_state.pop("pending_finish_player_id", None)
    finish_player_id = pending_finish_player_id
    if finish_player_id is None and last_card_candidate and completed_player_id is not None:
        try:
            if not room.player(completed_player_id).hand:
                finish_player_id = completed_player_id
        except KeyError:
            finish_player_id = None
    if open_has_sui_challenge(room, completed_player_id, finish_player_id=finish_player_id):
        return
    if _drain_seen_events(room, game):
        return
    if finish_player_id is not None and not room.player(finish_player_id).hand:
        _finish_game_state(room, game, finish_player_id)
        return
    _advance_turn(room, game)


def open_has_sui_challenge(
    room: Room,
    completed_player_id: str,
    *,
    advance_steps: int = 1,
    finish_player_id: str | None = None,
) -> bool:
    """Open the end-of-turn question after all linked effects have resolved.

    The eligible transfer set is frozen here, before any challenge penalty draw.
    Callers retain the current player until this window closes.  Runtime owns
    deadline scheduling and persistence.
    """
    game = _game(room)
    if game.current_prompt is not None:
        return False
    responders = _claim_responders(room, game, completed_player_id)
    if not responders:
        return False
    source = room.player(completed_player_id)
    # The opportunity to challenge is a public end-of-turn protocol window.
    # Do not make its existence depend on the source's private card category:
    # the frozen eligible set is evaluated only after a challenge is submitted.
    # An empty hand is a terminal state and does not need a meaningless window.
    if not source.hand:
        return False
    eligible_card_ids = [card.card_id for card in source.hand if card.category == CardCategory.SUI]
    effect = {
        "type": "has_sui_challenge",
        "source_player_id": completed_player_id,
        "source_card_kind": "has_sui",
        "responder_ids": responders,
        "responder_index": 0,
        "advance_steps": advance_steps,
        "finish_player_id": finish_player_id,
        "eligible_card_ids": eligible_card_ids,
        "challenger_id": None,
        "challenger_ids": [],
    }
    _open_effect(
        room,
        game,
        effect,
        kind=PromptKind.HAS_SUI_CHALLENGE,
        responder_id=responders[0],
        legal_responses=["challenge", "decline_challenge"],
        default_action="decline_challenge",
    )
    return True


def _finish_game_state(room: Room, game: GameState, winner_player_id: str) -> None:
    game.current_prompt = None
    game.status = GameStatus.FINISHED
    game.winner_player_id = winner_player_id
    game.turn_deadline_at = None
    game.uno_pending_player_id = None
    game.uno_catchable_by = []
    room.phase = RoomPhase.ROUND_RESULT


def _advance_or_finish_has_sui(room: Room, game: GameState, effect: dict[str, Any]) -> None:
    finish_player_id = effect.get("finish_player_id")
    if finish_player_id is not None:
        if not room.player(finish_player_id).hand:
            game.special_state["pending_finish_player_id"] = finish_player_id
        else:
            finish_player_id = None
            effect["finish_player_id"] = None
    if _drain_seen_events(room, game):
        return
    if finish_player_id is not None and not room.player(finish_player_id).hand:
        game.special_state.pop("pending_finish_player_id", None)
        _finish_game_state(room, game, finish_player_id)
        return
    _advance_turn(room, game, int(effect["advance_steps"]))


def _finish_has_sui_challenge(room: Room, game: GameState, effect: dict[str, Any]) -> dict[str, Any]:
    challengers = effect.get("challenger_ids") or []
    if challengers:
        responder_order = {player_id: index for index, player_id in enumerate(effect.get("responder_ids", []))}
        effect["challenger_id"] = min(challengers, key=lambda player_id: responder_order.get(player_id, 10**9))
    challenger_id = effect.get("challenger_id")
    if challenger_id is None:
        _close_effect(game, effect)
        _advance_or_finish_has_sui(room, game, effect)
        return {"special_kind": "has_sui", "result": "unchallenged", "pending": False}
    if not effect["eligible_card_ids"]:
        challenger = room.player(challenger_id)
        penalty = len(_draw_cards(game, challenger, 4))
        _close_effect(game, effect)
        _advance_or_finish_has_sui(room, game, effect)
        return {"special_kind": "has_sui", "result": "challenge_failed", "penalty_count": penalty, "pending": False}
    _replace_prompt(
        room,
        game,
        effect,
        kind=PromptKind.HAS_SUI_CHALLENGE,
        responder_id=effect["source_player_id"],
        legal_responses=["give_card"],
        default_action="give_card",
    )
    return {"special_kind": "has_sui", "result": "challenge_succeeded", "pending": True}


def _respond_has_sui_challenge(room: Room, game: GameState, effect: dict[str, Any], player, response: str, payload: dict[str, Any]) -> dict[str, Any]:
    if response == "give_card":
        card_id = payload.get("card_id")
        if player.player_id != effect["source_player_id"] or card_id not in effect["eligible_card_ids"]:
            raise SpecialEffectError("请选择一张符合条件的岁牌", code="SPECIAL_SELECTION_INVALID")
        card = _card_from_hand(player, card_id)
        player.hand.remove(card)
        room.player(effect["challenger_id"]).hand.append(card)
        penalty = len(_draw_cards(game, player, 4))
        _close_effect(game, effect)
        _advance_or_finish_has_sui(room, game, effect)
        return {"special_kind": "has_sui", "result": "challenge_succeeded", "transferred_card_kind": card.kind, "penalty_count": penalty, "pending": False}
    if response == "challenge":
        challenger_ids = effect.setdefault("challenger_ids", [])
        if player.player_id not in challenger_ids:
            challenger_ids.append(player.player_id)
        if effect.get("challenger_id") is None:
            effect["challenger_id"] = player.player_id
    elif response != "decline_challenge":
        raise SpecialEffectError("该岁牌质疑响应无效", code="ILLEGAL_PROMPT_RESPONSE")
    if not _next_effect_responder(
        room,
        game,
        effect,
        kind=PromptKind.HAS_SUI_CHALLENGE,
        legal_responses=["challenge", "decline_challenge"],
        default_action="decline_challenge",
    ):
        return _finish_has_sui_challenge(room, game, effect)
    return {"special_kind": "has_sui", "pending": True}


def _card_summary(card: Card | None) -> dict[str, Any] | None:
    if card is None:
        return None
    return {
        "card_id": card.card_id,
        "kind": card.kind,
        "color": card.color.value if card.color is not None else None,
        "value": card.value,
    }


def open_nian_turn_end_discard(
    room: Room,
    game: GameState,
    player,
    *,
    last_played_card: Card | None,
    advance_steps: int = 1,
) -> bool:
    if not nian_enabled(game) or game.current_prompt is not None:
        return False
    if not player.hand:
        _maybe_open_nian_claim_or_advance(room, game, player.player_id, last_played_card, advance_steps)
        return True
    effect = {
        "type": "nian_turn_end_discard",
        "source_card_kind": "nian",
        "source_player_id": player.player_id,
        "source_card_id": last_played_card.card_id if last_played_card is not None else None,
        "last_played": _card_summary(last_played_card),
        "advance_steps": advance_steps,
    }
    _open_effect(
        room,
        game,
        effect,
        kind=PromptKind.NIAN_TURN_END_DISCARD,
        responder_id=player.player_id,
        legal_responses=["discard_card"],
        default_action="discard_card",
    )
    return True


def _claim_responders(room: Room, game: GameState, source_player_id: str) -> list[str]:
    return [member.player_id for member in _ordered_players(room, game, source_player_id, include_source=False)]


def _maybe_open_nian_claim_or_advance(
    room: Room,
    game: GameState,
    source_player_id: str,
    last_played_card: Card | None,
    advance_steps: int,
    parent_wang_source_card_id: str | None = None,
) -> None:
    if not nian_enabled(game) or last_played_card is None or last_played_card.value is None:
        _advance_turn(room, game, advance_steps)
        if parent_wang_source_card_id:
            _resume_wang_parent(room, game, parent_wang_source_card_id)
        return
    responders = _claim_responders(room, game, source_player_id)
    effect = {
        "type": "nian_claim",
        "source_card_kind": "nian",
        "source_player_id": source_player_id,
        "source_card_id": last_played_card.card_id,
        "last_played": _card_summary(last_played_card),
        "advance_steps": advance_steps,
        "responder_ids": responders,
        "responder_index": 0,
        "claims": [],
        "parent_wang_source_card_id": parent_wang_source_card_id,
    }
    _open_effect(
        room,
        game,
        effect,
        kind=PromptKind.NIAN_CLAIM_WINDOW,
        responder_id=responders[0],
        legal_responses=["chi", "peng", "gang", "pass"],
        default_action="pass",
    )


def _selected_claim_cards(player, payload: dict[str, Any], expected_count: int) -> list[Card]:
    card_ids = payload.get("card_ids")
    if not isinstance(card_ids, list) or len(card_ids) != expected_count:
        raise SpecialEffectError("年牌吃碰杠选择的牌数不正确", code="SPECIAL_SELECTION_INVALID")
    return _cards_from_hand(player, card_ids)


def _validate_nian_peng_or_gang(effect: dict[str, Any], cards: list[Card], claim_type: str) -> None:
    value = effect["last_played"]["value"]
    if any(card.value != value for card in cards):
        claim_label = {"chi": "吃", "peng": "碰", "gang": "杠"}.get(claim_type, claim_type)
        raise SpecialEffectError(f"年牌{claim_label}需要数字相同的牌", code="SPECIAL_SELECTION_INVALID")


def _validate_nian_chi(effect: dict[str, Any], cards: list[Card]) -> None:
    value = effect["last_played"]["value"]
    values = sorted(card.value for card in cards)
    if any(card.category != CardCategory.NUMBER or card.value is None for card in cards):
        raise SpecialEffectError("年牌吃需要数字牌", code="SPECIAL_SELECTION_INVALID")
    if sorted([*values, value]) not in ([value - 2, value - 1, value], [value - 1, value, value + 1], [value, value + 1, value + 2]):
        raise SpecialEffectError("年牌吃需要连续数字牌", code="SPECIAL_SELECTION_INVALID")


def _finish_nian_claim(room: Room, game: GameState, effect: dict[str, Any], player, claim_type: str, cards: list[Card]) -> None:
    _discard_cards(player, game, cards)
    state = _nian_state(game)
    claim = {
        "claim_type": claim_type,
        "player_id": player.player_id,
        "source_player_id": effect["source_player_id"],
        "source_card_id": effect["source_card_id"],
        "card_count": len(cards),
    }
    state["last_claim"] = claim
    state.setdefault("seen_claims", []).append(claim)
    _close_effect(game, effect)
    game.current_player_id = player.player_id
    game.shop.bought_this_turn_by.discard(player.player_id)
    game.shop.refreshed_this_turn_by.discard(player.player_id)
    if effect.get("parent_wang_source_card_id"):
        _resume_wang_parent(room, game, effect["parent_wang_source_card_id"])


def _resolve_nian_claims(room: Room, game: GameState, effect: dict[str, Any]) -> None:
    """Apply only the winning declaration after every eligible player has answered."""
    claims = effect.get("claims", [])
    if not claims:
        _close_effect(game, effect)
        _advance_turn(room, game, int(effect.get("advance_steps", 1)))
        if effect.get("parent_wang_source_card_id"):
            _resume_wang_parent(room, game, effect["parent_wang_source_card_id"])
        return
    priority = {"gang": 0, "peng": 1, "chi": 2}
    winner = min(claims, key=lambda item: (priority[item["claim_type"]], item["direction_distance"]))
    player = room.player(winner["player_id"])
    cards = _cards_from_hand(player, winner["card_ids"])
    _finish_nian_claim(room, game, effect, player, winner["claim_type"], cards)


def _next_effect_responder(
    room: Room,
    game: GameState,
    effect: dict[str, Any],
    *,
    kind: PromptKind,
    legal_responses: list[str],
    default_action: str,
) -> bool:
    effect["responder_index"] += 1
    responder_ids = effect["responder_ids"]
    if effect["responder_index"] >= len(responder_ids):
        return False
    _replace_prompt(
        room,
        game,
        effect,
        kind=kind,
        responder_id=responder_ids[effect["responder_index"]],
        legal_responses=legal_responses,
        default_action=default_action,
    )
    return True


def _validate_pre_effect_activation(
    room: Room,
    game: GameState,
    player,
    card: Card,
    payload: dict[str, Any],
) -> list[str]:
    """Validate an immediate Sui activation before opening its reaction window."""
    if card.kind == "yi":
        pair_ids = payload.get("pair_card_ids")
        if not isinstance(pair_ids, list) or len(pair_ids) != 2:
            raise SpecialEffectError("易牌需要选择两张牌", code="BAD_CARD_SELECTION")
        pair = _cards_from_hand(player, pair_ids)
        if any(item.category != CardCategory.NUMBER or item.value is None for item in pair) or sum(item.value for item in pair) != 8:
            raise SpecialEffectError("易牌所选两张数字牌之和必须为 8", code="SPECIAL_SELECTION_INVALID")
        return [member.player_id for member in room.players if member.player_id != player.player_id]
    if card.kind == "shu":
        remainder_player_id = _shu_remainder_player_id(payload)
        chosen_color = _color(payload.get("chosen_color"))
        recipients = [member for member in room.players if member.player_id != player.player_id]
        selected_count = sum(1 for item in player.hand if item.color == chosen_color)
        if selected_count < len(recipients):
            raise SpecialEffectError("所选黍牌颜色的手牌不足", code="SPECIAL_TIMING_INVALID")
        _, remainder = divmod(selected_count, len(recipients))
        fewest = min(len(member.hand) for member in recipients)
        eligible_remainder = [member.player_id for member in recipients if len(member.hand) == fewest]
        if remainder:
            if remainder_player_id is None and len(eligible_remainder) != 1:
                raise SpecialEffectError("请选择黍牌余牌接收者", code="SPECIAL_TARGET_REQUIRED")
            if remainder_player_id is not None and remainder_player_id not in eligible_remainder:
                raise SpecialEffectError("黍牌余牌接收者无效", code="SPECIAL_TARGET_INVALID")
        elif remainder_player_id is not None and remainder_player_id not in {member.player_id for member in recipients}:
            raise SpecialEffectError("黍牌余牌接收者无效", code="SPECIAL_TARGET_INVALID")
        return [member.player_id for member in recipients]
    if card.kind == "chongyue":
        return [member.player_id for member in room.players]
    if card.kind == "wang":
        target_player_id = payload.get("target_player_id")
        if target_player_id != game.current_player_id or target_player_id == player.player_id:
            raise SpecialEffectError("望牌目标必须是当前无法出牌的玩家", code="SPECIAL_TARGET_INVALID")
        target = room.player(target_player_id)
        top = game.discard_pile[-1] if game.discard_pile else None
        has_play = any(
            item.category != CardCategory.SUI
            and can_play_card(top_card=top, current_color=game.current_color, hand=target.hand, candidate=item).allowed
            for item in target.hand
        )
        if has_play:
            raise SpecialEffectError("望牌只能对当前无牌可出的玩家使用", code="SPECIAL_TIMING_INVALID")
        return [target.player_id]
    raise SpecialEffectError("该岁牌没有对应的响应规则", code="SPECIAL_RESOLVER_MISSING")


def _open_pre_effect_reaction(
    room: Room,
    game: GameState,
    player,
    card: Card,
    payload: dict[str, Any],
    *,
    controlled_by: str | None,
) -> dict[str, Any]:
    affected_player_ids = _validate_pre_effect_activation(room, game, player, card, payload)
    responders = [member.player_id for member in _ordered_players(room, game, player.player_id, include_source=True)]
    effect = {
        "type": "sui_activation_reaction",
        "source_card_kind": card.kind,
        "source_card_id": card.card_id,
        "source_player_id": player.player_id,
        "activation_payload": dict(payload),
        "controlled_by": controlled_by,
        "affected_player_ids": affected_player_ids,
        "immune_player_ids": [],
        "responder_ids": responders,
        "responder_index": 0,
        "last_card_candidate": len(player.hand) == 1,
    }
    _open_effect(
        room,
        game,
        effect,
        kind=PromptKind.SUI_REACTION,
        responder_id=responders[0],
        legal_responses=["pass", "use_zuole", "evade"],
        default_action="pass",
    )
    return {
        "special_kind": "shu_reaction" if card.kind == "shu" else card.kind,
        "source_special_kind": card.kind,
        "pending": True,
        "reaction_pending": True,
        "prompt_id": effect["prompt_id"],
    }


def _activate_ling(room: Room, game: GameState, player, card_id: str) -> dict[str, Any]:
    hand_counts_before = {member.player_id: len(member.hand) for member in room.players}
    maximum = max(hand_counts_before.values())
    source_card = _consume_special(player, game, card_id, "ling")
    responders = [member.player_id for member in _ordered_players(room, game, player.player_id, include_source=True)]
    effect = {
        "type": "ling_reaction",
        "source_card_kind": "ling",
        "source_card_id": source_card.card_id,
        "source_player_id": player.player_id,
        "maximum": maximum,
        "responder_ids": responders,
        "responder_index": 0,
        "immune_player_ids": [],
        "last_card_candidate": not player.hand,
    }
    _open_effect(
        room,
        game,
        effect,
        kind=PromptKind.SUI_REACTION,
        responder_id=responders[0],
        legal_responses=["pass", "use_zuole", "evade"],
        default_action="pass",
    )
    return {"special_kind": "ling", "maximum": maximum, "pending": True, "prompt_id": effect["prompt_id"]}


def _finish_ling_reaction(room: Room, game: GameState, effect: dict[str, Any]) -> dict[str, Any]:
    maximum = effect["maximum"]
    draw_summary: dict[str, int] = {}
    for member in room.seats_in_order():
        count = 0 if member.player_id in effect["immune_player_ids"] else max(0, maximum - len(member.hand))
        if count:
            count = len(_draw_cards(game, member, count))
        draw_summary[member.player_id] = count
    _finish_effect_and_advance(room, game, effect)
    return {"special_kind": "ling", "draw_summary": draw_summary, "pending": game.current_prompt is not None}


def _respond_ling_reaction(room: Room, game: GameState, effect: dict[str, Any], player, response: str, payload: dict[str, Any]) -> dict[str, Any]:
    if response == "use_zuole":
        card = _card_from_hand(player, payload.get("card_id"))
        target_id = payload.get("target_player_id")
        if target_id not in {member.player_id for member in room.players}:
            raise SpecialEffectError("左乐目标无效", code="SPECIAL_TARGET_INVALID")
        if card.kind != "zuole":
            raise SpecialEffectError("请选择左乐牌", code="SPECIAL_SELECTION_INVALID")
        _consume_special(player, game, card.card_id, "zuole")
        if target_id not in effect["immune_player_ids"]:
            effect["immune_player_ids"].append(target_id)
    elif response == "evade":
        if player.player_id == effect["source_player_id"]:
            raise SpecialEffectError("岁牌来源不能规避自己发动的岁牌", code="SPECIAL_TARGET_INVALID")
        card = _card_from_hand(player, payload.get("card_id"))
        if card.category != CardCategory.SUI or not higher_sui_rank(card.kind, effect["source_card_kind"]):
            raise SpecialEffectError("需要选择更高阶的岁牌", code="SPECIAL_SELECTION_INVALID")
        _discard_cards(player, game, [card])
        if player.player_id not in effect["immune_player_ids"]:
            effect["immune_player_ids"].append(player.player_id)
    elif response != "pass":
        raise SpecialEffectError("该岁牌响应无效", code="ILLEGAL_PROMPT_RESPONSE")
    if not _next_effect_responder(
        room,
        game,
        effect,
        kind=PromptKind.SUI_REACTION,
        legal_responses=["pass", "use_zuole", "evade"],
        default_action="pass",
    ):
        return _finish_ling_reaction(room, game, effect)
    return {"special_kind": "ling", "pending": True, "prompt_id": effect["prompt_id"]}


def _activate_yi(
    room: Room,
    game: GameState,
    player,
    card_id: str,
    payload: dict[str, Any],
    *,
    immune_player_ids: list[str] | None = None,
) -> dict[str, Any]:
    pair_ids = payload.get("pair_card_ids")
    if not isinstance(pair_ids, list) or len(pair_ids) != 2:
        raise SpecialEffectError("易牌需要选择两张牌", code="BAD_CARD_SELECTION")
    pair = _cards_from_hand(player, pair_ids)
    if any(card.category != CardCategory.NUMBER or card.value is None for card in pair) or sum(card.value for card in pair) != 8:
        raise SpecialEffectError("易牌所选两张数字牌之和必须为 8", code="SPECIAL_SELECTION_INVALID")
    _consume_special(player, game, card_id, "yi")
    _discard_cards(player, game, pair)
    for member in room.seats_in_order():
        if member.player_id != player.player_id and member.player_id not in (immune_player_ids or []):
            _draw_cards(game, member, 1)
    return {"special_kind": "yi", "pending": False, "repeatable_this_turn": True}


def _shu_remainder_player_id(payload: dict[str, Any]) -> str | None:
    recipient_id = payload.get("remainder_recipient_id")
    legacy_player_id = payload.get("remainder_player_id")
    if recipient_id is not None and legacy_player_id is not None and recipient_id != legacy_player_id:
        raise SpecialEffectError("黍牌余牌接收者选择不一致", code="SPECIAL_TARGET_CONFLICT")
    return recipient_id if recipient_id is not None else legacy_player_id


def _activate_shu(
    room: Room,
    game: GameState,
    player,
    card_id: str,
    payload: dict[str, Any],
    *,
    immune_player_ids: list[str] | None = None,
) -> dict[str, Any]:
    remainder_player_id = _shu_remainder_player_id(payload)
    chosen_color = _color(payload.get("chosen_color"))
    recipients = [
        member
        for member in room.seats_in_order()
        if member.player_id != player.player_id and member.player_id not in (immune_player_ids or [])
    ]
    selected = [card for card in player.hand if card.color == chosen_color]
    if not recipients:
        _consume_special(player, game, card_id, "shu")
        return {"special_kind": "shu", "pending": False, "chosen_color": chosen_color.value}
    if len(selected) < len(recipients):
        raise SpecialEffectError("所选黍牌颜色的手牌不足", code="SPECIAL_TIMING_INVALID")
    base_count, remainder = divmod(len(selected), len(recipients))
    fewest = min(len(member.hand) for member in recipients)
    eligible_remainder = [member.player_id for member in recipients if len(member.hand) == fewest]
    if remainder and remainder_player_id is None and len(eligible_remainder) == 1:
        remainder_player_id = eligible_remainder[0]
    if remainder and remainder_player_id not in eligible_remainder:
        raise SpecialEffectError("黍牌余牌接收者无效", code="SPECIAL_TARGET_INVALID")
    _consume_special(player, game, card_id, "shu")
    for card in selected:
        player.hand.remove(card)
    for member in recipients:
        for _ in range(base_count):
            member.hand.append(selected.pop(0))
    if remainder:
        remainder_player = room.player(remainder_player_id)
        while selected:
            remainder_player.hand.append(selected.pop(0))
    return {"special_kind": "shu", "pending": False, "chosen_color": chosen_color.value}


def _activate_ji(room: Room, game: GameState, player, card_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    chosen_color = _color(payload.get("chosen_color"))
    source_card = _consume_special(player, game, card_id, "ji")
    responders = [member.player_id for member in _ordered_players(room, game, player.player_id, include_source=True)]
    effect = {
        "type": "ji",
        "source_card_kind": "ji",
        "source_card_id": source_card.card_id,
        "source_player_id": player.player_id,
        "chosen_color": chosen_color.value,
        "responder_ids": responders,
        "responder_index": 0,
        "total_discarded": 0,
        "immune_player_ids": [],
        "last_card_candidate": not player.hand,
    }
    _open_effect(
        room,
        game,
        effect,
        kind=PromptKind.SUI_PLAYER_RESPONSE,
        responder_id=responders[0],
        legal_responses=["submit_cards", "pass", "use_xi"],
        default_action="pass",
    )
    return {"special_kind": "ji", "pending": True, "prompt_id": effect["prompt_id"]}


def _validate_four_color_payment(player, card_ids: Any) -> list[Card]:
    if not isinstance(card_ids, list) or len(card_ids) != 4:
        raise SpecialEffectError("需要选择四张支付牌", code="SPECIAL_SELECTION_INVALID")
    cards = _cards_from_hand(player, card_ids)
    colors = {card.color for card in cards}
    if None in colors or len(colors) != 4:
        raise SpecialEffectError("支付牌必须包含四种不同颜色", code="SPECIAL_SELECTION_INVALID")
    return cards


def _activate_yu(room: Room, game: GameState, player, card_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    payment = _validate_four_color_payment(player, payload.get("payment_card_ids"))
    source_card = _consume_special(player, game, card_id, "yu")
    _discard_cards(player, game, payment)
    responders = [member.player_id for member in _ordered_players(room, game, player.player_id, include_source=False)]
    effect = {
        "type": "yu",
        "source_card_kind": "yu",
        "source_card_id": source_card.card_id,
        "source_player_id": player.player_id,
        "responder_ids": responders,
        "responder_index": 0,
        "used_colors": [],
        "phase": "responders",
        "immune_player_ids": [],
        "last_card_candidate": not player.hand,
    }
    _open_effect(
        room,
        game,
        effect,
        kind=PromptKind.SUI_PLAYER_RESPONSE,
        responder_id=responders[0],
        legal_responses=["submit_cards", "decline", "use_xi"],
        default_action="decline",
    )
    return {"special_kind": "yu", "pending": True, "prompt_id": effect["prompt_id"]}


def _activate_zuole(room: Room, game: GameState, player, card_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if game.current_prompt is None:
        raise SpecialEffectError("左乐只能在岁牌效果生效期间使用", code="SPECIAL_TIMING_INVALID")
    effect = _current_effect(game, game.current_prompt.prompt_id)
    if effect.get("source_card_kind") not in SPECIAL_RULES:
        raise SpecialEffectError("左乐只能在岁牌效果生效期间使用", code="SPECIAL_TIMING_INVALID")
    target_player_id = payload.get("target_player_id")
    if target_player_id not in {member.player_id for member in room.players}:
        raise SpecialEffectError("左乐目标无效", code="SPECIAL_TARGET_INVALID")
    _consume_special(player, game, card_id, "zuole")
    immune = effect.setdefault("immune_player_ids", [])
    if target_player_id not in immune:
        immune.append(target_player_id)
    return {"special_kind": "zuole", "pending": False, "target_player_id": target_player_id}


def _activate_nian(room: Room, game: GameState, player, card_id: str) -> dict[str, Any]:
    source_card = _consume_special(player, game, card_id, "nian")
    game.special_state["nian_rules_enabled"] = True
    state = _nian_state(game)
    state["enabled_by_player_id"] = player.player_id
    state["enabled_source_card_id"] = source_card.card_id
    opened = open_nian_turn_end_discard(
        room,
        game,
        player,
        last_played_card=source_card,
        advance_steps=1,
    )
    game.special_state["nian_rules_enabled"] = True
    return {"special_kind": "nian", "pending": opened, "nian_rules_enabled": True}


def _open_sui_xiang_effect(
    room: Room,
    game: GameState,
    player,
    source_card: Card,
    *,
    seen_event_id: str,
    seen_source: str,
    last_card_candidate: bool = False,
) -> dict[str, Any]:
    revealed: Card | None = None
    while revealed is None:
        try:
            _reshuffle(game)
            candidate = game.deck.pop()
        except SpecialEffectError as exc:
            if exc.code == "EMPTY_DECK":
                # 牌库彻底耗尽，翻不出有色牌：效果失效并推进回合
                _advance_turn(room, game)
                return {"special_kind": "sui_xiang", "pending": False, "reveal_failed": True}
            raise
        if candidate.color is None:
            game.discard_pile.append(candidate)
        else:
            revealed = candidate
    game.reveal_area.append(revealed)
    responders = [
        player.player_id,
        *[
            member.player_id
            for member in _ordered_players(room, game, player.player_id, include_source=False)
        ],
    ]
    effect = {
        "type": "sui_xiang",
        "source_card_kind": "sui_xiang",
        "source_card_id": source_card.card_id,
        "source_player_id": player.player_id,
        "seen_event_id": seen_event_id,
        "seen_source": seen_source,
        "revealed_card_id": revealed.card_id,
        "required_color": revealed.color.value,
        "responder_ids": responders,
        "responder_index": 0,
        "immune_player_ids": [],
        "last_card_candidate": last_card_candidate,
    }
    _open_effect(
        room,
        game,
        effect,
        kind=PromptKind.SUI_PLAYER_RESPONSE,
        responder_id=responders[0],
        legal_responses=["submit_cards", "draw_four", "use_xi"],
        default_action="draw_four",
    )
    return {"special_kind": "sui_xiang", "pending": True, "required_color": revealed.color.value}


def _activate_sui_xiang(room: Room, game: GameState, player, card_id: str) -> dict[str, Any]:
    source_card = _consume_special(player, game, card_id, "sui_xiang")
    event_ids = game.special_state.setdefault("sui_xiang_seen_event_ids", [])
    event_id = f"activate:{source_card.card_id}"
    if event_id not in event_ids:
        event_ids.append(event_id)
    return _open_sui_xiang_effect(
        room,
        game,
        player,
        source_card,
        seen_event_id=event_id,
        seen_source="activation",
        last_card_candidate=not player.hand,
    )


def _seen_event_distance(room: Room, game: GameState, source_player_id: str, observer_player_id: str) -> int:
    seats = room.seats_in_order()
    source_index = next(index for index, member in enumerate(seats) if member.player_id == source_player_id)
    observer_index = next(index for index, member in enumerate(seats) if member.player_id == observer_player_id)
    return (observer_index - source_index) * game.direction % len(seats)


def _queue_seen_event(
    room: Room,
    game: GameState,
    *,
    observer_player_id: str,
    owner_player_id: str | None,
    event_id: str,
    source: str,
    card_id: str,
) -> None:
    source_player_id = owner_player_id or observer_player_id
    queue = game.special_state.setdefault("pending_seen_events", [])
    sequence = len(queue)
    queue.append(
        {
            "observer_player_id": observer_player_id,
            "owner_player_id": owner_player_id,
            "source_player_id": source_player_id,
            "event_id": event_id,
            "card_id": card_id,
            "source": source,
            "sequence": sequence,
            "direction_distance": _seen_event_distance(room, game, source_player_id, observer_player_id),
        }
    )
    queue.sort(key=lambda item: (item.get("direction_distance", 10**9), item.get("sequence", 10**9)))


def _card_in_public_zones(game: GameState, card_id: str) -> Card | None:
    for card in [*game.discard_pile, *game.reveal_area, *game.deck]:
        if card.card_id == card_id:
            return card
    return None


def _drain_seen_events(room: Room, game: GameState) -> bool:
    """Open the next queued 'seen' event after the current effect is complete."""
    if game.current_prompt is not None:
        return False
    queue = game.special_state.setdefault("pending_seen_events", [])
    while queue:
        event = queue.pop(0)
        card_id = event.get("card_id")
        card = _card_in_public_zones(game, card_id) if card_id else None
        if card is None:
            continue
        if card in game.reveal_area:
            game.reveal_area.remove(card)
        if card not in game.discard_pile:
            game.discard_pile.append(card)
        observer = room.player(event["observer_player_id"])
        return _open_sui_xiang_effect(
            room,
            game,
            observer,
            card,
            seen_event_id=event["event_id"],
            seen_source=event["source"],
            last_card_candidate=False,
        ) is not None
    return False


def trigger_seen_card(
    room: Room,
    *,
    observer_player_id: str,
    owner_player_id: str | None,
    card: Card,
    event_id: str,
    source: str,
    event_source_player_id: str | None = None,
) -> dict[str, Any] | None:
    game = _game(room)
    if card.kind != "sui_xiang":
        return None
    event_ids = game.special_state.setdefault("sui_xiang_seen_event_ids", [])
    if event_id in event_ids:
        return None
    observer = room.player(observer_player_id)
    if owner_player_id is not None:
        owner = room.player(owner_player_id)
        if card in owner.hand:
            owner.hand.remove(card)
    if card in game.reveal_area:
        game.reveal_area.remove(card)
    if card not in game.discard_pile:
        game.discard_pile.append(card)
    event_ids.append(event_id)
    if game.current_prompt is not None:
        if card in game.discard_pile:
            game.discard_pile.remove(card)
        if card not in game.reveal_area:
            game.reveal_area.append(card)
        _queue_seen_event(
            room,
            game,
            observer_player_id=observer_player_id,
            owner_player_id=event_source_player_id or owner_player_id,
            event_id=event_id,
            source=source,
            card_id=card.card_id,
        )
        return {"special_kind": "sui_xiang", "pending": True, "queued": True, "event_id": event_id}
    return _open_sui_xiang_effect(
        room,
        game,
        observer,
        card,
        seen_event_id=event_id,
        seen_source=source,
        last_card_candidate=False,
    )


def _hand_colors(player) -> set[CardColor]:
    return {card.color for card in player.hand if card.color is not None}


def _draw_until_four_colors(game: GameState, player) -> int:
    drawn_count = 0
    while len(_hand_colors(player)) < 4:
        drew = _draw_cards(game, player, 1)
        if not drew:
            break
        drawn_count += 1
    return drawn_count


def _activate_chongyue(
    room: Room,
    game: GameState,
    player,
    card_id: str,
    *,
    immune_player_ids: list[str] | None = None,
) -> dict[str, Any]:
    source_card = _consume_special(player, game, card_id, "chongyue")
    responders = [member.player_id for member in _ordered_players(room, game, player.player_id, include_source=False)]
    drawn_until_four: dict[str, int] = {}
    for member in room.seats_in_order():
        drawn_until_four[member.player_id] = (
            0 if member.player_id in (immune_player_ids or []) else _draw_until_four_colors(game, member)
        )
    effect = {
        "type": "chongyue",
        "source_card_kind": "chongyue",
        "source_card_id": source_card.card_id,
        "source_player_id": player.player_id,
        "responder_ids": responders,
        "responder_index": 0,
        "displayed_colors": {
            member.player_id: (
                []
                if member.player_id in (immune_player_ids or [])
                else sorted(color.value for color in _hand_colors(member))
            )
            for member in room.seats_in_order()
        },
        "drawn_until_four": drawn_until_four,
        "immune_player_ids": list(immune_player_ids or []),
        "last_card_candidate": not player.hand,
    }
    _open_effect(
        room,
        game,
        effect,
        kind=PromptKind.CHONGYUE_CHALLENGE,
        responder_id=responders[0],
        legal_responses=["challenge", "decline_challenge"],
        default_action="decline_challenge",
    )
    return {
        "special_kind": "chongyue",
        "pending": True,
        "displayed_color_counts": {key: len(value) for key, value in effect["displayed_colors"].items()},
        "drawn_until_four": drawn_until_four,
    }


def _activate_wang(
    room: Room,
    game: GameState,
    player,
    card_id: str,
    payload: dict[str, Any],
    *,
    immune_player_ids: list[str] | None = None,
) -> dict[str, Any]:
    target_player_id = payload.get("target_player_id")
    if target_player_id != game.current_player_id or target_player_id == player.player_id:
        raise SpecialEffectError("望牌目标必须是当前无法出牌的玩家", code="SPECIAL_TARGET_INVALID")
    target = room.player(target_player_id)
    top = game.discard_pile[-1] if game.discard_pile else None
    has_play = any(
        card.category != CardCategory.SUI
        and can_play_card(top_card=top, current_color=game.current_color, hand=target.hand, candidate=card).allowed
        for card in target.hand
    )
    if has_play:
        raise SpecialEffectError("望牌只能对当前无牌可出的玩家使用", code="SPECIAL_TIMING_INVALID")
    source_card = _consume_special(player, game, card_id, "wang")
    if target.player_id in (immune_player_ids or []):
        return {
            "special_kind": "wang",
            "pending": False,
            "controlled_player_id": target.player_id,
            "evaded": True,
        }
    effect = {
        "type": "wang",
        "source_card_kind": "wang",
        "source_card_id": source_card.card_id,
        "source_player_id": player.player_id,
        "controller_player_id": player.player_id,
        "controlled_player_id": target.player_id,
        "immune_player_ids": list(immune_player_ids or []),
        "last_card_candidate": not player.hand,
    }
    _open_effect(
        room,
        game,
        effect,
        kind=PromptKind.SUI_PLAYER_RESPONSE,
        responder_id=player.player_id,
        legal_responses=["control_play", "control_pass"],
        default_action="control_pass",
    )
    return {"special_kind": "wang", "pending": True, "controlled_player_id": target.player_id}


def _activate_fuzhou(room: Room, game: GameState, player, card_id: str) -> dict[str, Any]:
    card = _card_from_hand(player, card_id)
    if card.kind != "fuzhou":
        raise SpecialEffectError("需要选择符咒牌", code="NOT_SPECIAL_CARD")
    player.hand.remove(card)
    game.reveal_area.append(card)
    responders = [member.player_id for member in _ordered_players(room, game, player.player_id, include_source=False)]
    effect = {
        "type": "fuzhou",
        "source_card_kind": "fuzhou",
        "source_card_id": card.card_id,
        "source_player_id": player.player_id,
        "responder_ids": responders,
        "responder_index": 0,
        "immune_player_ids": [],
        "last_card_candidate": False,
    }
    _open_effect(
        room,
        game,
        effect,
        kind=PromptKind.SUI_PLAYER_RESPONSE,
        responder_id=responders[0],
        legal_responses=["give_card", "decline"],
        default_action="decline",
    )
    return {"special_kind": "fuzhou", "pending": True}


def _dispatch_special_activation(
    room: Room,
    game: GameState,
    player,
    card: Card,
    payload: dict[str, Any],
    *,
    immune_player_ids: list[str] | None = None,
) -> dict[str, Any]:
    card_id = card.card_id
    if card.kind == "ling":
        return _activate_ling(room, game, player, card_id)
    if card.kind == "yi":
        return _activate_yi(room, game, player, card_id, payload, immune_player_ids=immune_player_ids)
    if card.kind == "shu":
        return _activate_shu(room, game, player, card_id, payload, immune_player_ids=immune_player_ids)
    if card.kind == "ji":
        return _activate_ji(room, game, player, card_id, payload)
    if card.kind == "yu":
        return _activate_yu(room, game, player, card_id, payload)
    if card.kind == "zuole":
        return _activate_zuole(room, game, player, card_id, payload)
    if card.kind == "nian":
        return _activate_nian(room, game, player, card_id)
    if card.kind == "sui_xiang":
        return _activate_sui_xiang(room, game, player, card_id)
    if card.kind == "chongyue":
        return _activate_chongyue(room, game, player, card_id, immune_player_ids=immune_player_ids)
    if card.kind == "wang":
        return _activate_wang(room, game, player, card_id, payload, immune_player_ids=immune_player_ids)
    if card.kind == "fuzhou":
        return _activate_fuzhou(room, game, player, card_id)
    if card.kind == "xi":
        raise SpecialEffectError("夕牌只能在被动响应窗口中使用", code="SPECIAL_TIMING_INVALID")
    raise SpecialEffectError("缺少该岁牌的结算规则", code="SPECIAL_RESOLVER_MISSING")


def activate_special(room: Room, player_id: str, payload: dict[str, Any], *, controlled_by: str | None = None) -> dict[str, Any]:
    game = _game(room)
    player = room.player(player_id)
    card_id = payload.get("card_id")
    card = _card_from_hand(player, card_id)
    if card.kind not in SPECIAL_RULES or card.kind == "cannot":
        raise SpecialEffectError("该牌不能从手牌发动", code="NOT_SPECIAL_CARD")
    active_kinds = {"ji", "yu", "yi", "shu", "chongyue", "ling"}
    if card.kind in active_kinds and game.current_player_id != player.player_id and controlled_by is None:
        raise SpecialEffectError("该特殊牌当前不能使用", code="SPECIAL_TIMING_INVALID")
    if game.current_prompt is not None and card.kind != "zuole":
        raise SpecialEffectError("请先处理当前待响应操作", code="PROMPT_PENDING")
    if card.kind in PRE_EFFECT_REACTION_KINDS:
        return _open_pre_effect_reaction(
            room,
            game,
            player,
            card,
            payload,
            controlled_by=controlled_by,
        )
    return _dispatch_special_activation(room, game, player, card, payload)


def activate_drawn_special(room: Room, player_id: str, drawn_cards: list[Card]) -> dict[str, Any] | None:
    game = _game(room)
    if game.current_prompt is not None:
        return None
    player = room.player(player_id)
    for card in drawn_cards:
        if card.kind == "fuzhou":
            return _activate_fuzhou(room, game, player, card.card_id)
        if card.kind == "sui_xiang":
            return trigger_seen_card(
                room,
                observer_player_id=player.player_id,
                owner_player_id=player.player_id,
                card=card,
                event_id=f"draw:{card.card_id}",
                source="draw",
            )
    return None


def _consume_xi(player, game: GameState) -> Card:
    xi = next((card for card in player.hand if card.kind == "xi"), None)
    if xi is None:
        raise SpecialEffectError("响应者手中没有所选夕牌", code="CARD_NOT_IN_HAND")
    player.hand.remove(xi)
    game.discard_pile.append(xi)
    return xi


def _consume_rank_evasion(game: GameState, effect: dict[str, Any], player, card_id: str | None) -> None:
    if player.player_id == effect.get("source_player_id"):
        raise SpecialEffectError("岁牌来源不能规避自己发动的岁牌", code="SPECIAL_TARGET_INVALID")
    card = _card_from_hand(player, card_id)
    if card.category != CardCategory.SUI or not higher_sui_rank(card.kind, effect["source_card_kind"]):
        raise SpecialEffectError("需要选择更高阶的岁牌", code="SPECIAL_SELECTION_INVALID")
    _discard_cards(player, game, [card])
    immune = effect.setdefault("immune_player_ids", [])
    if player.player_id not in immune:
        immune.append(player.player_id)


def _finish_shu_activation(
    room: Room,
    game: GameState,
    player,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    previous_pending = game.uno_pending_player_id
    if previous_pending is not None and previous_pending != player.player_id:
        game.uno_pending_player_id = None
        game.uno_catchable_by = []
        game.last_uno_event = {"type": "window_closed", "player_id": previous_pending}

    declared = bool(payload.get("declare_uno", False))
    uno_declared = False
    if len(player.hand) == 1:
        if declared:
            game.uno_pending_player_id = None
            game.uno_catchable_by = []
            game.last_uno_event = {"type": "declared", "player_id": player.player_id}
            uno_declared = True
        else:
            game.uno_pending_player_id = player.player_id
            game.uno_catchable_by = [
                member.player_id for member in room.seats_in_order() if member.player_id != player.player_id
            ]
            game.last_uno_event = {"type": "pending", "player_id": player.player_id}
    elif game.uno_pending_player_id == player.player_id:
        game.uno_pending_player_id = None
        game.uno_catchable_by = []

    if not player.hand:
        if not open_has_sui_challenge(
            room,
            player.player_id,
            finish_player_id=player.player_id,
        ):
            _finish_game_state(room, game, player.player_id)
    elif not open_has_sui_challenge(room, player.player_id):
        _advance_turn(room, game)

    return {
        **result,
        "uno_declared": uno_declared,
        "uno_pending_player_id": game.uno_pending_player_id,
    }


def _finish_pre_effect_reaction(room: Room, game: GameState, effect: dict[str, Any]) -> dict[str, Any]:
    source = room.player(effect["source_player_id"])
    source_card = _card_from_hand(source, effect["source_card_id"])
    parent_wang_source_card_id = effect.get("parent_wang_source_card_id")
    payload = dict(effect.get("activation_payload") or {})
    immune_player_ids = list(effect.get("immune_player_ids") or [])
    _close_effect(game, effect)
    result = _dispatch_special_activation(
        room,
        game,
        source,
        source_card,
        payload,
        immune_player_ids=immune_player_ids,
    )
    if source_card.kind == "shu" and parent_wang_source_card_id is None:
        result = _finish_shu_activation(room, game, source, payload, result)
    if game.current_prompt is not None:
        child = _current_effect(game, game.current_prompt.prompt_id)
        child["last_card_candidate"] = bool(
            child.get("last_card_candidate") or effect.get("last_card_candidate")
        )
        if parent_wang_source_card_id:
            child["parent_wang_source_card_id"] = parent_wang_source_card_id
        return result
    if parent_wang_source_card_id:
        _advance_turn(room, game)
        parent_result = _resume_wang_parent(room, game, parent_wang_source_card_id)
        return {**result, **parent_result, "nested_kind": source_card.kind}
    return result


def _respond_pre_effect_reaction(
    room: Room,
    game: GameState,
    effect: dict[str, Any],
    player,
    response: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if response == "use_zuole":
        target_player_id = payload.get("target_player_id")
        if target_player_id not in {member.player_id for member in room.players}:
            raise SpecialEffectError("左乐目标无效", code="SPECIAL_TARGET_INVALID")
        card = _card_from_hand(player, payload.get("card_id"))
        if card.kind != "zuole":
            raise SpecialEffectError("请选择左乐牌", code="SPECIAL_SELECTION_INVALID")
        _consume_special(player, game, card.card_id, "zuole")
        immune = effect.setdefault("immune_player_ids", [])
        if target_player_id not in immune:
            immune.append(target_player_id)
    elif response == "evade":
        if player.player_id not in effect.get("affected_player_ids", []):
            raise SpecialEffectError("该玩家不受此岁牌影响", code="SPECIAL_TARGET_INVALID")
        _consume_rank_evasion(game, effect, player, payload.get("card_id"))
    elif response != "pass":
        raise SpecialEffectError("该岁牌响应无效", code="ILLEGAL_PROMPT_RESPONSE")
    if not _next_effect_responder(
        room,
        game,
        effect,
        kind=PromptKind.SUI_REACTION,
        legal_responses=["pass", "use_zuole", "evade"],
        default_action="pass",
    ):
        return _finish_pre_effect_reaction(room, game, effect)
    return {
        "special_kind": effect["source_card_kind"],
        "pending": True,
        "reaction_pending": True,
        "prompt_id": effect["prompt_id"],
    }


def _respond_ji(room: Room, game: GameState, effect: dict[str, Any], player, response: str, payload: dict[str, Any]) -> dict[str, Any]:
    source_player_id = effect["source_player_id"]
    count = 0
    if response == "evade":
        _consume_rank_evasion(game, effect, player, payload.get("card_id"))
        response = "pass"
    if player.player_id not in effect.get("immune_player_ids", []):
        if response == "use_xi":
            _consume_xi(player, game)
            count = 1
        elif response == "submit_cards":
            card_ids = payload.get("card_ids", [])
            if not isinstance(card_ids, list):
                raise SpecialEffectError("card_ids 必须是牌号列表", code="BAD_CARD_SELECTION")
            cards = _cards_from_hand(player, card_ids)
            chosen_color = CardColor(effect["chosen_color"])
            if any(card.color != chosen_color for card in cards):
                raise SpecialEffectError("所选牌必须与声明颜色一致", code="SPECIAL_SELECTION_INVALID")
            if player.player_id == source_player_id and len(cards) > effect["total_discarded"]:
                raise SpecialEffectError("所选牌数量超过忌牌可弃置上限", code="SPECIAL_SELECTION_INVALID")
            _discard_cards(player, game, cards)
            count = len(cards)
        elif response != "pass":
            raise SpecialEffectError("该忌牌响应无效", code="ILLEGAL_PROMPT_RESPONSE")
    if player.player_id != source_player_id:
        effect["total_discarded"] += count
    if not _next_effect_responder(
        room,
        game,
        effect,
        kind=PromptKind.SUI_PLAYER_RESPONSE,
        legal_responses=["submit_cards", "pass", "use_xi"],
        default_action="pass",
    ):
        _finish_effect_and_advance(room, game, effect)
    return {"special_kind": "ji", "discarded_count": count, "pending": game.current_prompt is not None}


def _respond_yu(room: Room, game: GameState, effect: dict[str, Any], player, response: str, payload: dict[str, Any]) -> dict[str, Any]:
    if effect["phase"] == "restart":
        if player.player_id != effect["source_player_id"]:
            raise SpecialEffectError("只有余牌来源可以重新开始结算", code="NOT_PROMPT_RESPONDER")
        if response == "stop":
            _finish_effect_and_advance(room, game, effect)
            return {"special_kind": "yu", "pending": False}
        if response != "restart":
            raise SpecialEffectError("余牌重新开始响应无效", code="ILLEGAL_PROMPT_RESPONSE")
        payment = _validate_four_color_payment(player, payload.get("payment_card_ids"))
        _discard_cards(player, game, payment)
        effect["used_colors"] = []
        effect["responder_index"] = effect["declining_index"]
        effect["phase"] = "responders"
        responder_id = effect["responder_ids"][effect["responder_index"]]
        _replace_prompt(
            room,
            game,
            effect,
            kind=PromptKind.SUI_PLAYER_RESPONSE,
            responder_id=responder_id,
            legal_responses=["submit_cards", "decline", "use_xi"],
            default_action="decline",
        )
        return {"special_kind": "yu", "pending": True}

    if response == "evade":
        _consume_rank_evasion(game, effect, player, payload.get("card_id"))
    if player.player_id in effect.get("immune_player_ids", []):
        if not _next_effect_responder(
            room, game, effect,
            kind=PromptKind.SUI_PLAYER_RESPONSE,
            legal_responses=["submit_cards", "decline", "use_xi"],
            default_action="decline",
        ):
            _finish_effect_and_advance(room, game, effect)
        return {"special_kind": "yu", "pending": game.current_prompt is not None, "evaded": True}
    if response == "decline":
        effect["phase"] = "restart"
        effect["declining_index"] = effect["responder_index"]
        _replace_prompt(
            room,
            game,
            effect,
            kind=PromptKind.SUI_PLAYER_RESPONSE,
            responder_id=effect["source_player_id"],
            legal_responses=["restart", "stop"],
            default_action="stop",
        )
        return {"special_kind": "yu", "pending": True, "restart_available": True}
    if response == "use_xi":
        _consume_xi(player, game)
        chosen_color = _color(payload.get("as_color"))
    elif response == "submit_cards":
        card_ids = payload.get("card_ids", [])
        if not isinstance(card_ids, list) or len(card_ids) != 1:
            raise SpecialEffectError("余牌响应需要选择一张牌", code="SPECIAL_SELECTION_INVALID")
        card = _cards_from_hand(player, card_ids)[0]
        if card.color is None:
            raise SpecialEffectError("余牌响应必须选择有颜色的牌", code="SPECIAL_SELECTION_INVALID")
        chosen_color = card.color
        _discard_cards(player, game, [card])
    else:
        raise SpecialEffectError("余牌响应无效", code="ILLEGAL_PROMPT_RESPONSE")
    if chosen_color.value in effect["used_colors"]:
        raise SpecialEffectError("该颜色已经用于余牌响应", code="SPECIAL_SELECTION_INVALID")
    effect["used_colors"].append(chosen_color.value)
    if not _next_effect_responder(
        room,
        game,
        effect,
        kind=PromptKind.SUI_PLAYER_RESPONSE,
        legal_responses=["submit_cards", "decline", "use_xi"],
        default_action="decline",
    ):
        _finish_effect_and_advance(room, game, effect)
    return {"special_kind": "yu", "pending": game.current_prompt is not None}


def _respond_sui_xiang(room: Room, game: GameState, effect: dict[str, Any], player, response: str, payload: dict[str, Any]) -> dict[str, Any]:
    required_color = CardColor(effect["required_color"])
    if response == "evade":
        _consume_rank_evasion(game, effect, player, payload.get("card_id"))
    if player.player_id not in effect.get("immune_player_ids", []):
        if response == "use_xi":
            _consume_xi(player, game)
        elif response == "submit_cards":
            card_ids = payload.get("card_ids", [])
            if not isinstance(card_ids, list) or len(card_ids) != 1:
                raise SpecialEffectError("岁相响应需要选择一张牌", code="SPECIAL_SELECTION_INVALID")
            card = _cards_from_hand(player, card_ids)[0]
            if card.color != required_color:
                raise SpecialEffectError("所选牌与亮出的颜色不一致", code="SPECIAL_SELECTION_INVALID")
            _discard_cards(player, game, [card])
        elif response == "draw_four":
            if any(card.color == required_color for card in player.hand):
                raise SpecialEffectError("手中有同色牌，不能选择摸 4", code="SPECIAL_SELECTION_INVALID")
            _draw_cards(game, player, 4)
        else:
            raise SpecialEffectError("岁相响应无效", code="ILLEGAL_PROMPT_RESPONSE")
    if not _next_effect_responder(
        room,
        game,
        effect,
        kind=PromptKind.SUI_PLAYER_RESPONSE,
        legal_responses=["submit_cards", "draw_four", "use_xi"],
        default_action="draw_four",
    ):
        revealed = next(card for card in game.reveal_area if card.card_id == effect["revealed_card_id"])
        game.reveal_area.remove(revealed)
        game.discard_pile.append(revealed)
        _finish_effect_and_advance(room, game, effect)
    return {"special_kind": "sui_xiang", "pending": game.current_prompt is not None}


def _respond_chongyue(room: Room, game: GameState, effect: dict[str, Any], player, response: str) -> dict[str, Any]:
    result = "declined"
    if response == "challenge":
        source = room.player(effect["source_player_id"])
        if len(_hand_colors(source)) >= 4:
            _draw_cards(game, player, 4)
            result = "challenge_failed"
        else:
            while len(_hand_colors(source)) < 4:
                drew = _draw_cards(game, source, 1)
                if not drew:
                    break
            result = "challenge_succeeded"
            _finish_effect_and_advance(room, game, effect)
            return {"special_kind": "chongyue", "challenge_result": result, "pending": False}
    elif response != "decline_challenge":
        raise SpecialEffectError("重月响应无效", code="ILLEGAL_PROMPT_RESPONSE")
    if not _next_effect_responder(
        room,
        game,
        effect,
        kind=PromptKind.CHONGYUE_CHALLENGE,
        legal_responses=["challenge", "decline_challenge"],
        default_action="decline_challenge",
    ):
        _finish_effect_and_advance(room, game, effect)
    return {"special_kind": "chongyue", "challenge_result": result, "pending": game.current_prompt is not None}


def _respond_nian_turn_end_discard(
    room: Room,
    game: GameState,
    effect: dict[str, Any],
    player,
    response: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if response != "discard_card":
        raise SpecialEffectError("年牌回合结束响应无效", code="ILLEGAL_PROMPT_RESPONSE")
    card = _card_from_hand(player, payload.get("card_id"))
    _discard_cards(player, game, [card])
    _close_effect(game, effect)
    last_played = effect.get("last_played")
    last_card = None
    if isinstance(last_played, dict) and last_played.get("card_id"):
        last_card = Card(
            card_id=last_played["card_id"],
            category=CardCategory.NUMBER if last_played.get("value") is not None else CardCategory.SUI,
            kind=last_played.get("kind") or "number",
            asset_key=last_played.get("kind") or "nian_last_played",
            color=CardColor(last_played["color"]) if last_played.get("color") is not None else None,
            value=last_played.get("value"),
        )
    _maybe_open_nian_claim_or_advance(
        room,
        game,
        effect["source_player_id"],
        last_card,
        int(effect.get("advance_steps", 1)),
        effect.get("parent_wang_source_card_id"),
    )
    return {"special_kind": "nian", "discarded_card_id": card.card_id, "pending": game.current_prompt is not None}


def _respond_nian_claim(room: Room, game: GameState, effect: dict[str, Any], player, response: str, payload: dict[str, Any]) -> dict[str, Any]:
    if response == "chi":
        if effect["responder_index"] != 0:
            raise SpecialEffectError("只有下一位玩家可以吃牌", code="SPECIAL_TARGET_INVALID")
        cards = _selected_claim_cards(player, payload, 2)
        _validate_nian_chi(effect, cards)
    elif response == "peng":
        cards = _selected_claim_cards(player, payload, 2)
        _validate_nian_peng_or_gang(effect, cards, "peng")
    elif response == "gang":
        cards = _selected_claim_cards(player, payload, 3)
        _validate_nian_peng_or_gang(effect, cards, "gang")
    elif response == "pass":
        cards = []
    else:
        raise SpecialEffectError("年牌吃碰杠响应无效", code="ILLEGAL_PROMPT_RESPONSE")
    if cards:
        effect.setdefault("claims", []).append(
            {
                "claim_type": response,
                "player_id": player.player_id,
                "card_ids": [card.card_id for card in cards],
                "direction_distance": effect["responder_index"],
            }
        )
    if not _next_effect_responder(
        room,
        game,
        effect,
        kind=PromptKind.NIAN_CLAIM_WINDOW,
        legal_responses=["chi", "peng", "gang", "pass"],
        default_action="pass",
    ):
        _resolve_nian_claims(room, game, effect)
    return {"special_kind": "nian", "claim": response, "pending": game.current_prompt is not None, "current_player_id": game.current_player_id}


def _respond_wang(room: Room, game: GameState, effect: dict[str, Any], player, response: str, payload: dict[str, Any]) -> dict[str, Any]:
    if response == "control_play":
        controlled = room.player(effect["controlled_player_id"])
        selected_id = payload.get("card_id")
        owner = controlled if any(card.card_id == selected_id for card in controlled.hand) else player
        card = _card_from_hand(owner, selected_id)
        if card.category == CardCategory.FIELD:
            raise SpecialEffectError("无法控制所选牌", code="SPECIAL_SELECTION_INVALID")
        if card.category == CardCategory.SUI:
            return _control_wang_sui(room, game, effect, player, owner, card, payload)
        top = game.discard_pile[-1] if game.discard_pile else None
        check = can_play_card(top_card=top, current_color=game.current_color, hand=owner.hand, candidate=card)
        if not check.allowed:
            raise SpecialEffectError("所控的牌当前不能打出", code="ILLEGAL_PLAY")
        chosen_color = _color(payload.get("chosen_color")) if check.requires_color_choice else None
        previous_color = game.current_color
        hand_before_play = list(owner.hand)
        owner.hand.remove(card)
        game.discard_pile.append(card)
        game.current_color = card.color or chosen_color or game.current_color
        if card.kind == "wild_draw_four":
            target = _next_player(room, game)
            child = {
                "type": "wang_wild_draw_four_challenge",
                "source_player_id": owner.player_id,
                "source_card_id": card.card_id,
                "target_player_id": target.player_id,
                "challenge_result": wild_draw_four_challenge_result(previous_color, hand_before_play),
                "parent_wang_source_card_id": effect["source_card_id"],
            }
            game.current_player_id = target.player_id
            game.current_prompt = None
            _open_effect(
                room,
                game,
                child,
                kind=PromptKind.SUI_PLAYER_RESPONSE,
                responder_id=target.player_id,
                legal_responses=["challenge", "decline_challenge"],
                default_action="decline_challenge",
            )
            return {"special_kind": "wang", "pending": True, "nested_kind": "wild_draw_four"}
        steps = 1
        if card.kind == "skip":
            steps = 2
        elif card.kind == "reverse":
            game.direction *= -1
            steps = 2 if len(room.players) == 2 else 1
        elif card.kind == "draw_two":
            target = _next_player(room, game)
            _draw_cards(game, target, 2)
            steps = 2
        _advance_turn(room, game, steps)
    elif response == "control_pass":
        _advance_turn(room, game)
    else:
        raise SpecialEffectError("望牌响应无效", code="ILLEGAL_PROMPT_RESPONSE")
    if game.current_player_id == effect["controller_player_id"]:
        _close_effect(game, effect)
        if effect.get("parent_wang_source_card_id"):
            return _resume_wang_parent(room, game, effect["parent_wang_source_card_id"])
        return {"special_kind": "wang", "pending": False}
    effect["controlled_player_id"] = game.current_player_id
    _replace_prompt(
        room,
        game,
        effect,
        kind=PromptKind.SUI_PLAYER_RESPONSE,
        responder_id=effect["controller_player_id"],
        legal_responses=["control_play", "control_pass"],
        default_action="control_pass",
    )
    return {"special_kind": "wang", "pending": True, "controlled_player_id": game.current_player_id}


def _control_wang_sui(room: Room, game: GameState, parent: dict[str, Any], controller, owner, card: Card, payload: dict[str, Any]) -> dict[str, Any]:
    if card.kind in {"xi", "zuole"}:
        raise SpecialEffectError("该岁牌需要在响应窗口中使用", code="SPECIAL_TIMING_INVALID")
    parent_prompt = game.current_prompt
    game.current_prompt = None
    try:
        result = activate_special(room, owner.player_id, {**payload, "card_id": card.card_id}, controlled_by=controller.player_id)
    except Exception:
        game.current_prompt = parent_prompt
        raise
    if game.current_prompt is not None:
        child = _current_effect(game, game.current_prompt.prompt_id)
        child["parent_wang_source_card_id"] = parent["source_card_id"]
        return {"special_kind": "wang", "pending": True, "nested_kind": card.kind, "nested_prompt_id": game.current_prompt.prompt_id}
    if card.kind == "shu":
        _advance_turn(room, game)
    resumed = _resume_wang_parent(room, game, parent["source_card_id"])
    return {**resumed, "nested_kind": card.kind}


def _resume_wang_parent(room: Room, game: GameState, parent_source_card_id: str) -> dict[str, Any]:
    parent = next(
        (item for item in game.effect_queue if item.get("type") == "wang" and item.get("source_card_id") == parent_source_card_id),
        None,
    )
    if parent is None:
        raise SpecialEffectError("缺少望牌控制的原始响应状态", code="PROMPT_STATE_MISSING")
    if game.current_player_id == parent["controller_player_id"]:
        _close_effect(game, parent)
        controller = room.player(parent["controller_player_id"])
        if not controller.hand:
            game.special_state["pending_finish_player_id"] = controller.player_id
            if _drain_seen_events(room, game):
                return {"special_kind": "wang", "pending": True}
            if open_has_sui_challenge(
                room,
                controller.player_id,
                finish_player_id=controller.player_id,
            ):
                return {"special_kind": "wang", "pending": True}
            game.special_state.pop("pending_finish_player_id", None)
            _finish_game_state(room, game, controller.player_id)
        elif _drain_seen_events(room, game):
            return {"special_kind": "wang", "pending": True}
        return {"special_kind": "wang", "pending": False}
    parent["controlled_player_id"] = game.current_player_id
    _replace_prompt(
        room,
        game,
        parent,
        kind=PromptKind.SUI_PLAYER_RESPONSE,
        responder_id=parent["controller_player_id"],
        legal_responses=["control_play", "control_pass"],
        default_action="control_pass",
    )
    return {"special_kind": "wang", "pending": True, "controlled_player_id": game.current_player_id}


def _resolve_wang_wild_draw_four(room: Room, game: GameState, effect: dict[str, Any], response: str) -> dict[str, Any]:
    source = room.player(effect["source_player_id"])
    target = room.player(effect["target_player_id"])
    result = effect["challenge_result"]
    if response == "decline_challenge":
        _draw_cards(game, target, 4)
        _advance_turn(room, game)
        result = "declined"
    elif response == "challenge":
        if result == "illegal":
            _draw_cards(game, source, 4)
        else:
            _draw_cards(game, target, 6)
            _advance_turn(room, game)
    else:
        raise SpecialEffectError("+4 质疑响应无效", code="ILLEGAL_PROMPT_RESPONSE")
    _close_effect(game, effect)
    parent_result = _resume_wang_parent(room, game, effect["parent_wang_source_card_id"])
    return {**parent_result, "challenge_result": result}


def _respond_fuzhou(room: Room, game: GameState, effect: dict[str, Any], player, response: str, payload: dict[str, Any]) -> dict[str, Any]:
    gifted_card_id: str | None = None
    if response == "evade":
        _consume_rank_evasion(game, effect, player, payload.get("card_id"))
        response = "decline"
    if response == "give_card":
        card = _card_from_hand(player, payload.get("card_id"))
        player.hand.remove(card)
        room.player(effect["source_player_id"]).hand.append(card)
        gifted_card_id = card.card_id
    elif response != "decline":
        raise SpecialEffectError("符咒响应无效", code="ILLEGAL_PROMPT_RESPONSE")
    if not _next_effect_responder(
        room,
        game,
        effect,
        kind=PromptKind.SUI_PLAYER_RESPONSE,
        legal_responses=["give_card", "decline"],
        default_action="decline",
    ):
        source_card = next(card for card in game.reveal_area if card.card_id == effect["source_card_id"])
        game.reveal_area.remove(source_card)
        game.discard_pile.append(source_card)
        _finish_effect_and_advance(room, game, effect)
    return {"special_kind": "fuzhou", "gifted_card_id": gifted_card_id, "pending": game.current_prompt is not None}


def expire_special_prompt(room: Room, prompt_id: str, *, now: float | None = None) -> bool:
    """断线宽限兜底：特殊牌 prompt 超时后按默认动作推进，避免断线玩家卡死整局。

    各牌超时默认动作与 prompt.default_action 一致：
      - ji / fuzhou / nian_claim / nian_turn_end_discard / wang / chongyue -> 视为 pass/decline
      - yu (responder 阶段) -> 视为 decline，进入 restart 阶段（source 可 restart 或 stop）
      - yu (restart 阶段) -> stop，结束效果并推进回合
      - sui_xiang -> draw_four（无同色牌则摸 4 张）

    仅处理仍在 OPEN 且已超过 deadline 的 prompt；其余返回 False。
    """
    game = _game(room)
    prompt = game.current_prompt
    if (
        prompt is None
        or prompt.prompt_id != prompt_id
        or prompt.status != PromptStatus.OPEN
        or (now if now is not None else time()) < prompt.deadline_at
    ):
        return False

    effect = _current_effect(game, prompt_id)
    effect_type = effect["type"]
    responder = room.player(prompt.responder_ids[0])

    if effect_type == "sui_activation_reaction":
        if not _next_effect_responder(
            room,
            game,
            effect,
            kind=PromptKind.SUI_REACTION,
            legal_responses=["pass", "use_zuole", "evade"],
            default_action="pass",
        ):
            _finish_pre_effect_reaction(room, game, effect)
    elif effect_type == "ji":
        _finish_effect_and_advance(room, game, effect)
    elif effect_type == "yu":
        if effect.get("phase") == "restart":
            _finish_effect_and_advance(room, game, effect)
        else:
            effect["phase"] = "restart"
            effect["declining_index"] = effect["responder_index"]
            _replace_prompt(
                room,
                game,
                effect,
                kind=PromptKind.SUI_PLAYER_RESPONSE,
                responder_id=effect["source_player_id"],
                legal_responses=["restart", "stop"],
                default_action="stop",
            )
    elif effect_type == "sui_xiang":
        if not any(card.color == CardColor(effect["required_color"]) for card in responder.hand):
            _draw_cards(game, responder, 4)
        if not _next_effect_responder(
            room,
            game,
            effect,
            kind=PromptKind.SUI_PLAYER_RESPONSE,
            legal_responses=["submit_cards", "draw_four", "use_xi"],
            default_action="draw_four",
        ):
            revealed = next(card for card in game.reveal_area if card.card_id == effect["revealed_card_id"])
            game.reveal_area.remove(revealed)
            game.discard_pile.append(revealed)
            _finish_effect_and_advance(room, game, effect)
    elif effect_type == "chongyue":
        if not _next_effect_responder(
            room,
            game,
            effect,
            kind=PromptKind.CHONGYUE_CHALLENGE,
            legal_responses=["challenge", "decline_challenge"],
            default_action="decline_challenge",
        ):
            _finish_effect_and_advance(room, game, effect)
    elif effect_type == "nian_turn_end_discard":
        # This is a mandatory card choice. Runtime pauses the authoritative
        # room when its deadline expires and keeps this prompt intact.
        return False
    elif effect_type == "nian_claim":
        if not _next_effect_responder(
            room,
            game,
            effect,
            kind=PromptKind.NIAN_CLAIM_WINDOW,
            legal_responses=["chi", "peng", "gang", "pass"],
            default_action="pass",
        ):
            _resolve_nian_claims(room, game, effect)
    elif effect_type == "ling_reaction":
        if not _next_effect_responder(
            room,
            game,
            effect,
            kind=PromptKind.SUI_REACTION,
            legal_responses=["pass", "use_zuole", "evade"],
            default_action="pass",
        ):
            _finish_ling_reaction(room, game, effect)
    elif effect_type == "has_sui_challenge":
        if prompt.required:
            return False
        if not _next_effect_responder(
            room,
            game,
            effect,
            kind=PromptKind.HAS_SUI_CHALLENGE,
            legal_responses=["challenge", "decline_challenge"],
            default_action="decline_challenge",
        ):
            _finish_has_sui_challenge(room, game, effect)
    elif effect_type == "wang":
        _advance_turn(room, game)
        if game.current_player_id == effect["controller_player_id"]:
            _close_effect(game, effect)
            if effect.get("parent_wang_source_card_id"):
                _resume_wang_parent(room, game, effect["parent_wang_source_card_id"])
        else:
            effect["controlled_player_id"] = game.current_player_id
            _replace_prompt(
                room,
                game,
                effect,
                kind=PromptKind.SUI_PLAYER_RESPONSE,
                responder_id=effect["controller_player_id"],
                legal_responses=["control_play", "control_pass"],
                default_action="control_pass",
            )
    elif effect_type == "fuzhou":
        if not _next_effect_responder(
            room,
            game,
            effect,
            kind=PromptKind.SUI_PLAYER_RESPONSE,
            legal_responses=["give_card", "decline"],
            default_action="decline",
        ):
            source_card = next(card for card in game.reveal_area if card.card_id == effect["source_card_id"])
            game.reveal_area.remove(source_card)
            game.discard_pile.append(source_card)
            _finish_effect_and_advance(room, game, effect)
    elif effect_type == "wang_wild_draw_four_challenge":
        _resolve_wang_wild_draw_four(room, game, effect, "decline_challenge")
    else:
        return False
    return True


def respond_special_prompt(
    room: Room,
    player_id: str,
    prompt_id: str,
    response: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    game = _game(room)
    prompt = game.current_prompt
    if prompt is None or prompt.prompt_id != prompt_id:
        raise SpecialEffectError("该响应窗口已不再生效", code="STALE_PROMPT")
    if player_id not in prompt.responder_ids:
        raise SpecialEffectError("你不是当前响应者", code="NOT_PROMPT_RESPONDER")
    if response not in prompt.legal_responses:
        raise SpecialEffectError("该响应不在允许范围内", code="ILLEGAL_PROMPT_RESPONSE")
    effect = _current_effect(game, prompt_id)
    player = room.player(player_id)
    effect_type = effect["type"]
    if effect_type == "sui_activation_reaction":
        return _respond_pre_effect_reaction(room, game, effect, player, response, payload)
    if effect_type == "ji":
        return _respond_ji(room, game, effect, player, response, payload)
    if effect_type == "yu":
        return _respond_yu(room, game, effect, player, response, payload)
    if effect_type == "sui_xiang":
        return _respond_sui_xiang(room, game, effect, player, response, payload)
    if effect_type == "chongyue":
        return _respond_chongyue(room, game, effect, player, response)
    if effect_type == "nian_turn_end_discard":
        return _respond_nian_turn_end_discard(room, game, effect, player, response, payload)
    if effect_type == "nian_claim":
        return _respond_nian_claim(room, game, effect, player, response, payload)
    if effect_type == "ling_reaction":
        return _respond_ling_reaction(room, game, effect, player, response, payload)
    if effect_type == "has_sui_challenge":
        return _respond_has_sui_challenge(room, game, effect, player, response, payload)
    if effect_type == "wang":
        return _respond_wang(room, game, effect, player, response, payload)
    if effect_type == "wang_wild_draw_four_challenge":
        return _resolve_wang_wild_draw_four(room, game, effect, response)
    if effect_type == "fuzhou":
        return _respond_fuzhou(room, game, effect, player, response, payload)
    raise SpecialEffectError("缺少特殊响应窗口的结算规则", code="SPECIAL_RESOLVER_MISSING")


def buy_shop_good(room: Room, player_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    game = _game(room)
    if game.current_prompt is not None:
        raise SpecialEffectError("请先处理当前待响应操作", code="PROMPT_PENDING")
    if game.current_player_id != player_id:
        raise SpecialEffectError("只能在自己的回合操作商店", code="NOT_YOUR_TURN")
    if player_id in game.shop.bought_this_turn_by:
        raise SpecialEffectError("本回合已购买过商店物品", code="SHOP_BUY_LIMIT")
    player = room.player(player_id)
    good = next((card for card in game.shop.goods if card.card_id == payload.get("good_card_id")), None)
    if good is None:
        raise SpecialEffectError("未找到所选商店物品", code="SHOP_GOOD_NOT_FOUND")
    payment = _card_from_hand(player, payload.get("payment_card_id"))
    if good.color is not None:
        same_color = payment.color is not None and payment.color == good.color
        same_number = payment.value is not None and good.value is not None and payment.value == good.value
        if not (same_color or same_number):
            raise SpecialEffectError("支付牌与商店物品不匹配", code="SHOP_PAYMENT_INVALID")
    player.hand.remove(payment)
    game.discard_pile.append(payment)
    game.shop.goods.remove(good)
    player.hand.append(good)
    game.shop.bought_this_turn_by.add(player_id)
    return {"bought_card_id": good.card_id, "payment_card_id": payment.card_id, "shop_count": len(game.shop.goods)}


def refresh_shop(room: Room, player_id: str) -> dict[str, Any]:
    game = _game(room)
    if game.current_prompt is not None:
        raise SpecialEffectError("请先处理当前待响应操作", code="PROMPT_PENDING")
    if game.current_player_id != player_id:
        raise SpecialEffectError("只能在自己的回合操作商店", code="NOT_YOUR_TURN")
    if player_id in game.shop.refreshed_this_turn_by:
        raise SpecialEffectError("本回合已刷新过商店", code="SHOP_REFRESH_LIMIT")
    game.discard_pile.extend(game.shop.goods)
    game.shop.goods = []
    for _ in range(8):
        try:
            game.shop.goods.extend(_draw_cards(game, type("ShopHolder", (), {"hand": []})(), 1))
        except SpecialEffectError as exc:
            if exc.code == "EMPTY_DECK":
                break
            raise
    game.shop.refreshed_this_turn_by.add(player_id)
    return {"shop_count": len(game.shop.goods)}
