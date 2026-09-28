from __future__ import annotations

import secrets
import string
from threading import RLock
from dataclasses import dataclass, field
from enum import StrEnum
from time import time
from uuid import uuid4

from backend.app.domain.cards import Card, CardColor


MIN_PLAYERS = 2
MAX_PLAYERS = 5
AVATAR_IDS = frozenset({
    "default", "wang", "ji", "yu", "yi", "zuole", "xi", "nian",
    "sui_xiang", "shu", "chongyue", "ling", "fuzhou",
})


class RoomPhase(StrEnum):
    LOBBY = "LOBBY"
    STARTING = "STARTING"
    IN_GAME = "IN_GAME"
    ROUND_RESULT = "ROUND_RESULT"
    RESETTING = "RESETTING"
    CLOSED = "CLOSED"


class GameStatus(StrEnum):
    ACTIVE = "ACTIVE"
    FINISHED = "FINISHED"
    ABORTED_BY_ROOM_RESET = "ABORTED_BY_ROOM_RESET"


class PromptKind(StrEnum):
    TURN_MAIN = "TURN_MAIN"
    DRAWN_CARD_DECISION = "DRAWN_CARD_DECISION"
    UNO_WINDOW = "UNO_WINDOW"
    WILD_DRAW_FOUR_CHALLENGE = "WILD_DRAW_FOUR_CHALLENGE"
    SUI_REACTION = "SUI_REACTION"
    SUI_PLAYER_RESPONSE = "SUI_PLAYER_RESPONSE"
    NIAN_TURN_END_DISCARD = "NIAN_TURN_END_DISCARD"
    NIAN_CLAIM_WINDOW = "NIAN_CLAIM_WINDOW"
    CHONGYUE_CHALLENGE = "CHONGYUE_CHALLENGE"
    HAS_SUI_CHALLENGE = "HAS_SUI_CHALLENGE"
    GENERIC_RESPONSE_WINDOW = "GENERIC_RESPONSE_WINDOW"


class PromptStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class PromptResolutionPolicy(StrEnum):
    SINGLE = "single"
    FIRST_WINS = "first_wins"
    SEQUENTIAL = "sequential"
    ALL = "all"


@dataclass
class Prompt:
    prompt_id: str
    kind: PromptKind
    source_player_id: str | None
    source_card_id: str | None
    responder_ids: list[str]
    legal_responses: list[str]
    created_at: float
    deadline_at: float
    default_action: str
    state_version: int
    status: PromptStatus = PromptStatus.OPEN
    resolution_policy: PromptResolutionPolicy = PromptResolutionPolicy.SINGLE
    display_title: str | None = None
    display_message: str | None = None
    private_options_by_responder: dict[str, list[str]] = field(default_factory=dict)
    response_records: dict[str, str] = field(default_factory=dict)
    next_responder_index: int = 0
    resolved_by_player_id: str | None = None
    resolution_reason: str | None = None
    game_id: str | None = None
    game_epoch: int | None = None
    resume_count: int = 0
    default_applied_count: int = 0
    closed: bool = False
    required: bool = False


@dataclass
class PauseState:
    reason: str
    prompt_id: str | None
    step_kind: str
    paused_at: float


@dataclass
class PlayerSession:
    player_id: str
    reconnect_token: str
    session_id: str
    nickname: str
    seat_index: int
    avatar_id: str = "default"
    online: bool = True
    is_host: bool = False
    ready: bool = False
    hand: list[Card] = field(default_factory=list)
    last_seen_at: float = field(default_factory=time)


@dataclass
class ShopState:
    field_card: Card | None = None
    goods: list[Card] = field(default_factory=list)
    bought_this_turn_by: set[str] = field(default_factory=set)
    refreshed_this_turn_by: set[str] = field(default_factory=set)


@dataclass
class GameState:
    game_id: str
    game_epoch: int
    status: GameStatus = GameStatus.ACTIVE
    deck: list[Card] = field(default_factory=list)
    discard_pile: list[Card] = field(default_factory=list)
    field_cards: list[Card] = field(default_factory=list)
    reveal_area: list[Card] = field(default_factory=list)
    shop: ShopState = field(default_factory=ShopState)
    current_player_id: str | None = None
    direction: int = 1
    current_color: CardColor | None = None
    current_prompt: Prompt | None = None
    turn_deadline_at: float | None = None
    turn_sequence: int = 0
    pause_state: PauseState | None = None
    last_prompt: Prompt | None = None
    effect_queue: list[dict] = field(default_factory=list)
    special_state: dict = field(default_factory=dict)
    uno_pending_player_id: str | None = None
    uno_catchable_by: list[str] = field(default_factory=list)
    last_uno_event: dict | None = None
    winner_player_id: str | None = None
    seed: int | None = None
    reshuffle_count: int = 0


@dataclass
class Room:
    room_id: str
    host_player_id: str
    players: list[PlayerSession]
    phase: RoomPhase = RoomPhase.LOBBY
    settings: dict = field(default_factory=dict)
    active_game: GameState | None = None
    game_history: list[dict] = field(default_factory=list)
    state_version: int = 0
    room_version: int = 0
    processed_actions: dict[str, dict] = field(default_factory=dict)
    closed_reason: str | None = None
    lock: RLock = field(default_factory=RLock, repr=False, compare=False)

    def player(self, player_id: str) -> PlayerSession:
        for player in self.players:
            if player.player_id == player_id:
                return player
        raise KeyError(player_id)

    def seats_in_order(self) -> list[PlayerSession]:
        return sorted(self.players, key=lambda player: player.seat_index)

    def next_epoch(self) -> int:
        if self.active_game is None:
            return self.room_version + 1
        return self.active_game.game_epoch + 1


def make_room_code(existing: set[str] | None = None) -> str:
    existing = existing or set()
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(6))
        if code not in existing:
            return code


def new_player(nickname: str, seat_index: int, *, is_host: bool = False, avatar_id: str = "default") -> PlayerSession:
    return PlayerSession(
        player_id=uuid4().hex,
        reconnect_token=secrets.token_urlsafe(32),
        session_id=uuid4().hex,
        nickname=nickname,
        seat_index=seat_index,
        avatar_id=avatar_id,
        is_host=is_host,
    )
