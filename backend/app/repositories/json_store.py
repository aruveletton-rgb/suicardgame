from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from backend.app.domain.cards import Card, CardCategory, CardColor
from backend.app.domain.room import (
    GameState,
    GameStatus,
    PauseState,
    PlayerSession,
    Prompt,
    PromptKind,
    PromptResolutionPolicy,
    PromptStatus,
    Room,
    RoomPhase,
    ShopState,
)


SNAPSHOT_SCHEMA_VERSION = 1


def _json_default(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"{type(value)!r} is not JSON serializable")


class JsonSnapshotStore:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def path_for_room(self, room_id: str) -> Path:
        return self.base_dir / f"{room_id}.json"

    def save(self, room_id: str, payload: Any) -> Path:
        target = self.path_for_room(room_id)
        with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=self.base_dir, suffix=".tmp") as tmp:
            json.dump(payload, tmp, ensure_ascii=False, indent=2, default=_json_default)
            tmp.write("\n")
            temp_name = tmp.name
        os.replace(temp_name, target)
        return target

    def save_room(self, room: Room) -> Path:
        return self.save(room.room_id, room_to_snapshot(room))

    def delete_room(self, room_id: str) -> None:
        """删除房间快照文件（不存在则静默忽略）。"""
        path = self.path_for_room(room_id)
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def load_room_snapshots(self) -> list[Room]:
        rooms: list[Room] = []
        for path in sorted(self.base_dir.glob("*.json")):
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            room = room_from_snapshot(payload)
            # A process restart invalidates every live transport. Reconnect is
            # the only supported way to make a persisted player online again.
            for player in room.players:
                player.online = False
            rooms.append(room)
        return rooms


def card_to_snapshot(card: Card) -> dict[str, Any]:
    return {
        "card_id": card.card_id,
        "category": card.category.value,
        "kind": card.kind,
        "asset_key": card.asset_key,
        "color": card.color.value if card.color is not None else None,
        "value": card.value,
        "display_name": card.display_name,
    }


def card_from_snapshot(payload: dict[str, Any]) -> Card:
    color = payload.get("color")
    return Card(
        card_id=payload["card_id"],
        category=CardCategory(payload["category"]),
        kind=payload["kind"],
        asset_key=payload["asset_key"],
        color=CardColor(color) if color is not None else None,
        value=payload.get("value"),
        display_name=payload.get("display_name"),
    )


def prompt_to_snapshot(prompt: Prompt) -> dict[str, Any]:
    return {
        "prompt_id": prompt.prompt_id,
        "kind": prompt.kind.value,
        "source_player_id": prompt.source_player_id,
        "source_card_id": prompt.source_card_id,
        "responder_ids": list(prompt.responder_ids),
        "legal_responses": list(prompt.legal_responses),
        "created_at": prompt.created_at,
        "deadline_at": prompt.deadline_at,
        "default_action": prompt.default_action,
        "state_version": prompt.state_version,
        "status": prompt.status.value,
        "resolution_policy": prompt.resolution_policy.value,
        "display_title": prompt.display_title,
        "display_message": prompt.display_message,
        "private_options_by_responder": prompt.private_options_by_responder,
        "response_records": prompt.response_records,
        "next_responder_index": prompt.next_responder_index,
        "resolved_by_player_id": prompt.resolved_by_player_id,
        "resolution_reason": prompt.resolution_reason,
        "game_id": prompt.game_id,
        "game_epoch": prompt.game_epoch,
        "resume_count": prompt.resume_count,
        "default_applied_count": prompt.default_applied_count,
        "closed": prompt.closed,
        "required": prompt.required,
    }


def prompt_from_snapshot(payload: dict[str, Any]) -> Prompt:
    closed = payload.get("closed", False)
    return Prompt(
        prompt_id=payload["prompt_id"],
        kind=PromptKind(payload["kind"]),
        source_player_id=payload.get("source_player_id"),
        source_card_id=payload.get("source_card_id"),
        responder_ids=list(payload.get("responder_ids", [])),
        legal_responses=list(payload.get("legal_responses", [])),
        created_at=payload["created_at"],
        deadline_at=payload["deadline_at"],
        default_action=payload["default_action"],
        state_version=payload["state_version"],
        status=PromptStatus(payload.get("status", PromptStatus.CANCELLED.value if closed else PromptStatus.OPEN.value)),
        resolution_policy=PromptResolutionPolicy(payload.get("resolution_policy", PromptResolutionPolicy.SINGLE.value)),
        display_title=payload.get("display_title"),
        display_message=payload.get("display_message"),
        private_options_by_responder={
            player_id: list(options)
            for player_id, options in payload.get("private_options_by_responder", {}).items()
        },
        response_records=dict(payload.get("response_records", {})),
        next_responder_index=payload.get("next_responder_index", 0),
        resolved_by_player_id=payload.get("resolved_by_player_id"),
        resolution_reason=payload.get("resolution_reason"),
        game_id=payload.get("game_id"),
        game_epoch=payload.get("game_epoch"),
        resume_count=payload.get("resume_count", 0),
        default_applied_count=payload.get("default_applied_count", 0),
        closed=closed,
        required=payload.get("required", False),
    )


def player_to_snapshot(player: PlayerSession) -> dict[str, Any]:
    return {
        "player_id": player.player_id,
        "reconnect_token": player.reconnect_token,
        "session_id": player.session_id,
        "nickname": player.nickname,
        "seat_index": player.seat_index,
        "avatar_id": player.avatar_id,
        "online": player.online,
        "is_host": player.is_host,
        "ready": player.ready,
        "hand": [card_to_snapshot(card) for card in player.hand],
        "last_seen_at": player.last_seen_at,
    }


def player_from_snapshot(payload: dict[str, Any]) -> PlayerSession:
    return PlayerSession(
        player_id=payload["player_id"],
        reconnect_token=payload["reconnect_token"],
        session_id=payload["session_id"],
        nickname=payload["nickname"],
        seat_index=payload["seat_index"],
        avatar_id=payload.get("avatar_id", "default"),
        online=payload.get("online", False),
        is_host=payload.get("is_host", False),
        ready=payload.get("ready", False),
        hand=[card_from_snapshot(card) for card in payload.get("hand", [])],
        last_seen_at=payload.get("last_seen_at"),
    )


def shop_to_snapshot(shop: ShopState) -> dict[str, Any]:
    return {
        "field_card": card_to_snapshot(shop.field_card) if shop.field_card is not None else None,
        "goods": [card_to_snapshot(card) for card in shop.goods],
        "bought_this_turn_by": sorted(shop.bought_this_turn_by),
        "refreshed_this_turn_by": sorted(shop.refreshed_this_turn_by),
    }


def shop_from_snapshot(payload: dict[str, Any]) -> ShopState:
    field_card = payload.get("field_card")
    return ShopState(
        field_card=card_from_snapshot(field_card) if field_card is not None else None,
        goods=[card_from_snapshot(card) for card in payload.get("goods", [])],
        bought_this_turn_by=set(payload.get("bought_this_turn_by", [])),
        refreshed_this_turn_by=set(payload.get("refreshed_this_turn_by", [])),
    )


def game_to_snapshot(game: GameState) -> dict[str, Any]:
    return {
        "game_id": game.game_id,
        "game_epoch": game.game_epoch,
        "status": game.status.value,
        "deck": [card_to_snapshot(card) for card in game.deck],
        "discard_pile": [card_to_snapshot(card) for card in game.discard_pile],
        "field_cards": [card_to_snapshot(card) for card in game.field_cards],
        "reveal_area": [card_to_snapshot(card) for card in game.reveal_area],
        "shop": shop_to_snapshot(game.shop),
        "current_player_id": game.current_player_id,
        "direction": game.direction,
        "current_color": game.current_color.value if game.current_color is not None else None,
        "current_prompt": prompt_to_snapshot(game.current_prompt) if game.current_prompt is not None else None,
        "turn_deadline_at": game.turn_deadline_at,
        "turn_sequence": game.turn_sequence,
        "pause_state": asdict(game.pause_state) if game.pause_state is not None else None,
        "last_prompt": prompt_to_snapshot(game.last_prompt) if game.last_prompt is not None else None,
        "effect_queue": list(game.effect_queue),
        "special_state": dict(game.special_state),
        "uno_pending_player_id": game.uno_pending_player_id,
        "uno_catchable_by": list(game.uno_catchable_by),
        "last_uno_event": game.last_uno_event,
        "winner_player_id": game.winner_player_id,
        "seed": game.seed,
        "reshuffle_count": game.reshuffle_count,
    }


def game_from_snapshot(payload: dict[str, Any]) -> GameState:
    current_color = payload.get("current_color")
    current_prompt = payload.get("current_prompt")
    last_prompt = payload.get("last_prompt")
    pause_state = payload.get("pause_state")
    return GameState(
        game_id=payload["game_id"],
        game_epoch=payload["game_epoch"],
        status=GameStatus(payload.get("status", GameStatus.ACTIVE.value)),
        deck=[card_from_snapshot(card) for card in payload.get("deck", [])],
        discard_pile=[card_from_snapshot(card) for card in payload.get("discard_pile", [])],
        field_cards=[card_from_snapshot(card) for card in payload.get("field_cards", [])],
        reveal_area=[card_from_snapshot(card) for card in payload.get("reveal_area", [])],
        shop=shop_from_snapshot(payload.get("shop", {})),
        current_player_id=payload.get("current_player_id"),
        direction=payload.get("direction", 1),
        current_color=CardColor(current_color) if current_color is not None else None,
        current_prompt=prompt_from_snapshot(current_prompt) if current_prompt is not None else None,
        turn_deadline_at=payload.get("turn_deadline_at"),
        turn_sequence=payload.get("turn_sequence", 0),
        pause_state=PauseState(**pause_state) if pause_state is not None else None,
        last_prompt=prompt_from_snapshot(last_prompt) if last_prompt is not None else None,
        effect_queue=list(payload.get("effect_queue", [])),
        special_state=dict(payload.get("special_state", {})),
        uno_pending_player_id=payload.get("uno_pending_player_id"),
        uno_catchable_by=list(payload.get("uno_catchable_by", [])),
        last_uno_event=payload.get("last_uno_event"),
        winner_player_id=payload.get("winner_player_id"),
        seed=payload.get("seed"),
        reshuffle_count=payload.get("reshuffle_count", 0),
    )


def room_to_snapshot(room: Room) -> dict[str, Any]:
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "room_id": room.room_id,
        "host_player_id": room.host_player_id,
        "players": [player_to_snapshot(player) for player in room.players],
        "phase": room.phase.value,
        "settings": room.settings,
        "active_game": game_to_snapshot(room.active_game) if room.active_game is not None else None,
        "game_history": list(room.game_history),
        "state_version": room.state_version,
        "room_version": room.room_version,
        "processed_actions": room.processed_actions,
        "closed_reason": room.closed_reason,
    }


def room_from_snapshot(payload: dict[str, Any]) -> Room:
    active_game = payload.get("active_game")
    return Room(
        room_id=payload["room_id"],
        host_player_id=payload["host_player_id"],
        players=[player_from_snapshot(player) for player in payload.get("players", [])],
        phase=RoomPhase(payload.get("phase", RoomPhase.LOBBY.value)),
        settings=dict(payload.get("settings", {})),
        active_game=game_from_snapshot(active_game) if active_game is not None else None,
        game_history=list(payload.get("game_history", [])),
        state_version=payload.get("state_version", 0),
        room_version=payload.get("room_version", 0),
        processed_actions=dict(payload.get("processed_actions", {})),
        closed_reason=payload.get("closed_reason"),
    )
