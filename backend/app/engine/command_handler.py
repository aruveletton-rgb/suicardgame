from __future__ import annotations

import os
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from time import time
from typing import Any
from uuid import uuid4

from backend.app.domain.cards import Card, CardCategory, CardColor, SPECIAL_BY_ASSET_KEY, build_game_deck, iter_uno_specs
from backend.app.domain.room import (
    MAX_PLAYERS,
    MIN_PLAYERS,
    GameState,
    GameStatus,
    Prompt,
    PromptKind,
    PromptResolutionPolicy,
    PromptStatus,
    Room,
    RoomPhase,
    ShopState,
)
from backend.app.engine.invariants import assert_room_invariants
from backend.app.engine.special_effects import (
    SpecialEffectError,
    activate_drawn_special,
    activate_special,
    buy_shop_good,
    nian_enabled,
    open_nian_turn_end_discard,
    refresh_shop,
    respond_special_prompt,
)
from backend.app.rules.uno import can_play_card, wild_draw_four_challenge_result


class CommandError(ValueError):
    code = "COMMAND_ERROR"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


@dataclass(frozen=True)
class Command:
    action_id: str
    room_id: str
    player_id: str
    command_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    game_id: str | None = None
    game_epoch: int | None = None
    expected_state_version: int | None = None


_TEST_CARD_SPECS = {
    **{spec.asset_key: spec for spec in iter_uno_specs()},
    **SPECIAL_BY_ASSET_KEY,
}

_GENERIC_FIXTURE_OPTION = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_GENERIC_FIXTURE_POLICIES = {
    PromptResolutionPolicy.FIRST_WINS,
    PromptResolutionPolicy.SEQUENTIAL,
    PromptResolutionPolicy.ALL,
}


def _remember(room: Room, command: Command, response: dict[str, Any]) -> dict[str, Any]:
    room.processed_actions[command.action_id] = response
    return response


def _require_player(room: Room, player_id: str):
    try:
        return room.player(player_id)
    except KeyError as exc:
        raise CommandError("玩家不存在", code="PLAYER_NOT_FOUND") from exc


def _require_current_game(room: Room, command: Command) -> GameState:
    game = room.active_game
    if game is None or game.status != GameStatus.ACTIVE:
        raise CommandError("该操作属于已经结束或重置的牌局", code="STALE_GAME_COMMAND")
    if command.game_id is not None and command.game_id != game.game_id:
        raise CommandError("该操作属于已经结束或重置的牌局", code="STALE_GAME_COMMAND")
    if command.game_epoch is not None and command.game_epoch != game.game_epoch:
        raise CommandError("该操作属于已经结束或重置的牌局", code="STALE_GAME_COMMAND")
    return game


def _bump(room: Room) -> None:
    room.state_version += 1


def _draw(deck: list[Card]) -> Card:
    if not deck:
        raise CommandError("摸牌堆为空，重洗逻辑尚未补充到该路径", code="EMPTY_DECK")
    return deck.pop()


def _reshuffle_discard_into_deck(game: GameState) -> None:
    if game.deck:
        return
    if len(game.discard_pile) <= 1 or game.reshuffle_count >= 1:
        raise CommandError("摸牌堆和可重洗弃牌都为空", code="EMPTY_DECK")
    top_card = game.discard_pile[-1]
    recycled = game.discard_pile[:-1]
    game.discard_pile = [top_card]
    random.shuffle(recycled)
    game.deck.extend(recycled)
    game.reshuffle_count += 1


def _draw_from_game(game: GameState) -> Card:
    _reshuffle_discard_into_deck(game)
    return game.deck.pop()


def _draw_cards(game: GameState, player, count: int) -> list[Card]:
    drawn: list[Card] = []
    for _ in range(count):
        try:
            card = _draw_from_game(game)
        except CommandError as exc:
            if exc.code == "EMPTY_DECK":
                break
            raise
        player.hand.append(card)
        drawn.append(card)
    return drawn


def _player_after(room: Room, game: GameState, steps: int = 1):
    players = room.seats_in_order()
    if not players:
        raise CommandError("没有玩家", code="PLAYER_NOT_FOUND")
    if game.current_player_id is None:
        return players[0]
    current_index = next((index for index, player in enumerate(players) if player.player_id == game.current_player_id), None)
    if current_index is None:
        raise CommandError("当前玩家不存在", code="PLAYER_NOT_FOUND")
    next_index = (current_index + game.direction * steps) % len(players)
    return players[next_index]


def _advance_turn(room: Room, game: GameState, steps: int = 1) -> None:
    next_player = _player_after(room, game, steps)
    game.current_player_id = next_player.player_id
    game.shop.bought_this_turn_by.discard(next_player.player_id)
    game.shop.refreshed_this_turn_by.discard(next_player.player_id)
    if nian_enabled(game):
        drawn = _draw_cards(game, next_player, 1)
        state = game.special_state.setdefault("nian", {})
        state.setdefault("enabled", True)
        state["last_turn_start_draw"] = {
            "player_id": next_player.player_id,
            "drawn_count": len(drawn),
        }


def _chosen_color(payload: dict[str, Any]) -> CardColor:
    chosen = payload.get("chosen_color")
    try:
        return CardColor(chosen)
    except (TypeError, ValueError) as exc:
        raise CommandError("万能牌必须选择有效颜色", code="COLOR_REQUIRED") from exc


def _require_no_active_prompt(game: GameState) -> None:
    if game.current_prompt is not None:
        raise CommandError("请先处理当前待响应操作", code="PROMPT_PENDING")


def _prompt_effect(game: GameState, prompt_id: str) -> dict[str, Any]:
    effect = next((item for item in game.effect_queue if item.get("prompt_id") == prompt_id), None)
    if effect is None:
        raise CommandError("待响应操作缺少结算状态", code="PROMPT_STATE_MISSING")
    return effect


def _close_prompt(game: GameState, prompt_id: str) -> None:
    prompt = game.current_prompt
    if prompt is not None and prompt.prompt_id == prompt_id:
        prompt.status = PromptStatus.RESOLVED
        prompt.closed = True
        prompt.resolution_reason = "resolved"
    game.current_prompt = None
    game.effect_queue = [item for item in game.effect_queue if item.get("prompt_id") != prompt_id]


def _invalidate_active_prompt(game: GameState, *, reason: str) -> bool:
    prompt = game.current_prompt
    if prompt is None:
        return False
    prompt.status = PromptStatus.CANCELLED
    prompt.closed = True
    prompt.resolution_reason = reason
    game.current_prompt = None
    game.effect_queue = [item for item in game.effect_queue if item.get("prompt_id") != prompt.prompt_id]
    if prompt.kind == PromptKind.GENERIC_RESPONSE_WINDOW:
        game.last_prompt = prompt
    return True


def _finish_game(room: Room, game: GameState, winner_player_id: str) -> None:
    _invalidate_active_prompt(game, reason="game_finished")
    game.status = GameStatus.FINISHED
    game.winner_player_id = winner_player_id
    room.phase = RoomPhase.ROUND_RESULT


def _finish_game_by_hand_count(room: Room, game: GameState) -> str | None:
    """牌库彻底耗尽且玩家无法行动时，按手牌数判胜负。

    手牌数最少者获胜；并列时座位序号小者优先（确定性）。
    返回胜者 player_id；无玩家时返回 None。
    """
    players = room.seats_in_order()
    if not players:
        return None
    winner = min(players, key=lambda p: (len(p.hand), p.seat_index))
    _finish_game(room, game, winner.player_id)
    return winner.player_id


def _player_has_no_legal_action(room: Room, game: GameState, player) -> bool:
    """玩家手牌中是否存在任何合法动作（可出的普通牌，或可激活的特殊牌）。"""
    top = game.discard_pile[-1] if game.discard_pile else None
    for card in player.hand:
        if card.category != CardCategory.SUI:
            if can_play_card(top_card=top, current_color=game.current_color, hand=player.hand, candidate=card).allowed:
                return False
        else:
            # 主动可激活的特殊牌（无 prompt 时可打出）
            if card.kind in {"ling", "chongyue", "nian", "sui_xiang", "ji", "yi", "yu", "shu"}:
                return False
    return True


def _clear_uno_window(game: GameState) -> None:
    game.uno_pending_player_id = None
    game.uno_catchable_by = []


def _expire_uno_window_after_action(game: GameState, acting_player_id: str) -> None:
    pending_player_id = game.uno_pending_player_id
    if pending_player_id is None or pending_player_id == acting_player_id:
        return
    _clear_uno_window(game)
    game.last_uno_event = {
        "type": "window_closed",
        "player_id": pending_player_id,
    }


def _set_uno_state_after_play(room: Room, game: GameState, player, *, declared: bool) -> tuple[bool, str | None]:
    if len(player.hand) != 1:
        return False, None
    if declared:
        _clear_uno_window(game)
        game.last_uno_event = {
            "type": "declared",
            "player_id": player.player_id,
        }
        return True, None
    game.uno_pending_player_id = player.player_id
    game.uno_catchable_by = [member.player_id for member in room.seats_in_order() if member.player_id != player.player_id]
    game.last_uno_event = {
        "type": "pending",
        "player_id": player.player_id,
    }
    return False, player.player_id


def _declare_uno(room: Room, game: GameState, command: Command) -> dict[str, Any]:
    player = room.player(command.player_id)
    if game.uno_pending_player_id != player.player_id or len(player.hand) != 1:
        raise CommandError("当前没有可宣告的 UNO 状态", code="UNO_DECLARE_INVALID")
    _clear_uno_window(game)
    game.last_uno_event = {
        "type": "declared",
        "player_id": player.player_id,
    }
    _bump(room)
    assert_room_invariants(room)
    return _remember(
        room,
        command,
        {
            "ok": True,
            "uno_declared": True,
            "player_id": player.player_id,
            "state_version": room.state_version,
        },
    )


def _catch_uno(room: Room, game: GameState, command: Command) -> dict[str, Any]:
    target_player_id = command.payload.get("target_player_id")
    if (
        not isinstance(target_player_id, str)
        or game.uno_pending_player_id != target_player_id
        or command.player_id == target_player_id
        or command.player_id not in game.uno_catchable_by
    ):
        raise CommandError("当前不能抓取该玩家的 UNO", code="UNO_CATCH_INVALID")
    target = room.player(target_player_id)
    drawn = _draw_cards(game, target, 2)
    _clear_uno_window(game)
    game.last_uno_event = {
        "type": "caught",
        "target_player_id": target.player_id,
        "catcher_player_id": command.player_id,
        "penalty_count": len(drawn),
    }
    _bump(room)
    assert_room_invariants(room)
    return _remember(
        room,
        command,
        {
            "ok": True,
            "caught": True,
            "target_player_id": target.player_id,
            "catcher_player_id": command.player_id,
            "penalty_count": len(drawn),
            "state_version": room.state_version,
        },
    )


def _resolve_wild_draw_four_prompt(room: Room, game: GameState, command: Command, prompt: Prompt) -> dict[str, Any]:
    response = command.payload.get("response")
    effect = _prompt_effect(game, prompt.prompt_id)
    source = room.player(effect["source_player_id"])
    target = room.player(effect["target_player_id"])
    challenge_result = effect["challenge_result"]
    drawn_count = 0
    penalty_player_id: str | None = None

    if response == "decline_challenge":
        drawn_count = len(_draw_cards(game, target, 4))
        penalty_player_id = target.player_id
        challenge_result = "declined"
        _advance_turn(room, game)
    elif response == "challenge":
        if challenge_result == "illegal":
            drawn_count = len(_draw_cards(game, source, 4))
            penalty_player_id = source.player_id
        else:
            drawn_count = len(_draw_cards(game, target, 6))
            penalty_player_id = target.player_id
            _advance_turn(room, game)
    else:
        raise CommandError("该响应不在允许范围内", code="ILLEGAL_PROMPT_RESPONSE")

    source_would_win = bool(effect.get("source_would_win"))
    _close_prompt(game, prompt.prompt_id)
    _expire_uno_window_after_action(game, command.player_id)
    if source_would_win and challenge_result != "illegal":
        _finish_game(room, game, source.player_id)
    _bump(room)
    assert_room_invariants(room)
    return _remember(
        room,
        command,
        {
            "ok": True,
            "prompt_id": prompt.prompt_id,
            "challenge_result": challenge_result,
            "penalty_player_id": penalty_player_id,
            "drawn_count": drawn_count,
            "next_player_id": game.current_player_id,
            "state_version": room.state_version,
        },
    )


def _require_safe_test_fixture() -> None:
    if os.getenv("TEST_MODE") != "1":
        raise CommandError("Generic response fixture is disabled", code="TEST_MODE_DISABLED")
    configured = os.getenv("SUICARDGAME_DATA_DIR")
    if not configured:
        raise CommandError("Generic response fixture requires an isolated data directory", code="TEST_DATA_DIR_UNSAFE")
    data_dir = Path(configured).resolve()
    tmp_root = Path("/tmp").resolve()
    try:
        relative = data_dir.relative_to(tmp_root)
    except ValueError as exc:
        raise CommandError("Generic response fixture requires an isolated data directory", code="TEST_DATA_DIR_UNSAFE") from exc
    if not relative.parts or not relative.parts[0].startswith("suicardgame-step8-"):
        raise CommandError("Generic response fixture requires a unique Step8 data directory", code="TEST_DATA_DIR_UNSAFE")


def _generic_fixture_stats(game: GameState) -> dict[str, Any]:
    return game.special_state.setdefault(
        "response_window_fixture",
        {"resolution_count": 0, "default_count": 0, "resume_count": 0},
    )


def _finalize_generic_prompt(
    game: GameState,
    prompt: Prompt,
    *,
    status: PromptStatus,
    reason: str,
    resolved_by_player_id: str | None = None,
    apply_default: bool = False,
) -> None:
    if game.current_prompt is not prompt or prompt.status != PromptStatus.OPEN:
        raise CommandError("Prompt is already consumed", code="PROMPT_CONSUMED")
    prompt.status = status
    prompt.closed = True
    prompt.resolution_reason = reason
    prompt.resolved_by_player_id = resolved_by_player_id
    prompt.resume_count += 1
    if apply_default:
        prompt.default_applied_count += 1
    stats = _generic_fixture_stats(game)
    stats["resume_count"] += 1
    if status == PromptStatus.RESOLVED:
        stats["resolution_count"] += 1
    if apply_default:
        stats["default_count"] += 1
    game.current_prompt = None
    game.last_prompt = prompt
    game.effect_queue = [item for item in game.effect_queue if item.get("prompt_id") != prompt.prompt_id]


def expire_generic_response_window(room: Room, prompt_id: str, *, now: float | None = None) -> bool:
    game = room.active_game
    prompt = game.current_prompt if game is not None else None
    if (
        game is None
        or prompt is None
        or prompt.prompt_id != prompt_id
        or prompt.kind != PromptKind.GENERIC_RESPONSE_WINDOW
        or prompt.status != PromptStatus.OPEN
        or (now if now is not None else time()) < prompt.deadline_at
    ):
        return False
    _finalize_generic_prompt(
        game,
        prompt,
        status=PromptStatus.EXPIRED,
        reason="timeout_default",
        apply_default=True,
    )
    _bump(room)
    assert_room_invariants(room)
    return True


def _open_test_response_window(room: Room, game: GameState, command: Command) -> dict[str, Any]:
    _require_safe_test_fixture()
    player = room.player(command.player_id)
    if not player.is_host:
        raise CommandError("Only host may open the generic response fixture", code="HOST_REQUIRED")
    _require_no_active_prompt(game)

    responder_ids = command.payload.get("responder_ids")
    known_player_ids = {member.player_id for member in room.players}
    if (
        not isinstance(responder_ids, list)
        or not responder_ids
        or len(responder_ids) != len(set(responder_ids))
        or any(not isinstance(item, str) or item not in known_player_ids for item in responder_ids)
    ):
        raise CommandError("Invalid generic responder set", code="BAD_TEST_RESPONSE_WINDOW")
    try:
        resolution_policy = PromptResolutionPolicy(command.payload.get("resolution_policy", "first_wins"))
    except ValueError as exc:
        raise CommandError("Invalid generic resolution policy", code="BAD_TEST_RESPONSE_WINDOW") from exc
    if resolution_policy not in _GENERIC_FIXTURE_POLICIES:
        raise CommandError("Invalid generic resolution policy", code="BAD_TEST_RESPONSE_WINDOW")
    timeout_seconds = command.payload.get("timeout_seconds", 5)
    if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or not 0.25 <= timeout_seconds <= 60:
        raise CommandError("Invalid generic response timeout", code="BAD_TEST_RESPONSE_WINDOW")

    raw_options = command.payload.get("private_options_by_responder", {})
    if not isinstance(raw_options, dict) or any(key not in responder_ids for key in raw_options):
        raise CommandError("Invalid generic private options", code="BAD_TEST_RESPONSE_WINDOW")
    private_options: dict[str, list[str]] = {}
    for responder_id in responder_ids:
        options = raw_options.get(responder_id, ["accept", "decline"])
        if (
            not isinstance(options, list)
            or not 1 <= len(options) <= 4
            or len(options) != len(set(options))
            or any(not isinstance(option, str) or _GENERIC_FIXTURE_OPTION.fullmatch(option) is None for option in options)
        ):
            raise CommandError("Invalid generic private options", code="BAD_TEST_RESPONSE_WINDOW")
        private_options[responder_id] = list(options)

    created_at = time()
    prompt = Prompt(
        prompt_id=uuid4().hex,
        kind=PromptKind.GENERIC_RESPONSE_WINDOW,
        source_player_id=command.player_id,
        source_card_id=None,
        responder_ids=list(responder_ids),
        legal_responses=sorted({option for options in private_options.values() for option in options}),
        created_at=created_at,
        deadline_at=created_at + float(timeout_seconds),
        default_action="decline",
        state_version=room.state_version,
        resolution_policy=resolution_policy,
        display_title="Response required",
        display_message="Choose an available response before the window closes.",
        private_options_by_responder=private_options,
        game_id=game.game_id,
        game_epoch=game.game_epoch,
    )
    game.current_prompt = prompt
    game.last_prompt = None
    game.effect_queue.append(
        {
            "type": "generic_response_window",
            "prompt_id": prompt.prompt_id,
            "resume_hook": "test_fixture_only",
        }
    )
    _generic_fixture_stats(game)
    _bump(room)
    assert_room_invariants(room)
    return _remember(
        room,
        command,
        {
            "ok": True,
            "test_mode": True,
            "prompt_id": prompt.prompt_id,
            "prompt_status": prompt.status.value,
            "resolution_policy": prompt.resolution_policy.value,
            "state_version": room.state_version,
        },
    )


def _resolve_generic_prompt(room: Room, game: GameState, command: Command, prompt: Prompt) -> dict[str, Any]:
    if prompt.game_id != game.game_id or prompt.game_epoch != game.game_epoch:
        raise CommandError("Prompt belongs to an old game", code="STALE_PROMPT")
    if prompt.status != PromptStatus.OPEN or prompt.closed:
        raise CommandError("Prompt is already consumed", code="PROMPT_CONSUMED")
    if time() >= prompt.deadline_at:
        raise CommandError("Prompt has expired", code="PROMPT_EXPIRED")
    if command.player_id in prompt.response_records:
        raise CommandError("Responder already submitted", code="DUPLICATE_PROMPT_RESPONSE")
    if prompt.resolution_policy == PromptResolutionPolicy.SEQUENTIAL:
        expected_responder_id = prompt.responder_ids[prompt.next_responder_index]
        if command.player_id != expected_responder_id:
            raise CommandError("It is not this responder's step", code="NOT_CURRENT_PROMPT_RESPONDER")

    response = command.payload.get("response")
    allowed = prompt.private_options_by_responder.get(command.player_id, prompt.legal_responses)
    if response not in allowed:
        raise CommandError("Response is not available to this responder", code="ILLEGAL_PROMPT_RESPONSE")
    prompt.response_records[command.player_id] = response

    if prompt.resolution_policy == PromptResolutionPolicy.FIRST_WINS:
        _finalize_generic_prompt(
            game,
            prompt,
            status=PromptStatus.RESOLVED,
            reason="first_response",
            resolved_by_player_id=command.player_id,
        )
    elif prompt.resolution_policy == PromptResolutionPolicy.ALL:
        if len(prompt.response_records) == len(prompt.responder_ids):
            _finalize_generic_prompt(
                game,
                prompt,
                status=PromptStatus.RESOLVED,
                reason="all_responses",
                resolved_by_player_id=command.player_id,
            )
    elif prompt.resolution_policy == PromptResolutionPolicy.SEQUENTIAL:
        prompt.next_responder_index += 1
        if prompt.next_responder_index == len(prompt.responder_ids):
            _finalize_generic_prompt(
                game,
                prompt,
                status=PromptStatus.RESOLVED,
                reason="sequence_complete",
                resolved_by_player_id=command.player_id,
            )

    _bump(room)
    assert_room_invariants(room)
    return _remember(
        room,
        command,
        {
            "ok": True,
            "prompt_id": prompt.prompt_id,
            "prompt_status": prompt.status.value,
            "resolution_policy": prompt.resolution_policy.value,
            "response_count": len(prompt.response_records),
            "state_version": room.state_version,
        },
    )


def _respond_to_prompt(room: Room, game: GameState, command: Command) -> dict[str, Any]:
    prompt = game.current_prompt
    if prompt is None:
        previous = game.last_prompt
        if previous is not None and command.payload.get("prompt_id") == previous.prompt_id:
            code = {
                PromptStatus.RESOLVED: "PROMPT_RESOLVED",
                PromptStatus.EXPIRED: "PROMPT_EXPIRED",
                PromptStatus.CANCELLED: "PROMPT_CANCELLED",
            }.get(previous.status, "PROMPT_CONSUMED")
            raise CommandError("Prompt is no longer open", code=code)
        raise CommandError("当前没有待响应操作", code="NO_ACTIVE_PROMPT")
    if command.payload.get("prompt_id") != prompt.prompt_id:
        raise CommandError("待响应操作已过期", code="STALE_PROMPT")
    if command.player_id not in prompt.responder_ids:
        raise CommandError("你不是当前响应者", code="NOT_PROMPT_RESPONDER")
    response = command.payload.get("response")
    if response not in prompt.legal_responses:
        raise CommandError("该响应不在允许范围内", code="ILLEGAL_PROMPT_RESPONSE")
    if prompt.kind == PromptKind.GENERIC_RESPONSE_WINDOW:
        return _resolve_generic_prompt(room, game, command, prompt)
    if prompt.kind == PromptKind.WILD_DRAW_FOUR_CHALLENGE:
        return _resolve_wild_draw_four_prompt(room, game, command, prompt)
    try:
        result = respond_special_prompt(room, command.player_id, prompt.prompt_id, response, command.payload)
    except SpecialEffectError as exc:
        raise CommandError(str(exc), code=exc.code) from exc
    _bump(room)
    assert_room_invariants(room)
    return _remember(
        room,
        command,
        {
            "ok": True,
            **result,
            "next_player_id": game.current_player_id,
            "state_version": room.state_version,
        },
    )


def _run_special_command(room: Room, game: GameState, command: Command, resolver) -> dict[str, Any]:
    try:
        result = resolver()
    except SpecialEffectError as exc:
        raise CommandError(str(exc), code=exc.code) from exc
    if result.get("special_kind") == "shu":
        player = room.player(command.player_id)
        _expire_uno_window_after_action(game, player.player_id)
        uno_declared, uno_pending_player_id = _set_uno_state_after_play(
            room,
            game,
            player,
            declared=bool(command.payload.get("declare_uno", False)),
        )
        result = {
            **result,
            "uno_declared": uno_declared,
            "uno_pending_player_id": uno_pending_player_id,
        }
        if not player.hand:
            _finish_game(room, game, player.player_id)
        else:
            _advance_turn(room, game)
    _bump(room)
    assert_room_invariants(room)
    return _remember(
        room,
        command,
        {
            "ok": True,
            **result,
            "next_player_id": game.current_player_id,
            "state_version": room.state_version,
        },
    )


def _test_card(asset_key: Any) -> Card:
    if not isinstance(asset_key, str) or asset_key not in _TEST_CARD_SPECS:
        raise CommandError("Unknown test card asset key", code="TEST_CARD_UNKNOWN")
    return Card.from_spec(_TEST_CARD_SPECS[asset_key])


def _set_test_state(room: Room, game: GameState, command: Command) -> dict[str, Any]:
    if os.getenv("TEST_MODE") != "1":
        raise CommandError("Test state command is disabled", code="TEST_MODE_DISABLED")
    player = room.player(command.player_id)
    if not player.is_host:
        raise CommandError("Only host may set test state", code="HOST_REQUIRED")
    hands_payload = command.payload.get("hands")
    deck_asset_keys = command.payload.get("deck_asset_keys", [])
    current_player_id = command.payload.get("current_player_id")
    discard_asset_key = command.payload.get("discard_asset_key")
    known_player_ids = {member.player_id for member in room.players}
    if not isinstance(hands_payload, dict) or current_player_id not in known_player_ids:
        raise CommandError("Invalid test state payload", code="BAD_TEST_STATE")
    if not isinstance(deck_asset_keys, list):
        raise CommandError("Invalid test deck", code="BAD_TEST_STATE")

    new_hands: dict[str, list[Card]] = {}
    for member in room.players:
        asset_keys = hands_payload.get(member.player_id, [])
        if not isinstance(asset_keys, list):
            raise CommandError("Invalid test hand", code="BAD_TEST_STATE")
        new_hands[member.player_id] = [_test_card(asset_key) for asset_key in asset_keys]
    new_deck = [_test_card(asset_key) for asset_key in deck_asset_keys]
    new_discard = _test_card(discard_asset_key)

    for member in room.players:
        member.hand = new_hands[member.player_id]
    game.deck = new_deck
    game.discard_pile = [new_discard]
    game.current_color = new_discard.color
    game.current_player_id = current_player_id
    game.direction = 1
    game.current_prompt = None
    game.last_prompt = None
    game.effect_queue = []
    game.special_state = {}
    game.uno_pending_player_id = None
    game.uno_catchable_by = []
    game.last_uno_event = None
    game.winner_player_id = None
    game.status = GameStatus.ACTIVE
    room.phase = RoomPhase.IN_GAME
    _bump(room)
    assert_room_invariants(room)
    return _remember(
        room,
        command,
        {
            "ok": True,
            "test_mode": True,
            "current_player_id": current_player_id,
            "state_version": room.state_version,
        },
    )


def start_game(room: Room, seed: int | None = None) -> dict[str, Any]:
    if room.phase not in {RoomPhase.LOBBY, RoomPhase.ROUND_RESULT}:
        raise CommandError("当前阶段不能开始新局", code="ROOM_NOT_IN_LOBBY")
    if len(room.players) < MIN_PLAYERS or len(room.players) > MAX_PLAYERS:
        raise CommandError("玩家人数必须为 2 到 5", code="INVALID_PLAYER_COUNT")
    not_ready = [member.nickname for member in room.seats_in_order() if not member.online or not member.ready]
    if not_ready:
        raise CommandError("所有在座且在线玩家都准备后才能开始", code="PLAYERS_NOT_READY")

    rng = random.Random(seed)
    deck, field_cards = build_game_deck(len(room.players))
    rng.shuffle(deck)
    game = GameState(game_id=uuid4().hex, game_epoch=room.next_epoch(), deck=deck, field_cards=field_cards, seed=seed)
    room.active_game = game
    room.phase = RoomPhase.IN_GAME
    room.room_version = game.game_epoch
    game.current_player_id = room.seats_in_order()[0].player_id
    for player in room.seats_in_order():
        player.hand = [_draw(game.deck) for _ in range(7)]
        player.ready = False
    if field_cards:
        game.shop.field_card = field_cards.pop(0)
        game.shop.goods = [_draw(game.deck) for _ in range(min(8, len(game.deck)))]

    while game.deck:
        top = _draw(game.deck)
        if top.kind == "wild_draw_four" or top.category == CardCategory.SUI:
            game.deck.insert(0, top)
            rng.shuffle(game.deck)
            continue
        game.discard_pile.append(top)
        game.current_color = top.color
        break
    _bump(room)
    assert_room_invariants(room)
    return {"ok": True, "game_id": game.game_id, "game_epoch": game.game_epoch, "state_version": room.state_version}


def reset_room(room: Room, by_player_id: str) -> dict[str, Any]:
    player = _require_player(room, by_player_id)
    if not player.is_host:
        raise CommandError("只有房主可以 Reset", code="HOST_REQUIRED")
    if room.active_game is not None:
        _invalidate_active_prompt(room.active_game, reason="room_reset")
        room.active_game.status = GameStatus.ABORTED_BY_ROOM_RESET
        room.game_history.append({"game_id": room.active_game.game_id, "game_epoch": room.active_game.game_epoch, "status": room.active_game.status.value})
    for member in room.players:
        member.hand = []
        member.ready = False
    room.active_game = None
    room.phase = RoomPhase.LOBBY
    room.room_version += 1
    _bump(room)
    assert_room_invariants(room)
    return {"ok": True, "room_phase": room.phase.value, "state_version": room.state_version}


def close_room(room: Room, by_player_id: str) -> dict[str, Any]:
    player = _require_player(room, by_player_id)
    if not player.is_host:
        raise CommandError("Only host may close the room", code="HOST_REQUIRED")
    if room.active_game is not None:
        _invalidate_active_prompt(room.active_game, reason="room_closed")
        if room.active_game.status == GameStatus.ACTIVE:
            room.active_game.status = GameStatus.ABORTED_BY_ROOM_RESET
    room.phase = RoomPhase.CLOSED
    room.closed_reason = "closed_by_host"
    _bump(room)
    assert_room_invariants(room)
    return {"ok": True, "room_phase": room.phase.value, "state_version": room.state_version}


def process_command(room: Room, command: Command) -> dict[str, Any]:
    if command.action_id in room.processed_actions:
        return room.processed_actions[command.action_id]
    _require_player(room, command.player_id)

    if room.phase == RoomPhase.CLOSED:
        raise CommandError("Room is closed", code="ROOM_CLOSED")

    if command.expected_state_version is not None and command.expected_state_version != room.state_version:
        raise CommandError("客户端状态版本超前", code="BAD_STATE_VERSION")

    if command.command_type == "READY":
        player = room.player(command.player_id)
        player.ready = bool(command.payload.get("ready", True))
        _bump(room)
        return _remember(room, command, {"ok": True, "ready": player.ready, "state_version": room.state_version})

    if command.command_type == "START_GAME":
        player = room.player(command.player_id)
        if not player.is_host:
            raise CommandError("只有房主可以开始游戏", code="HOST_REQUIRED")
        return _remember(room, command, start_game(room, seed=command.payload.get("seed")))

    if command.command_type == "RESET_ROOM":
        return _remember(room, command, reset_room(room, command.player_id))

    if command.command_type == "CLOSE_ROOM":
        return _remember(room, command, close_room(room, command.player_id))

    if command.command_type == "REMATCH":
        if room.phase != RoomPhase.ROUND_RESULT:
            raise CommandError("只有本局结果阶段可以 Rematch", code="NOT_ROUND_RESULT")
        if room.active_game is not None:
            _invalidate_active_prompt(room.active_game, reason="rematch")
        room.phase = RoomPhase.LOBBY
        for player in room.players:
            player.ready = False
        room.active_game = None
        _bump(room)
        assert_room_invariants(room)
        return _remember(room, command, {"ok": True, "room_phase": room.phase.value, "state_version": room.state_version})

    game = _require_current_game(room, command)

    if command.command_type == "TEST_SET_STATE":
        return _set_test_state(room, game, command)

    if command.command_type == "TEST_OPEN_RESPONSE_WINDOW":
        return _open_test_response_window(room, game, command)

    if command.command_type == "ACTIVATE_SPECIAL":
        return _run_special_command(
            room,
            game,
            command,
            lambda: activate_special(room, command.player_id, command.payload),
        )

    if command.command_type == "BUY_SHOP_GOOD":
        return _run_special_command(
            room,
            game,
            command,
            lambda: buy_shop_good(room, command.player_id, command.payload),
        )

    if command.command_type == "REFRESH_SHOP":
        return _run_special_command(
            room,
            game,
            command,
            lambda: refresh_shop(room, command.player_id),
        )

    if command.command_type == "DECLARE_UNO":
        return _declare_uno(room, game, command)

    if command.command_type == "CATCH_UNO":
        return _catch_uno(room, game, command)

    if command.command_type == "RESPOND_TO_PROMPT":
        return _respond_to_prompt(room, game, command)

    if command.command_type == "DRAW_CARD":
        _require_no_active_prompt(game)
        player = room.player(command.player_id)
        if game.current_player_id != player.player_id:
            raise CommandError("还没轮到你", code="NOT_YOUR_TURN")
        drawn = _draw_cards(game, player, 1)
        _expire_uno_window_after_action(game, player.player_id)
        # 牌库彻底耗尽且玩家无合法出牌 -> 按手牌数判胜负
        if not drawn and _player_has_no_legal_action(room, game, player):
            _finish_game_by_hand_count(room, game)
            _bump(room)
            assert_room_invariants(room)
            return _remember(
                room,
                command,
                {
                    "ok": True,
                    "drawn_count": 0,
                    "triggered_special": None,
                    "finished_by_deck_exhausted": True,
                    "winner_player_id": game.winner_player_id,
                    "state_version": room.state_version,
                },
            )
        try:
            triggered = activate_drawn_special(room, player.player_id, drawn)
        except SpecialEffectError as exc:
            raise CommandError(str(exc), code=exc.code) from exc
        if triggered is None:
            if not open_nian_turn_end_discard(room, game, player, last_played_card=None, advance_steps=1):
                _advance_turn(room, game)
        _bump(room)
        assert_room_invariants(room)
        return _remember(
            room,
            command,
            {
                "ok": True,
                "drawn_count": len(drawn),
                "triggered_special": triggered["special_kind"] if triggered is not None else None,
                "next_player_id": game.current_player_id,
                "state_version": room.state_version,
            },
        )

    if command.command_type == "PLAY_CARD":
        _require_no_active_prompt(game)
        player = room.player(command.player_id)
        if game.current_player_id != player.player_id:
            raise CommandError("还没轮到你", code="NOT_YOUR_TURN")
        card_id = command.payload.get("card_id")
        card = next((item for item in player.hand if item.card_id == card_id), None)
        if card is None:
            raise CommandError("手牌中没有这张牌", code="CARD_NOT_IN_HAND")
        top = game.discard_pile[-1] if game.discard_pile else None
        check = can_play_card(top_card=top, current_color=game.current_color, hand=player.hand, candidate=card)
        if not check.allowed:
            raise CommandError(check.reason or "不能出这张牌", code="ILLEGAL_PLAY")
        previous_color = game.current_color
        hand_before_play = list(player.hand)
        chosen_color = _chosen_color(command.payload) if check.requires_color_choice else None
        _expire_uno_window_after_action(game, player.player_id)
        player.hand.remove(card)
        game.discard_pile.append(card)
        game.current_color = card.color or chosen_color or game.current_color
        uno_declared, uno_pending_player_id = _set_uno_state_after_play(
            room,
            game,
            player,
            declared=bool(command.payload.get("declare_uno", False)),
        )
        drawn_count = 0
        if card.kind == "wild_draw_four":
            target = _player_after(room, game)
            prompt = Prompt(
                prompt_id=uuid4().hex,
                kind=PromptKind.WILD_DRAW_FOUR_CHALLENGE,
                source_player_id=player.player_id,
                source_card_id=card.card_id,
                responder_ids=[target.player_id],
                legal_responses=["challenge", "decline_challenge"],
                created_at=time(),
                deadline_at=time() + 10,
                default_action="decline_challenge",
                state_version=room.state_version,
            )
            game.current_prompt = prompt
            game.effect_queue.append(
                {
                    "type": "wild_draw_four_challenge",
                    "prompt_id": prompt.prompt_id,
                    "source_player_id": player.player_id,
                    "target_player_id": target.player_id,
                    "challenge_result": wild_draw_four_challenge_result(previous_color, hand_before_play),
                    "source_would_win": not player.hand,
                }
            )
            game.current_player_id = target.player_id
        elif not player.hand:
            _finish_game(room, game, player.player_id)
        else:
            advance_steps = 1
            if card.kind == "skip":
                advance_steps = 2
            elif card.kind == "reverse":
                game.direction *= -1
                advance_steps = 2 if len(room.players) == 2 else 1
            elif card.kind == "draw_two":
                target = _player_after(room, game)
                drawn_count = len(_draw_cards(game, target, 2))
                advance_steps = 2
            if game.current_prompt is None:
                if not open_nian_turn_end_discard(
                    room,
                    game,
                    player,
                    last_played_card=card,
                    advance_steps=advance_steps,
                ):
                    _advance_turn(room, game, advance_steps)
        _bump(room)
        assert_room_invariants(room)
        return _remember(
            room,
            command,
            {
                "ok": True,
                "played_card_id": card.card_id,
                "drawn_count": drawn_count,
                "uno_declared": uno_declared,
                "uno_pending_player_id": uno_pending_player_id,
                "next_player_id": game.current_player_id,
                "state_version": room.state_version,
            },
        )

    raise CommandError(f"未支持的命令: {command.command_type}", code="UNKNOWN_COMMAND")
