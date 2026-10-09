#!/usr/bin/env python3
"""Run a bounded one-room/five-client load against an isolated backend."""

from __future__ import annotations

import argparse
import asyncio
import json
from time import perf_counter
from uuid import uuid4

import httpx
import websockets


async def _receive_event(socket, expected: str) -> dict:
    while True:
        message = json.loads(await socket.recv())
        if message.get("event") == expected:
            return message


async def _command(client: httpx.AsyncClient, room_code: str, session: dict, command_type: str) -> dict:
    response = await client.post(
        f"/api/v1/rooms/{room_code}/commands",
        headers={"Authorization": f"Bearer {session['session_id']}"},
        json={
            "action_id": uuid4().hex,
            "player_id": session["player_id"],
            "command_type": command_type,
            "payload": {},
        },
    )
    response.raise_for_status()
    return response.json()


async def run(base_url: str, duration: float, interval: float) -> dict:
    base_url = base_url.rstrip("/")
    ws_base = base_url.replace("http://", "ws://", 1).replace("https://", "wss://", 1)
    timeout = httpx.Timeout(10.0)
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        health = await client.get("/api/v1/health")
        health.raise_for_status()
        host = (await client.post("/api/v1/rooms", json={"nickname": "g8-host"})).json()
        room_code = host["room_code"]
        players = [host]
        for index in range(1, 5):
            response = await client.post(
                f"/api/v1/rooms/{room_code}/join",
                json={"nickname": f"g8-p{index}"},
            )
            response.raise_for_status()
            players.append(response.json())
        sixth = await client.post(
            f"/api/v1/rooms/{room_code}/join",
            json={"nickname": "g8-overflow"},
        )

        sockets = []
        try:
            for player in players:
                socket = await websockets.connect(
                    f"{ws_base}/api/v1/rooms/{room_code}/ws"
                    f"?player_id={player['player_id']}&session_id={player['session_id']}",
                    open_timeout=10,
                    close_timeout=5,
                    max_size=2**20,
                )
                sockets.append(socket)
                await _receive_event(socket, "snapshot")
                await _receive_event(socket, "private_snapshot")

            for player in players:
                await _command(client, room_code, player, "READY")
            start_result = await _command(client, room_code, host, "START_GAME")

            sent = 0
            received = 0
            latencies_ms = []
            deadline = perf_counter() + duration
            while perf_counter() < deadline:
                for socket in sockets:
                    started_at = perf_counter()
                    await socket.send(json.dumps({"event": "ping"}))
                    await _receive_event(socket, "pong")
                    latencies_ms.append((perf_counter() - started_at) * 1000)
                    sent += 1
                    received += 1
                    await socket.send(json.dumps({"event": "get_state"}))
                    await _receive_event(socket, "snapshot")
                    sent += 1
                    received += 1
                await asyncio.sleep(interval)

            state = (await client.get(f"/api/v1/rooms/{room_code}/state")).json()
            return {
                "room_count": 1,
                "player_count": len(players),
                "websocket_connections": len(sockets),
                "sixth_player_status": sixth.status_code,
                "sixth_player_rejected": sixth.status_code == 409,
                "game_started": bool(start_result.get("ok")),
                "game_status": state.get("active_game", {}).get("status"),
                "duration_seconds": duration,
                "messages_sent": sent,
                "messages_received": received,
                "average_round_trip_ms": round(sum(latencies_ms) / len(latencies_ms), 3),
                "peak_round_trip_ms": round(max(latencies_ms), 3),
            }
        finally:
            await asyncio.gather(*(socket.close() for socket in sockets), return_exceptions=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--duration", type=float, default=20.0)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = asyncio.run(run(args.base_url, args.duration, args.interval))
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
