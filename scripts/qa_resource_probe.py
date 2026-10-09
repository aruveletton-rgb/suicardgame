from __future__ import annotations

import argparse
import asyncio
import json
from time import monotonic

import httpx
import websockets


def create_room(base_url: str) -> tuple[str, list[dict]]:
    with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
        host_response = client.post("/api/v1/rooms", json={"nickname": "Load Host"})
        host_response.raise_for_status()
        host = host_response.json()
        players = [host]
        for index in range(1, 5):
            response = client.post(
                f"/api/v1/rooms/{host['room_code']}/join",
                json={"nickname": f"Load Guest {index}"},
            )
            response.raise_for_status()
            players.append(response.json())
        for index, player in enumerate(players):
            response = client.post(
                f"/api/v1/rooms/{host['room_code']}/commands",
                headers={"Authorization": f"Bearer {player['session_id']}"},
                json={
                    "action_id": f"resource-ready-{index}",
                    "player_id": player["player_id"],
                    "command_type": "READY",
                    "payload": {"ready": True},
                },
            )
            response.raise_for_status()
        start_response = client.post(
            f"/api/v1/rooms/{host['room_code']}/commands",
            headers={"Authorization": f"Bearer {host['session_id']}"},
            json={
                "action_id": "resource-start",
                "player_id": host["player_id"],
                "command_type": "START_GAME",
                "payload": {"seed": 20260928},
            },
        )
        start_response.raise_for_status()
        return host["room_code"], players


async def hold_connection(ws_base_url: str, room_code: str, player: dict, duration: float) -> int:
    uri = f"{ws_base_url}/api/v1/rooms/{room_code}/ws"
    messages = 0
    async with websockets.connect(uri, open_timeout=10, close_timeout=5, proxy=None) as websocket:
        await websocket.recv()
        await websocket.send(
            json.dumps(
                {
                    "event": "authenticate",
                    "player_id": player["player_id"],
                    "session_id": player["session_id"],
                }
            )
        )
        await websocket.recv()
        deadline = monotonic() + duration
        while monotonic() < deadline:
            await websocket.send(json.dumps({"event": "ping"}))
            await websocket.recv()
            messages += 1
            await asyncio.sleep(0.2)
    return messages


async def run(base_url: str, ws_base_url: str, duration: float) -> None:
    room_code, players = create_room(base_url)
    counts = await asyncio.gather(
        *(hold_connection(ws_base_url, room_code, player, duration) for player in players)
    )
    print(
        json.dumps(
            {
                "room_code_redacted": f"{room_code[:2]}****",
                "players": len(players),
                "websocket_connections": len(players),
                "ping_messages": sum(counts),
                "duration_seconds": duration,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--ws-base-url", required=True)
    parser.add_argument("--duration", type=float, default=15.0)
    args = parser.parse_args()
    asyncio.run(run(args.base_url, args.ws_base_url, args.duration))
