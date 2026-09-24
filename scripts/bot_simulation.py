#!/usr/bin/env python3
"""suicardgame 机器人对局模拟（进程内，验证规则正确性与无死锁）。

机器人策略：
  - 有 prompt 时按默认动作响应（sui_xiang / nian_turn_end_discard 特殊处理）
  - 无 prompt 时当前玩家：优先出普通牌（number/action/wild），其次特殊牌，否则摸牌
  - 出最后一张时声明 UNO

用法（服务器上执行）:
    cd /home/suicardgame
    source /home/miniconda3/etc/profile.d/conda.sh && conda activate audio
    python scripts/bot_simulation.py [--games 100] [--max-steps 5000]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.domain.cards import (
    CardCategory,
    CardColor,
    SPECIAL_BY_KIND,
    build_game_deck,
)
from backend.app.domain.room import Room, RoomPhase, Room as RoomType
from backend.app.engine.command_handler import Command, CommandError, process_command
from backend.app.rules.uno import can_play_card
from backend.app.domain.room import new_player, make_room_code


def make_room(player_count: int) -> Room:
    room = Room(room_id=make_room_code(set()), host_player_id="", players=[])
    players = [new_player(f"bot{i}", i, is_host=(i == 0)) for i in range(player_count)]
    room.players = players
    room.host_player_id = players[0].player_id
    return room


def start_game(room: Room, seed: int) -> None:
    cmd = Command(action_id="start", room_id=room.room_id, player_id=room.host_player_id,
                  command_type="START_GAME", payload={"seed": seed})
    process_command(room, cmd)


def find_sum8_pair(hand):
    numbers = [c for c in hand if c.category == CardCategory.NUMBER and c.value is not None]
    for i, a in enumerate(numbers):
        for b in numbers[i + 1:]:
            if a.value + b.value == 8:
                return [a.card_id, b.card_id]
    return None


def find_four_colors(hand):
    seen: dict[CardColor, object] = {}
    for c in hand:
        if c.color is not None and c.color not in seen:
            seen[c.color] = c
        if len(seen) == 4:
            return [c.card_id for c in seen.values()]
    return None


def choose_special_payload(kind: str, hand, player_count: int):
    """为主动特殊牌构造 payload；条件不满足返回 None。"""
    if kind == "ling":
        return {}
    if kind == "chongyue":
        return {}
    if kind == "nian":
        return {}
    if kind == "sui_xiang":
        return {}
    if kind == "ji":
        color = next((c.color for c in hand if c.color is not None), CardColor.RED)
        return {"chosen_color": color.value}
    if kind == "yi":
        pair = find_sum8_pair(hand)
        return {"pair_card_ids": pair} if pair else None
    if kind == "yu":
        pay = find_four_colors(hand)
        return {"payment_card_ids": pay} if pay else None
    if kind == "shu":
        # 选择一种颜色，其手牌数量 >= 其他玩家数
        colors = [c.color for c in hand if c.color is not None]
        for color in CardColor:
            if colors.count(color) >= player_count - 1:
                return {"chosen_color": color.value}
        return None
    if kind == "wang":
        # 需要目标无法出牌；机器人不主动触发，留给被动场景
        return None
    return None


def choose_action(room: Room):
    """返回 (command_type, payload) 或 None 表示摸牌。"""
    game = room.active_game
    player = room.player(game.current_player_id)
    hand = player.hand
    top = game.discard_pile[-1] if game.discard_pile else None

    # 1. 普通牌（number / action / wild）
    for card in hand:
        if card.category in (CardCategory.NUMBER, CardCategory.ACTION, CardCategory.WILD):
            chk = can_play_card(top_card=top, current_color=game.current_color, hand=hand, candidate=card)
            if chk.allowed:
                payload = {"card_id": card.card_id}
                if chk.requires_color_choice:
                    payload["chosen_color"] = (card.color or CardColor.RED).value
                if len(hand) == 1:
                    payload["declare_uno"] = True
                return "PLAY_CARD", payload

    # 2. 主动特殊牌（按简单度排序）
    for kind in ("ling", "chongyue", "nian", "sui_xiang", "ji", "yi", "yu", "shu"):
        for card in hand:
            if card.category == CardCategory.SUI and card.kind == kind:
                payload = choose_special_payload(kind, hand, len(room.players))
                if payload is not None:
                    return "ACTIVATE_SPECIAL", {"card_id": card.card_id, **payload}

    return None


def respond_prompt(room: Room):
    """对当前 prompt 按默认动作构造响应；返回 (responder_id, command_type, payload)。"""
    game = room.active_game
    prompt = game.current_prompt
    responder_id = prompt.responder_ids[0]
    effect = next((e for e in game.effect_queue if e.get("prompt_id") == prompt.prompt_id), {})
    etype = effect.get("type", "")
    payload = {"prompt_id": prompt.prompt_id}
    responder = room.player(responder_id)

    if etype == "sui_xiang":
        required = CardColor(effect["required_color"])
        match = next((c for c in responder.hand if c.color == required), None)
        if match is not None:
            payload["response"] = "submit_cards"
            payload["card_ids"] = [match.card_id]
        else:
            payload["response"] = "draw_four"
    elif etype == "nian_turn_end_discard":
        payload["response"] = "discard_card"
        payload["card_id"] = responder.hand[0].card_id
    elif etype == "yu":
        payload["response"] = "stop" if effect.get("phase") == "restart" else "decline"
    elif etype == "wang":
        payload["response"] = "control_pass"
    else:
        # ji / chongyue / nian_claim / fuzhou / wild_draw_four_challenge 等
        payload["response"] = prompt.default_action if prompt.default_action in prompt.legal_responses else prompt.legal_responses[0]

    return responder_id, "RESPOND_TO_PROMPT", payload


def run_game(room: Room, seed: int, max_steps: int) -> dict:
    start_game(room, seed)
    game = room.active_game
    special_triggers = 0
    steps = 0
    stall_reason = None
    while steps < max_steps:
        steps += 1
        game = room.active_game
        if room.phase != RoomPhase.IN_GAME or game is None or game.status.value != "ACTIVE":
            break

        player_id = game.current_player_id
        player = room.player(player_id)

        if game.current_prompt is not None:
            responder_id, cmd_type, payload = respond_prompt(room)
            cmd = Command(action_id=f"r{steps}", room_id=room.room_id, player_id=responder_id,
                          command_type=cmd_type, payload=payload)
            try:
                process_command(room, cmd)
            except CommandError as exc:
                print(f"  [warn] seed={seed} step={steps} respond failed: {exc.code}", file=sys.stderr)
                stall_reason = f"respond:{exc.code}"
                break
            continue

        action = choose_action(room)
        if action is None:
            cmd_type, payload = "DRAW_CARD", {}
        else:
            cmd_type, payload = action
            if cmd_type == "ACTIVATE_SPECIAL":
                special_triggers += 1

        cmd = Command(action_id=f"a{steps}", room_id=room.room_id, player_id=player_id,
                      command_type=cmd_type, payload=payload)
        try:
            process_command(room, cmd)
        except CommandError as exc:
            if exc.code == "EMPTY_DECK":
                # 无牌可摸且无牌可出：对局无法继续
                stall_reason = "empty_deck"
                break
            # 出牌不合法则摸牌兜底
            try:
                cmd = Command(action_id=f"d{steps}", room_id=room.room_id, player_id=player_id,
                              command_type="DRAW_CARD", payload={})
                process_command(room, cmd)
            except CommandError as exc2:
                if exc2.code == "EMPTY_DECK":
                    stall_reason = "empty_deck"
                else:
                    stall_reason = f"draw:{exc2.code}"
                break

    game = room.active_game
    winner = game.winner_player_id if game is not None else None
    finished = room.phase == RoomPhase.ROUND_RESULT
    return {
        "seed": seed,
        "player_count": len(room.players),
        "steps": steps,
        "finished": finished,
        "winner": winner,
        "special_triggers": special_triggers,
        "stall_reason": stall_reason,
        "hit_step_limit": steps >= max_steps and not finished and stall_reason is None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=100)
    ap.add_argument("--max-steps", type=int, default=20000)
    ap.add_argument("--seed-base", type=int, default=1)
    args = ap.parse_args()

    # 混合 2/3/4/5 人局，均匀分布
    sizes = [2, 3, 4, 5]
    results = []
    finished = 0
    hit_limit = 0
    total_special = 0
    step_counts = []
    stalls: dict[str, int] = {}

    t_start = time.time()
    for i in range(args.games):
        size = sizes[i % len(sizes)]
        room = make_room(size)
        result = run_game(room, args.seed_base + i, args.max_steps)
        results.append(result)
        if result["finished"]:
            finished += 1
        if result["hit_step_limit"]:
            hit_limit += 1
        if result["stall_reason"]:
            stalls[result["stall_reason"]] = stalls.get(result["stall_reason"], 0) + 1
        total_special += result["special_triggers"]
        step_counts.append(result["steps"])

    elapsed = time.time() - t_start
    step_counts_sorted = sorted(step_counts)
    summary = {
        "total_games": args.games,
        "finished": finished,
        "hit_step_limit": hit_limit,
        "stalls": stalls,
        "total_special_triggers": total_special,
        "avg_steps": round(sum(step_counts) / len(step_counts), 1),
        "median_steps": step_counts_sorted[len(step_counts_sorted) // 2],
        "max_steps": max(step_counts),
        "elapsed_seconds": round(elapsed, 2),
        "games_per_second": round(args.games / elapsed, 2),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    out = ROOT / "audits" / "bot_simulation_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, ensure_ascii=False, indent=2)
    print(f"[written] {out}")

    # 非零退出码表示存在死锁（未正常结束的局）
    if hit_limit > 0 or stalls:
        print(f"\n⚠️ 卡死统计: step_limit={hit_limit}, stalls={stalls}，退出码 1")
        sys.exit(1)


if __name__ == "__main__":
    main()
