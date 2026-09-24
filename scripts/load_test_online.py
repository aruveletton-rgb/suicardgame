#!/usr/bin/env python3
"""suicardgame 小型上线前压测：5 并发房间 × 2-5 人，打线上公网入口。

覆盖链路：Nginx(8000) -> uvicorn(8012) -> 结算 -> WebSocket 广播。
收集指标：HTTP create/join/command 延迟分位、WS 广播延迟、错误率，
并断言：座位唯一、public snapshot 无手牌泄露。

用法（服务器上执行）:
    cd /home/suicardgame
    source /home/miniconda3/etc/profile.d/conda.sh && conda activate audio
    python scripts/load_test_online.py [--base http://139.196.13.53:8000]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
import uuid

import httpx
from websockets.asyncio.client import connect as ws_connect

DEFAULT_BASE = "http://139.196.13.53:8000"
ROOM_SIZES = [2, 3, 4, 5, 5]   # 5 个房间，每房人数覆盖 2-5
GAME_ROUNDS = 15               # 每房对局命令轮数
SETTLE_DELAY = 0.05            # 对局内相邻命令间隔（秒）


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f) if c != f else s[f]


class Metrics:
    def __init__(self) -> None:
        self.create: list[float] = []
        self.join: list[float] = []
        self.command: list[float] = []
        self.ws_connect: list[float] = []
        self.ws_first_snapshot: list[float] = []
        self.command_errors: dict[str, int] = {}
        self.leaks: list[dict] = []
        self.rooms: list[dict] = []

    def summary(self) -> dict:
        return {
            "room_count": len(self.rooms),
            "total_players": sum(r["players"] for r in self.rooms),
            "http_create": self._stats(self.create),
            "http_join": self._stats(self.join),
            "http_command": self._stats(self.command),
            "ws_connect": self._stats(self.ws_connect),
            "ws_first_snapshot": self._stats(self.ws_first_snapshot),
            "command_errors": dict(self.command_errors),
            "hand_leak_count": len(self.leaks),
            "rooms": self.rooms,
        }

    @staticmethod
    def _stats(values: list[float]) -> dict:
        n = len(values)
        if n == 0:
            return {"count": 0}
        return {
            "count": n,
            "p50_ms": round(percentile(values, 0.50), 2),
            "p95_ms": round(percentile(values, 0.95), 2),
            "p99_ms": round(percentile(values, 0.99), 2),
            "max_ms": round(max(values), 2),
            "mean_ms": round(statistics.mean(values), 2),
        }


class Player:
    def __init__(self, pid: str, session: str, seat: int, nickname: str) -> None:
        self.pid = pid
        self.session = session
        self.seat = seat
        self.nickname = nickname
        self.hand: list[dict] = []
        self.ws = None
        self.reader: asyncio.Task | None = None


class Room:
    def __init__(self, code: str) -> None:
        self.code = code
        self.players: list[Player] = []
        self.public_state: dict = {}
        self.state_version = 0
        self.leaks: list[dict] = []
        self.ready = False


def check_leak(state: dict, room: Room) -> None:
    for p in state.get("players", []):
        if "hand" in p:
            room.leaks.append({"player_id": p.get("player_id"), "seat": p.get("seat_index")})


async def reader(player: Player, room: Room, metrics: Metrics) -> None:
    """持续接收 WS 消息，缓存 public state 与私有手牌，检测泄露。"""
    try:
        while True:
            raw = await player.ws.recv()
            msg = json.loads(raw)
            ev = msg.get("event")
            if ev == "snapshot":
                room.public_state = msg.get("state", {})
                room.state_version = msg.get("state_version", 0)
                check_leak(room.public_state, room)
            elif ev == "private_snapshot":
                player.hand = msg.get("you", {}).get("hand", [])
            elif ev == "state_patch":
                room.public_state = msg.get("state", {})
                room.state_version = msg.get("state_version", 0)
                check_leak(room.public_state, room)
    except Exception:
        return


async def http_command(client: httpx.AsyncClient, room: Room, player: Player,
                       cmd: str, payload: dict, metrics: Metrics) -> tuple[int, dict | None]:
    body = {
        "action_id": f"{cmd}-{player.pid}-{uuid.uuid4().hex[:8]}",
        "player_id": player.pid,
        "command_type": cmd,
        "payload": payload,
    }
    t0 = time.perf_counter()
    try:
        r = await client.post(
            f"{DEFAULT_BASE}/api/v1/rooms/{room.code}/commands",
            json=body,
            headers={"Authorization": f"Bearer {player.session}"},
            timeout=10.0,
        )
        dt = (time.perf_counter() - t0) * 1000
        metrics.command.append(dt)
        if r.status_code != 200:
            detail = r.json().get("detail", {})
            err = detail.get("error", "UNKNOWN") if isinstance(detail, dict) else "UNKNOWN"
            metrics.command_errors[err] = metrics.command_errors.get(err, 0) + 1
        return r.status_code, r.json()
    except Exception as exc:
        dt = (time.perf_counter() - t0) * 1000
        metrics.command.append(dt)
        metrics.command_errors["EXCEPTION"] = metrics.command_errors.get("EXCEPTION", 0) + 1
        return 0, {"error": str(exc)}


async def run_room(idx: int, size: int, client: httpx.AsyncClient, metrics: Metrics) -> None:
    """一个房间的完整生命周期。"""
    room = Room("")
    t0 = time.perf_counter()
    r = await client.post(f"{DEFAULT_BASE}/api/v1/rooms", json={"nickname": f"host-{idx}"}, timeout=10.0)
    metrics.create.append((time.perf_counter() - t0) * 1000)
    if r.status_code != 200:
        return
    host_data = r.json()
    room.code = host_data["room_code"]
    room.players.append(Player(host_data["player_id"], host_data["session_id"], host_data["seat_index"], f"host-{idx}"))

    # 并发加入其余玩家（每房共 size 人）
    join_results = await asyncio.gather(*[
        _join(client, room.code, idx, j) for j in range(1, size)
    ])
    for status, data, dt in join_results:
        metrics.join.append(dt)
        if status == 200:
            room.players.append(Player(data["player_id"], data["session_id"], data["seat_index"], f"bot-{idx}-{data['seat_index']}"))

    # 断言座位唯一
    seats = [p.seat for p in room.players]
    seat_ok = len(seats) == len(set(seats)) == size

    # WS 连接 + 读取初始快照
    for p in room.players:
        url = f"{DEFAULT_BASE.replace('http', 'ws')}/api/v1/rooms/{room.code}/ws?player_id={p.pid}&session_id={p.session}"
        t = time.perf_counter()
        try:
            p.ws = await ws_connect(url, open_timeout=10.0)
        except Exception:
            metrics.ws_connect.append((time.perf_counter() - t) * 1000)
            continue
        metrics.ws_connect.append((time.perf_counter() - t) * 1000)
        p.reader = asyncio.create_task(reader(p, room, metrics))
    await asyncio.sleep(0.4)  # 等初始 snapshot/private_snapshot 到位

    # READY 所有玩家
    for p in room.players:
        await http_command(client, room, p, "READY", {"ready": True}, metrics)

    # host START_GAME
    host = room.players[0]
    await http_command(client, room, host, "START_GAME", {"seed": idx + 1}, metrics)

    # 对局命令压测
    for _ in range(GAME_ROUNDS):
        active = room.public_state.get("active_game") or {}
        cur = active.get("current_player_id")
        if not cur:
            break
        player = next((p for p in room.players if p.pid == cur), None)
        if player is None:
            break
        playable = _choose_playable(player.hand, active)
        if playable is not None:
            await http_command(client, room, player, "PLAY_CARD", playable, metrics)
        else:
            await http_command(client, room, player, "DRAW_CARD", {}, metrics)
        await asyncio.sleep(SETTLE_DELAY)

    # 清理房间
    await http_command(client, room, host, "CLOSE_ROOM", {}, metrics)

    # 关闭 WS
    for p in room.players:
        if p.reader is not None:
            p.reader.cancel()
        if p.ws is not None:
            try:
                await p.ws.close()
            except Exception:
                pass

    metrics.rooms.append({
        "room_code": room.code,
        "players": len(room.players),
        "seat_unique_ok": seat_ok,
        "hand_leak_count": len(room.leaks),
        "final_state_version": room.state_version,
    })
    for leak in room.leaks:
        leak["room_code"] = room.code
        metrics.leaks.append(leak)


def _choose_playable(hand: list[dict], game: dict) -> dict | None:
    """客户端侧简单合法性过滤：返回可出的 PLAY_CARD payload，否则 None。

    规则（与后端 can_play_card 对齐）：
      - wild / wild_draw_four 总是可出
      - 颜色匹配 current_color
      - 数字牌同数字、动作牌同 kind 匹配 top_discard
    """
    if not hand:
        return None
    current_color = game.get("current_color")
    top = game.get("top_discard") or {}

    for card in hand:
        kind = card.get("kind")
        if kind in ("wild", "wild_draw_four"):
            payload = {"card_id": card["card_id"]}
            payload["chosen_color"] = card.get("color") or "red"
            return payload
        if current_color is not None and card.get("color") == current_color:
            return {"card_id": card["card_id"]}
    for card in hand:
        kind = card.get("kind")
        if card.get("value") is not None and card.get("value") == top.get("value"):
            return {"card_id": card["card_id"]}
        if kind in ("skip", "reverse", "draw_two") and kind == top.get("kind"):
            return {"card_id": card["card_id"]}
    return None


async def _join(client: httpx.AsyncClient, code: str, idx: int, j: int) -> tuple[int, dict, float]:
    t0 = time.perf_counter()
    try:
        r = await client.post(f"{DEFAULT_BASE}/api/v1/rooms/{code}/join", json={"nickname": f"bot-{idx}-{j}"}, timeout=10.0)
        return r.status_code, r.json(), (time.perf_counter() - t0) * 1000
    except Exception as exc:
        return 0, {"error": str(exc)}, (time.perf_counter() - t0) * 1000


async def main(base: str) -> None:
    global DEFAULT_BASE
    DEFAULT_BASE = base
    metrics = Metrics()

    # 基线健康检查
    try:
        async with httpx.AsyncClient() as client:
            h = await client.get(f"{DEFAULT_BASE}/api/v1/health", timeout=10.0)
            print(f"[baseline] health={h.status_code} {h.text}")
    except Exception as exc:
        print(f"[baseline] health check failed: {exc}")
        sys.exit(1)

    print(f"[load-test] base={DEFAULT_BASE} rooms={len(ROOM_SIZES)} sizes={ROOM_SIZES} rounds={GAME_ROUNDS}")
    t_start = time.perf_counter()
    async with httpx.AsyncClient() as client:
        await asyncio.gather(*[
            run_room(i, size, client, metrics) for i, size in enumerate(ROOM_SIZES)
        ])
    total = time.perf_counter() - t_start

    summary = metrics.summary()
    summary["total_duration_s"] = round(total, 2)
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))

    out = "audits/load_test_report.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n[written] {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    args = ap.parse_args()
    asyncio.run(main(args.base))
