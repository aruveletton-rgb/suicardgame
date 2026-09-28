from __future__ import annotations

import asyncio
import json
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from threading import RLock
from time import time
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from backend.app.domain.room import MAX_PLAYERS, PromptKind, PromptResolutionPolicy, PromptStatus, Room, RoomPhase, make_room_code, new_player
from backend.app.engine.command_handler import Command, CommandError, expire_generic_response_window, process_command
from backend.app.engine.special_effects import expire_special_prompt
from backend.app.repositories.json_store import JsonSnapshotStore


# 未上线清理阈值：房间内所有玩家离线且离线时长超过该值则清理（秒）
ROOM_IDLE_TIMEOUT_SECONDS = 3600.0
# 后台清理扫描间隔（秒）
CLEANUP_INTERVAL_SECONDS = 300.0


@asynccontextmanager
async def lifespan(_app: FastAPI):
    cleanup_task = asyncio.create_task(_cleanup_idle_rooms_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()


app = FastAPI(title="Sui Card Game Rebuild", lifespan=lifespan)
rooms: dict[str, Room] = {}
rooms_lock = RLock()
snapshot_store = JsonSnapshotStore(Path(os.getenv("SUICARDGAME_DATA_DIR", "data/rooms")))


class WebSocketHub:
    def __init__(self) -> None:
        self._connections: dict[str, dict[WebSocket, str | None]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, room_code: str, websocket: WebSocket, player_id: str | None = None) -> None:
        async with self._lock:
            self._connections.setdefault(room_code, {})[websocket] = player_id

    async def authenticate(self, room_code: str, websocket: WebSocket, player_id: str) -> None:
        async with self._lock:
            connections = self._connections.get(room_code)
            if connections is not None and websocket in connections:
                connections[websocket] = player_id

    async def disconnect(self, room_code: str, websocket: WebSocket) -> bool:
        """移除连接；返回该 player 是否仍有其他活跃连接。

        True = 还有其他连接（或该连接未认证），不应据此将玩家置为离线。
        False = 该 player 已无任何连接。
        """
        async with self._lock:
            connections = self._connections.get(room_code)
            if connections is None:
                return True
            player_id = connections.pop(websocket, None)
            if not connections:
                self._connections.pop(room_code, None)
            if player_id is None:
                return True
            return any(pid == player_id for pid in connections.values())

    async def broadcast_state_patch(self, room: Room) -> None:
        payload = _public_snapshot(room)
        payload["event"] = "state_patch"
        async with self._lock:
            targets = list(self._connections.get(room.room_id, {}).items())
        stale: list[WebSocket] = []
        for websocket, player_id in targets:
            try:
                await websocket.send_json(payload)
                if player_id is not None:
                    await websocket.send_json(_private_snapshot(room, player_id))
            except (RuntimeError, WebSocketDisconnect):
                stale.append(websocket)
        for websocket in stale:
            await self.disconnect(room.room_id, websocket)


websocket_hub = WebSocketHub()
prompt_expiry_tasks: dict[tuple[str, str], asyncio.Task] = {}


SPECIAL_PROMPT_KINDS = {
    PromptKind.SUI_PLAYER_RESPONSE,
    PromptKind.NIAN_TURN_END_DISCARD,
    PromptKind.NIAN_CLAIM_WINDOW,
    PromptKind.CHONGYUE_CHALLENGE,
}


def _schedule_prompt_expiry(room: Room) -> None:
    with room.lock:
        game = room.active_game
        prompt = game.current_prompt if game is not None else None
        if prompt is None or prompt.status != PromptStatus.OPEN:
            return
        if prompt.kind == PromptKind.GENERIC_RESPONSE_WINDOW:
            expire_fn = expire_generic_response_window
        elif prompt.kind in SPECIAL_PROMPT_KINDS:
            expire_fn = expire_special_prompt
        else:
            return
        key = (room.room_id, prompt.prompt_id)
        if key in prompt_expiry_tasks:
            return
        delay = max(0.0, prompt.deadline_at - time())

    async def expire_later() -> None:
        try:
            await asyncio.sleep(delay)
            with room.lock:
                changed = expire_fn(room, key[1])
                if changed:
                    snapshot_store.save_room(room)
            if changed:
                await websocket_hub.broadcast_state_patch(room)
        finally:
            prompt_expiry_tasks.pop(key, None)

    prompt_expiry_tasks[key] = asyncio.create_task(expire_later())


class CreateRoomBody(BaseModel):
    nickname: str = Field(default="Guest", min_length=1, max_length=24)


class JoinRoomBody(BaseModel):
    nickname: str = Field(default="Guest", min_length=1, max_length=24)


class ReconnectBody(BaseModel):
    player_id: str
    reconnect_token: str


class CommandBody(BaseModel):
    action_id: str = Field(default_factory=lambda: uuid4().hex)
    player_id: str
    command_type: str
    payload: dict = Field(default_factory=dict)
    game_id: str | None = None
    game_epoch: int | None = None
    expected_state_version: int | None = None


def _session_from_authorization(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        return None
    return value


def _serialize_pending_action(room: Room, viewer_player_id: str | None = None) -> dict | None:
    game = room.active_game
    if game is None:
        return None
    prompt = game.current_prompt
    is_open = prompt is not None
    if prompt is None and game.last_prompt is not None and game.last_prompt.kind == PromptKind.GENERIC_RESPONSE_WINDOW:
        prompt = game.last_prompt
    if prompt is None:
        return None
    effect = next((item for item in game.effect_queue if item.get("prompt_id") == prompt.prompt_id), {}) if is_open else {}
    public_effect_keys = {
        "type",
        "source_card_kind",
        "source_player_id",
        "target_player_id",
        "controlled_player_id",
        "chosen_color",
        "required_color",
        "phase",
        "responder_index",
        "total_discarded",
        "used_colors",
        "displayed_colors",
        "drawn_until_four",
        "last_played",
        "advance_steps",
        "seen_event_id",
        "seen_source",
        "required_color",
        "immune_player_ids",
    }
    can_respond = False
    legal_responses: list[str] = []
    default_action: str | None = None
    if is_open and viewer_player_id is not None and viewer_player_id in prompt.responder_ids:
        if prompt.resolution_policy == PromptResolutionPolicy.SEQUENTIAL:
            can_respond = (
                prompt.next_responder_index < len(prompt.responder_ids)
                and prompt.responder_ids[prompt.next_responder_index] == viewer_player_id
            )
        else:
            can_respond = viewer_player_id not in prompt.response_records
        if can_respond:
            legal_responses = list(prompt.private_options_by_responder.get(viewer_player_id, prompt.legal_responses))
            default_action = prompt.default_action
    return {
        "prompt_id": prompt.prompt_id,
        "kind": prompt.kind.value,
        "source_player_id": prompt.source_player_id,
        "status": prompt.status.value,
        "resolution_policy": prompt.resolution_policy.value,
        "display_title": prompt.display_title,
        "display_message": prompt.display_message,
        "created_at": prompt.created_at,
        "deadline_at": prompt.deadline_at,
        "responder_count": len(prompt.responder_ids),
        "responded_count": len(prompt.response_records),
        "can_respond": can_respond,
        "legal_responses": legal_responses,
        "default_action": default_action,
        "resolution_reason": prompt.resolution_reason,
        "effect": {key: value for key, value in effect.items() if key in public_effect_keys},
    }


def _room_or_404(room_code: str) -> Room:
    with rooms_lock:
        room = rooms.get(room_code.upper())
    if room is None:
        raise HTTPException(status_code=404, detail="ROOM_NOT_FOUND")
    return room


def _persist_room(room: Room) -> None:
    with room.lock:
        snapshot_store.save_room(room)


def _room_is_idle(room: Room, now: float) -> bool:
    """房间内所有玩家都已离线且离线时长超过阈值，则该房间视为空闲可清理。"""
    if not room.players:
        return True
    for player in room.players:
        if player.online:
            return False
        if now - player.last_seen_at < ROOM_IDLE_TIMEOUT_SECONDS:
            return False
    return True


async def _cleanup_idle_rooms_loop() -> None:
    """后台周期任务：扫描并清理空闲房间（内存 + 磁盘）。"""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        now = time()
        with rooms_lock:
            idle_ids = [rid for rid, room in rooms.items() if _room_is_idle(room, now)]
        for room_id in idle_ids:
            with rooms_lock:
                rooms.pop(room_id, None)
            snapshot_store.delete_room(room_id)
        if idle_ids:
            print(f"[cleanup] removed {len(idle_ids)} idle rooms", flush=True)


def load_rooms_from_store() -> None:
    loaded_rooms = snapshot_store.load_room_snapshots()
    with rooms_lock:
        rooms.clear()
        for room in loaded_rooms:
            rooms[room.room_id.upper()] = room


def _serialize_room_state(room: Room, viewer_player_id: str | None = None) -> dict:
    game = room.active_game
    return {
        "room_code": room.room_id,
        "phase": room.phase.value,
        "state_version": room.state_version,
        "players": [
            {
                "player_id": player.player_id,
                "nickname": player.nickname,
                "seat_index": player.seat_index,
                "online": player.online,
                "is_host": player.is_host,
                "ready": player.ready,
                "hand_count": len(player.hand),
            }
            for player in room.seats_in_order()
        ],
        "active_game": None
        if game is None
        else {
            "game_id": game.game_id,
            "game_epoch": game.game_epoch,
            "status": game.status.value,
            "deck_count": len(game.deck),
            "discard_count": len(game.discard_pile),
            "shop_count": len(game.shop.goods),
            "field_count": len(game.field_cards),
            "current_player_id": game.current_player_id,
            "current_color": game.current_color,
            "direction": game.direction,
            "winner_player_id": game.winner_player_id,
            "top_discard": _serialize_card(game.discard_pile[-1]) if game.discard_pile else None,
            "shop_goods": [_serialize_card(card) for card in game.shop.goods],
            "field_card": _serialize_card(game.shop.field_card) if game.shop.field_card is not None else None,
            "reveal_area": [_serialize_card(card) for card in game.reveal_area],
            "pending_action": _serialize_pending_action(room, viewer_player_id),
            "special_state": dict(game.special_state),
            "uno": {
                "pending_player_id": game.uno_pending_player_id,
                "catchable_by": list(game.uno_catchable_by),
                "last_event": game.last_uno_event,
            },
        },
    }


def _serialize_card(card) -> dict:
    return {
        "card_id": card.card_id,
        "category": card.category.value,
        "kind": card.kind,
        "color": card.color.value if card.color is not None else None,
        "value": card.value,
        "asset_key": card.asset_key,
    }


def _public_snapshot(room: Room) -> dict:
    with room.lock:
        return {
            "event": "snapshot",
            "room_code": room.room_id,
            "state_version": room.state_version,
            "state": _serialize_room_state(room),
        }


def _private_snapshot(room: Room, player_id: str) -> dict:
    with room.lock:
        player = room.player(player_id)
        game = room.active_game
        uno_pending_player_id = game.uno_pending_player_id if game is not None else None
        uno_catchable_by = game.uno_catchable_by if game is not None else []
        return {
            "event": "private_snapshot",
            "room_code": room.room_id,
            "state_version": room.state_version,
            "state": _serialize_room_state(room, player_id),
            "you": {
                "player_id": player.player_id,
                "session_id": player.session_id,
                "seat_index": player.seat_index,
                "nickname": player.nickname,
                "is_host": player.is_host,
                "ready": player.ready,
                "online": player.online,
                "hand": [_serialize_card(card) for card in player.hand],
                "uno": {
                    "must_declare": uno_pending_player_id == player.player_id,
                    "can_catch_player_id": uno_pending_player_id if player.player_id in uno_catchable_by else None,
                },
            },
        }


def _player_for_session(room: Room, player_id: str | None, session_id: str | None):
    if not player_id or not session_id:
        return None
    with room.lock:
        try:
            player = room.player(player_id)
        except KeyError:
            return None
        if player.session_id != session_id:
            return None
        return player


def _player_for_session_id(room: Room, session_id: str | None):
    if not session_id:
        return None
    with room.lock:
        return next((player for player in room.players if player.session_id == session_id), None)


def _authenticated_player_from_authorization(room: Room, authorization: str | None):
    session_id = _session_from_authorization(authorization)
    if session_id is None:
        raise CommandError("认证信息缺失", code="AUTH_REQUIRED")
    player = _player_for_session_id(room, session_id)
    if player is None:
        raise CommandError("认证信息无效", code="AUTH_FAILED")
    return player


def _reconnect_player(room: Room, player_id: str, reconnect_token: str) -> dict:
    with room.lock:
        try:
            player = room.player(player_id)
        except KeyError as exc:
            raise CommandError("reconnect failed", code="RECONNECT_FAILED") from exc
        if player.reconnect_token != reconnect_token:
            raise CommandError("reconnect failed", code="RECONNECT_FAILED")
        new_reconnect_token = secrets.token_urlsafe(32)
        player.reconnect_token = new_reconnect_token
        player.session_id = uuid4().hex
        player.online = True
        player.last_seen_at = time()
        room.state_version += 1
        response = {
            "room_code": room.room_id,
            "player_id": player.player_id,
            "session_id": player.session_id,
            "reconnect_token": new_reconnect_token,
            "seat_index": player.seat_index,
            "is_host": player.is_host,
            "state_version": room.state_version,
            "private_snapshot": _private_snapshot(room, player.player_id),
        }
        snapshot_store.save_room(room)
    return response


def _command_from_body(room: Room, body: CommandBody, authenticated_player_id: str) -> Command:
    if body.player_id != authenticated_player_id:
        raise CommandError("命令玩家与认证身份不一致", code="AUTH_PLAYER_MISMATCH")
    return Command(
        action_id=body.action_id,
        room_id=room.room_id,
        player_id=authenticated_player_id,
        command_type=body.command_type,
        payload=body.payload,
        game_id=body.game_id,
        game_epoch=body.game_epoch,
        expected_state_version=body.expected_state_version,
    )


def _command_from_ws_message(room: Room, message: dict, authenticated_player_id: str) -> Command:
    command_type = message.get("command_type")
    if not isinstance(command_type, str) or not command_type:
        raise CommandError("command_type is required", code="COMMAND_TYPE_REQUIRED")
    message_player_id = message.get("player_id")
    if message_player_id is not None and message_player_id != authenticated_player_id:
        raise CommandError("命令玩家与认证身份不一致", code="AUTH_PLAYER_MISMATCH")
    payload = message.get("payload", {})
    if not isinstance(payload, dict):
        raise CommandError("payload must be an object", code="BAD_PAYLOAD")
    return Command(
        action_id=str(message.get("action_id") or uuid4().hex),
        room_id=room.room_id,
        player_id=authenticated_player_id,
        command_type=command_type,
        payload=payload,
        game_id=message.get("game_id"),
        game_epoch=message.get("game_epoch"),
        expected_state_version=message.get("expected_state_version"),
    )


def _process_room_command(room: Room, command: Command) -> tuple[dict, bool]:
    with room.lock:
        already_processed = command.action_id in room.processed_actions
        response = process_command(room, command)
    return response, not already_processed


async def _execute_room_command(room: Room, command: Command) -> dict:
    response, changed = _process_room_command(room, command)
    if changed:
        _persist_room(room)
        await websocket_hub.broadcast_state_patch(room)
        _schedule_prompt_expiry(room)
    return response


load_rooms_from_store()


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/v1/rooms")
def create_room(body: CreateRoomBody) -> dict:
    with rooms_lock:
        code = make_room_code(set(rooms))
        host = new_player(body.nickname, 0, is_host=True)
        room = Room(room_id=code, host_player_id=host.player_id, players=[host])
        rooms[code] = room
        _persist_room(room)
    return {
        "room_code": code,
        "player_id": host.player_id,
        "reconnect_token": host.reconnect_token,
        "session_id": host.session_id,
        "seat_index": host.seat_index,
        "is_host": True,
    }


@app.post("/api/v1/rooms/{room_code}/join")
async def join_room(room_code: str, body: JoinRoomBody) -> dict:
    room = _room_or_404(room_code)
    with room.lock:
        if room.phase == RoomPhase.CLOSED:
            raise HTTPException(status_code=404, detail="ROOM_NOT_FOUND")
        if room.phase != RoomPhase.LOBBY:
            raise HTTPException(status_code=409, detail="ROOM_NOT_JOINABLE")
        if len(room.players) >= MAX_PLAYERS:
            raise HTTPException(status_code=409, detail="ROOM_FULL")
        seat = min(set(range(MAX_PLAYERS)) - {player.seat_index for player in room.players})
        player = new_player(body.nickname, seat)
        room.players.append(player)
        room.state_version += 1
        response = {
            "room_code": room.room_id,
            "player_id": player.player_id,
            "reconnect_token": player.reconnect_token,
            "session_id": player.session_id,
            "seat_index": player.seat_index,
            "is_host": False,
        }
        snapshot_store.save_room(room)
    await websocket_hub.broadcast_state_patch(room)
    return response


@app.post("/api/v1/rooms/{room_code}/reconnect")
async def reconnect_room(room_code: str, body: ReconnectBody) -> dict:
    room = _room_or_404(room_code)
    try:
        response = _reconnect_player(room, body.player_id, body.reconnect_token)
    except CommandError as exc:
        raise HTTPException(status_code=403, detail={"error": exc.code, "message": str(exc)}) from exc
    await websocket_hub.broadcast_state_patch(room)
    _schedule_prompt_expiry(room)
    return response


@app.get("/api/v1/rooms/{room_code}/state")
def room_state(room_code: str) -> dict:
    room = _room_or_404(room_code)
    with room.lock:
        return _serialize_room_state(room)


@app.post("/api/v1/rooms/{room_code}/commands")
async def room_command(room_code: str, body: CommandBody, authorization: str | None = Header(default=None)) -> dict:
    room = _room_or_404(room_code)
    try:
        player = _authenticated_player_from_authorization(room, authorization)
        return await _execute_room_command(room, _command_from_body(room, body, player.player_id))
    except CommandError as exc:
        status_code = 401 if exc.code == "AUTH_REQUIRED" else 403 if exc.code in {"AUTH_FAILED", "AUTH_PLAYER_MISMATCH"} else 400
        raise HTTPException(status_code=status_code, detail={"error": exc.code, "message": str(exc)}) from exc


@app.websocket("/api/v1/rooms/{room_code}/ws")
async def room_websocket(websocket: WebSocket, room_code: str, player_id: str | None = None, session_id: str | None = None) -> None:
    await websocket.accept()
    room = None
    try:
        room = _room_or_404(room_code)
    except HTTPException:
        await websocket.send_json({"event": "error", "error": "ROOM_NOT_FOUND"})
        await websocket.close(code=1008)
        return

    authenticated_player_id: str | None = None
    authenticated_session_id: str | None = None

    if player_id is not None or session_id is not None:
        player = _player_for_session(room, player_id, session_id)
        if player is None:
            await websocket.close(code=1008)
            return
        authenticated_player_id = player.player_id
        authenticated_session_id = player.session_id
        with room.lock:
            player.online = True
            player.last_seen_at = time()

    await websocket.send_json(_public_snapshot(room))
    if authenticated_player_id is not None:
        await websocket.send_json(_private_snapshot(room, authenticated_player_id))
    await websocket_hub.connect(room.room_id, websocket, authenticated_player_id)
    try:
        while True:
            raw_message = await websocket.receive_text()
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                await websocket.send_json({"event": "error", "error": "BAD_JSON"})
                continue

            event = message.get("event")
            if event == "ping":
                with room.lock:
                    state_version = room.state_version
                    if authenticated_player_id is not None:
                        try:
                            room.player(authenticated_player_id).last_seen_at = time()
                        except KeyError:
                            pass
                await websocket.send_json({"event": "pong", "state_version": state_version})
            elif event == "get_state":
                await websocket.send_json(_public_snapshot(room))
            elif event == "authenticate":
                message_player_id = message.get("player_id") or player_id
                message_session_id = message.get("session_id")
                player = _player_for_session(room, message_player_id, message_session_id)
                if player is None:
                    await websocket.close(code=1008)
                    return
                authenticated_player_id = player.player_id
                authenticated_session_id = player.session_id
                await websocket_hub.authenticate(room.room_id, websocket, player.player_id)
                with room.lock:
                    player.online = True
                    player.last_seen_at = time()
                await websocket.send_json(_private_snapshot(room, authenticated_player_id))
            elif event == "command":
                if authenticated_player_id is None:
                    await websocket.send_json(
                        {
                            "event": "error",
                            "error": "AUTH_REQUIRED",
                            "message": "请先完成 WebSocket 认证",
                            "action_id": message.get("action_id"),
                        }
                    )
                    continue
                try:
                    command = _command_from_ws_message(room, message, authenticated_player_id)
                    response, changed = _process_room_command(room, command)
                except CommandError as exc:
                    await websocket.send_json({"event": "error", "error": exc.code, "message": str(exc), "action_id": message.get("action_id")})
                    continue
                await websocket.send_json({"event": "command_result", "action_id": command.action_id, "result": response})
                if changed:
                    _persist_room(room)
                    await websocket_hub.broadcast_state_patch(room)
                    _schedule_prompt_expiry(room)
            else:
                await websocket.send_json({"event": "error", "error": "UNKNOWN_WS_EVENT"})
    except WebSocketDisconnect:
        still_connected = await websocket_hub.disconnect(room.room_id, websocket)
        if authenticated_player_id is not None and authenticated_session_id is not None and not still_connected:
            should_broadcast = False
            with room.lock:
                try:
                    player = room.player(authenticated_player_id)
                except KeyError:
                    player = None
                if player is not None and player.session_id == authenticated_session_id:
                    player.online = False
                    player.last_seen_at = time()
                    room.state_version += 1
                    snapshot_store.save_room(room)
                    should_broadcast = True
            if should_broadcast:
                await websocket_hub.broadcast_state_patch(room)
        return
