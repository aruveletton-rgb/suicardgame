#!/usr/bin/env python3
"""Run deterministic in-process games using the production bot policy."""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.domain.room import Room, RoomPhase, make_room_code, new_player
from backend.app.engine.bot import choose_bot_command, fallback_bot_prompt_command
from backend.app.engine.command_handler import Command, CommandError, process_command


def make_room(player_count: int) -> Room:
    players = [
        new_player(f"bot{index}", index, is_host=index == 0, is_bot=True)
        for index in range(player_count)
    ]
    room = Room(
        room_id=make_room_code(set()),
        host_player_id=players[0].player_id,
        players=players,
    )
    for player in players:
        player.ready = True
    return room


def start_game(room: Room, seed: int) -> None:
    process_command(
        room,
        Command(
            action_id="start",
            room_id=room.room_id,
            player_id=room.host_player_id,
            command_type="START_GAME",
            payload={"seed": seed},
        ),
    )


def _fallback_command(room: Room, command: Command) -> Command | None:
    game = room.active_game
    if command.command_type == "RESPOND_TO_PROMPT":
        return fallback_bot_prompt_command(room)
    if (
        command.command_type != "DRAW_CARD"
        and game is not None
        and game.current_prompt is None
        and game.current_player_id == command.player_id
    ):
        return Command(
            action_id=f"{command.action_id}:draw",
            room_id=room.room_id,
            player_id=command.player_id,
            command_type="DRAW_CARD",
            payload={},
            game_id=game.game_id,
            game_epoch=game.game_epoch,
            expected_state_version=room.state_version,
        )
    return None


def run_game(room: Room, seed: int, max_steps: int) -> dict:
    start_game(room, seed)
    steps = 0
    special_triggers = 0
    stall_reason = None
    primary_rejections: Counter[str] = Counter()
    fallback_rejections: Counter[str] = Counter()
    fallback_success_count = 0

    while steps < max_steps:
        game = room.active_game
        if room.phase != RoomPhase.IN_GAME or game is None or game.status.value != "ACTIVE":
            break

        command = choose_bot_command(room)
        if command is None:
            stall_reason = "no_bot_command"
            break
        if command.command_type == "ACTIVATE_SPECIAL":
            special_triggers += 1

        steps += 1
        try:
            process_command(room, command)
        except CommandError as exc:
            primary_rejections[exc.code] += 1
            fallback = _fallback_command(room, command)
            if fallback is None:
                stall_reason = f"command:{exc.code}"
                break
            try:
                process_command(room, fallback)
                fallback_success_count += 1
            except CommandError as fallback_exc:
                fallback_rejections[fallback_exc.code] += 1
                stall_reason = f"fallback:{fallback_exc.code}"
                break

    game = room.active_game
    finished = room.phase == RoomPhase.ROUND_RESULT
    return {
        "seed": seed,
        "player_count": len(room.players),
        "steps": steps,
        "finished": finished,
        "winner": game.winner_player_id if game is not None else None,
        "winner_seat_index": next(
            (player.seat_index for player in room.players if game and player.player_id == game.winner_player_id),
            None,
        ),
        "primary_command_rejection_count": sum(primary_rejections.values()),
        "primary_command_rejections": dict(primary_rejections),
        "fallback_success_count": fallback_success_count,
        "fallback_rejection_count": sum(fallback_rejections.values()),
        "fallback_rejections": dict(fallback_rejections),
        "special_triggers": special_triggers,
        "stall_reason": stall_reason,
        "hit_step_limit": steps >= max_steps and not finished and stall_reason is None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--max-steps", type=int, default=20_000)
    parser.add_argument("--seed-base", type=int, default=1)
    args = parser.parse_args()
    if args.games < 1 or args.max_steps < 1:
        parser.error("--games and --max-steps must be positive")

    sizes = (2, 3, 4, 5)
    results = []
    started_at = time.perf_counter()
    for index in range(args.games):
        size = sizes[index % len(sizes)]
        results.append(run_game(make_room(size), args.seed_base + index, args.max_steps))

    elapsed = time.perf_counter() - started_at
    step_counts = sorted(result["steps"] for result in results)
    stalls: dict[str, int] = {}
    primary_rejections: Counter[str] = Counter()
    fallback_rejections: Counter[str] = Counter()
    for result in results:
        primary_rejections.update(result["primary_command_rejections"])
        fallback_rejections.update(result["fallback_rejections"])
        reason = result["stall_reason"]
        if reason:
            stalls[reason] = stalls.get(reason, 0) + 1
    summary = {
        "total_games": len(results),
        "finished": sum(result["finished"] for result in results),
        "hit_step_limit": sum(result["hit_step_limit"] for result in results),
        "stalls": stalls,
        "primary_command_rejection_count": sum(primary_rejections.values()),
        "primary_command_rejections": dict(primary_rejections),
        "fallback_success_count": sum(result["fallback_success_count"] for result in results),
        "fallback_rejection_count": sum(fallback_rejections.values()),
        "fallback_rejections": dict(fallback_rejections),
        "total_special_triggers": sum(result["special_triggers"] for result in results),
        "avg_steps": round(sum(step_counts) / len(step_counts), 1),
        "median_steps": step_counts[len(step_counts) // 2],
        "max_steps": max(step_counts),
        "elapsed_seconds": round(elapsed, 2),
        "games_per_second": round(args.games / elapsed, 2) if elapsed else None,
    }
    print(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2))
    if summary["finished"] != args.games or summary["hit_step_limit"] or stalls:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
