"""Deterministic server-side players.

Bots deliberately submit the same commands as a human client.  This keeps
rule validation, prompt expiry and game history on one authoritative path.
"""

from __future__ import annotations

from collections import Counter
from typing import Any
from uuid import uuid4

from backend.app.domain.cards import Card, CardCategory, CardColor
from backend.app.domain.room import GameState, PromptKind, Room
from backend.app.engine.command_handler import Command
from backend.app.rules.sui.catalog import higher_sui_rank
from backend.app.rules.uno import can_play_card


def _action(room: Room, player_id: str, command_type: str, payload: dict[str, Any]) -> Command:
    game = room.active_game
    return Command(
        action_id=f"bot:{room.room_id}:{game.game_id if game else 'lobby'}:{uuid4().hex}",
        room_id=room.room_id,
        player_id=player_id,
        command_type=command_type,
        payload=payload,
        game_id=game.game_id if game else None,
        game_epoch=game.game_epoch if game else None,
        expected_state_version=room.state_version,
    )


def _cards_by_ids(player, ids: list[str]) -> list[Card]:
    return [card for card in player.hand if card.card_id in ids]


def _normal_playable(game: GameState, player) -> list[Card]:
    top = game.discard_pile[-1] if game.discard_pile else None
    return [
        card for card in player.hand
        if card.category != CardCategory.SUI
        and can_play_card(top_card=top, current_color=game.current_color, hand=player.hand, candidate=card).allowed
    ]


def _choose_color(player) -> str:
    colors = [card.color.value for card in player.hand if card.color is not None]
    return Counter(colors).most_common(1)[0][0] if colors else CardColor.RED.value


def _claim_cards(player, effect: dict[str, Any], claim: str) -> list[str] | None:
    last = effect.get("last_played") or {}
    value = last.get("value")
    numbered = [card for card in player.hand if card.category == CardCategory.NUMBER and card.value is not None]
    if claim == "peng":
        matches = [card for card in numbered if card.value == value]
        return [card.card_id for card in matches[:2]] if len(matches) >= 2 else None
    if claim == "gang":
        matches = [card for card in numbered if card.value == value]
        return [card.card_id for card in matches[:3]] if len(matches) >= 3 else None
    if claim == "chi" and isinstance(value, int):
        by_value = {card.value: card for card in numbered}
        for values in ((value - 2, value - 1), (value - 1, value + 1), (value + 1, value + 2)):
            if values[0] in by_value and values[1] in by_value:
                return [by_value[values[0]].card_id, by_value[values[1]].card_id]
    return None


def _prompt_command(room: Room, game: GameState, bot, prompt) -> Command | None:
    allowed = list(prompt.private_options_by_responder.get(bot.player_id, prompt.legal_responses))
    effect = next((item for item in game.effect_queue if item.get("prompt_id") == prompt.prompt_id), {})
    effect_type = effect.get("type")
    hand_ids = {card.card_id for card in bot.hand}
    private_ids = [item for item in allowed if item in hand_ids]

    response = None
    payload: dict[str, Any] = {"prompt_id": prompt.prompt_id}
    if "give_card" in prompt.legal_responses and private_ids:
        response = "give_card"
        payload["card_id"] = private_ids[0]
    elif "give_card" in prompt.legal_responses and effect_type == "fuzhou" and bot.hand:
        response = "give_card"
        payload["card_id"] = bot.hand[0].card_id
    elif prompt.kind == PromptKind.NIAN_TURN_END_DISCARD and bot.hand:
        response = "discard_card"
        payload["card_id"] = bot.hand[0].card_id
    elif prompt.kind == PromptKind.NIAN_CLAIM_WINDOW:
        for candidate in ("gang", "peng", "chi"):
            if candidate == "chi" and effect.get("responder_index") != 0:
                continue  # 只有下一位玩家可以吃牌
            ids = _claim_cards(bot, effect, candidate)
            if candidate in prompt.legal_responses and ids:
                response = candidate
                payload["card_ids"] = ids
                break
        response = response or "pass"
    elif "submit_cards" in prompt.legal_responses:
        required_color = effect.get("required_color")
        if effect_type == "sui_xiang":
            match = next((card for card in bot.hand if card.color and card.color.value == required_color), None)
            if match:
                response = "submit_cards"
                payload["card_ids"] = [match.card_id]
        elif effect_type == "yu":
            used = set(effect.get("used_colors", []))
            match = next((card for card in bot.hand if card.color and card.color.value not in used), None)
            if match:
                response = "submit_cards"
                payload["card_ids"] = [match.card_id]
        elif effect_type == "ji":
            chosen = effect.get("chosen_color")
            matches = [card for card in bot.hand if card.color and card.color.value == chosen]
            if bot.player_id == effect.get("source_player_id"):
                # 使用者最多只能再弃置其他玩家已弃总数的同色牌；上限为 0 时只能放弃。
                matches = matches[: max(int(effect.get("total_discarded", 0)), 0)]
            else:
                matches = matches[:1]
            if matches:
                response = "submit_cards"
                payload["card_ids"] = [card.card_id for card in matches]
    if response is None and "use_zuole" in prompt.legal_responses:
        zuole_id = next((card.card_id for card in bot.hand if card.kind == "zuole"), None)
        if zuole_id is not None and effect_type in {"sui_activation_reaction", "ling_reaction"}:
            response = "use_zuole"
            payload["card_id"] = zuole_id
            payload["target_player_id"] = effect.get("source_player_id") or bot.player_id
    if response is None and "use_xi" in prompt.legal_responses:
        xi = next((card for card in bot.hand if card.kind == "xi"), None)
        if xi is not None:
            response = "use_xi"
            if effect_type == "sui_xiang":
                payload["as_color"] = effect.get("required_color") or CardColor.RED.value
    if response is None and "draw_four" in prompt.legal_responses:
        required_color = effect.get("required_color")
        if not any(card.color and card.color.value == required_color for card in bot.hand):
            response = "draw_four"
    if response is None and "challenge" in prompt.legal_responses:
        response = "challenge" if effect.get("challenge_result") == "legal" else "decline_challenge"
    if response is None and "evade" in prompt.legal_responses and bot.player_id != effect.get("source_player_id"):
        # 规避牌必须是辈分高于来源岁牌的岁牌；private_ids 还可能含左乐等其他可选牌。
        evade_card = next(
            (
                card
                for card in bot.hand
                if card.card_id in private_ids
                and card.category == CardCategory.SUI
                and higher_sui_rank(card.kind, effect.get("source_card_kind", ""))
            ),
            None,
        )
        if evade_card is not None:
            response = "evade"
            payload["card_id"] = evade_card.card_id
    if response is None and "control_play" in prompt.legal_responses:
        controlled = room.player(effect.get("controlled_player_id")) if effect.get("controlled_player_id") else bot
        playable = _normal_playable(game, controlled)
        if playable:
            card = playable[0]
            response = "control_play"
            payload["card_id"] = card.card_id
            if card.kind in {"wild", "wild_draw_four"}:
                payload["chosen_color"] = _choose_color(controlled)
    if response is None:
        for fallback in ("decline", "decline_challenge", "pass", "control_pass", "stop"):
            if fallback in prompt.legal_responses:
                response = fallback
                break
    if response is None:
        return None
    payload["response"] = response
    return _action(room, bot.player_id, "RESPOND_TO_PROMPT", payload)


def fallback_bot_prompt_command(room: Room) -> Command | None:
    """Build a safe default response after a bot strategy is rejected.

    The fallback is intentionally derived from the authoritative prompt. It
    prevents a bad optional choice from being retried until timeout while
    preserving mandatory prompts when no legal default can be constructed.
    """
    game = room.active_game
    prompt = game.current_prompt if game is not None else None
    if game is None or prompt is None or prompt.status.value != "open":
        return None
    responder_id = (
        prompt.responder_ids[prompt.next_responder_index]
        if prompt.resolution_policy.value == "sequential"
        and prompt.next_responder_index < len(prompt.responder_ids)
        else next(
            (player_id for player_id in prompt.responder_ids if player_id not in prompt.response_records),
            None,
        )
    )
    if responder_id is None:
        return None
    bot = room.player(responder_id)
    if not bot.is_bot:
        return None
    effect = next((item for item in game.effect_queue if item.get("prompt_id") == prompt.prompt_id), {})
    response = prompt.default_action
    if response not in prompt.legal_responses:
        return None
    payload: dict[str, Any] = {"prompt_id": prompt.prompt_id, "response": response}

    if response == "give_card":
        eligible = set(prompt.private_options_by_responder.get(bot.player_id, []))
        card = next((item for item in bot.hand if item.card_id in eligible), None)
        if card is None and effect.get("type") == "fuzhou":
            card = bot.hand[0] if bot.hand else None
        if card is None:
            return None
        payload["card_id"] = card.card_id
    elif response == "discard_card":
        if not bot.hand:
            return None
        payload["card_id"] = bot.hand[0].card_id
    elif response == "control_play":
        controlled = room.player(effect["controlled_player_id"]) if effect.get("controlled_player_id") else bot
        playable = _normal_playable(game, controlled)
        if not playable:
            if "control_pass" not in prompt.legal_responses:
                return None
            payload["response"] = "control_pass"
        else:
            card = playable[0]
            payload["card_id"] = card.card_id
            if card.kind in {"wild", "wild_draw_four"}:
                payload["chosen_color"] = _choose_color(controlled)
    elif response == "evade":
        source_kind = effect.get("source_card_kind", "")
        card = next(
            (
                item for item in bot.hand
                if item.category == CardCategory.SUI and higher_sui_rank(item.kind, source_kind)
            ),
            None,
        )
        if card is None:
            return None
        payload["card_id"] = card.card_id
    elif response == "draw_four":
        required_color = effect.get("required_color")
        if any(item.color and item.color.value == required_color for item in bot.hand):
            replacement = next((item for item in bot.hand if item.color and item.color.value == required_color), None)
            if "submit_cards" in prompt.legal_responses and replacement is not None:
                payload["response"] = "submit_cards"
                payload["card_ids"] = [replacement.card_id]
            elif "use_xi" in prompt.legal_responses and any(item.kind == "xi" for item in bot.hand):
                payload["response"] = "use_xi"
                if effect.get("type") == "sui_xiang":
                    payload["as_color"] = required_color
            else:
                return None
    return _action(room, bot.player_id, "RESPOND_TO_PROMPT", payload)


def choose_bot_command(room: Room) -> Command | None:
    game = room.active_game
    if game is None or game.status.value != "ACTIVE" or game.pause_state is not None:
        return None
    if game.current_prompt is not None:
        prompt = game.current_prompt
        responder_ids = prompt.responder_ids
        if prompt.resolution_policy.value == "sequential":
            if prompt.next_responder_index >= len(responder_ids):
                return None
            bot_id = responder_ids[prompt.next_responder_index]
        else:
            bot_id = next((player_id for player_id in responder_ids if player_id not in prompt.response_records), None)
        if bot_id is None:
            return None
        bot = room.player(bot_id)
        if not bot.is_bot:
            return None
        return _prompt_command(room, game, bot, prompt)

    # 望牌 can be activated by a bot while a human is stuck on the current
    # turn. It is the only out-of-turn activation exposed to the bot policy.
    target = room.player(game.current_player_id) if game.current_player_id else None
    if target is not None and not target.is_bot and not _normal_playable(game, target):
        controller = next(
            (
                player for player in room.seats_in_order()
                if player.is_bot and any(card.kind == "wang" for card in player.hand)
            ),
            None,
        )
        if controller is not None:
            card = next(card for card in controller.hand if card.kind == "wang")
            return _action(
                room,
                controller.player_id,
                "ACTIVATE_SPECIAL",
                {"card_id": card.card_id, "target_player_id": target.player_id},
            )

    if game.current_player_id is None:
        return None
    bot = room.player(game.current_player_id)
    if not bot.is_bot:
        return None
    playable = _normal_playable(game, bot)
    if playable:
        card = playable[0]
        payload: dict[str, Any] = {"card_id": card.card_id}
        if card.kind in {"wild", "wild_draw_four"}:
            payload["chosen_color"] = _choose_color(bot)
        return _action(room, bot.player_id, "PLAY_CARD", payload)

    for card in bot.hand:
        if card.category != CardCategory.SUI:
            continue  # 不能出的普通牌不是可发动的岁牌
        payload: dict[str, Any] = {"card_id": card.card_id}
        if card.kind == "yi":
            pair = next(((a, b) for index, a in enumerate(bot.hand) for b in bot.hand[index + 1:] if a.category == b.category == CardCategory.NUMBER and (a.value or 0) + (b.value or 0) == 8), None)
            if pair:
                payload["pair_card_ids"] = [pair[0].card_id, pair[1].card_id]
            else:
                continue
        elif card.kind == "shu":
            colors = Counter(item.color.value for item in bot.hand if item.color is not None)
            chosen = next(((color, count) for color, count in colors.items() if count >= len(room.players) - 1), None)
            if chosen is None:
                continue
            payload["chosen_color"] = chosen[0]
            recipients = [member for member in room.players if member.player_id != bot.player_id]
            remainder = chosen[1] % len(recipients)
            if remainder:
                fewest = min(len(member.hand) for member in recipients)
                candidates = [member for member in recipients if len(member.hand) == fewest]
                if not candidates:
                    continue
                payload["remainder_recipient_id"] = candidates[0].player_id
        elif card.kind in {"ling", "chongyue"}:
            pass
        elif card.kind == "yu":
            payment: list[str] = []
            for color in (CardColor.RED, CardColor.YELLOW, CardColor.GREEN, CardColor.BLUE):
                match = next((item for item in bot.hand if item.color == color and item.card_id not in payment), None)
                if match:
                    payment.append(match.card_id)
            if len(payment) != 4:
                continue
            payload["payment_card_ids"] = payment
        elif card.kind == "wang":
            target = room.player(game.current_player_id)
            if target.player_id == bot.player_id or _normal_playable(game, target):
                continue
            payload["target_player_id"] = target.player_id
        elif card.kind in {"xi", "zuole"}:
            continue
        return _action(room, bot.player_id, "ACTIVATE_SPECIAL", payload)
    return _action(room, bot.player_id, "DRAW_CARD", {})
