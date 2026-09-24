from __future__ import annotations

from collections import defaultdict

from backend.app.domain.room import GameState, PromptStatus, Room, RoomPhase


class InvariantError(AssertionError):
    pass


def card_locations(room: Room) -> dict[str, list[str]]:
    locations: dict[str, list[str]] = defaultdict(list)
    game = room.active_game
    for player in room.players:
        for card in player.hand:
            locations[card.card_id].append(f"player:{player.player_id}:hand")
    if game is not None:
        for card in game.deck:
            locations[card.card_id].append("deck")
        for card in game.discard_pile:
            locations[card.card_id].append("discard")
        for card in game.field_cards:
            locations[card.card_id].append("field")
        for card in game.reveal_area:
            locations[card.card_id].append("reveal")
        for card in game.shop.goods:
            locations[card.card_id].append("shop")
        if game.shop.field_card is not None:
            locations[game.shop.field_card.card_id].append("shop_field_card")
    return dict(locations)


def assert_card_uniqueness(room: Room) -> None:
    duplicates = {card_id: locs for card_id, locs in card_locations(room).items() if len(locs) != 1}
    if duplicates:
        raise InvariantError(f"card must exist in exactly one zone: {duplicates}")


def assert_single_current_player(game: GameState) -> None:
    if game.current_player_id is None:
        return
    if not isinstance(game.current_player_id, str):
        raise InvariantError("current_player_id must be a string or None")


def assert_single_prompt(game: GameState) -> None:
    if game.current_prompt and (game.current_prompt.closed or game.current_prompt.status != PromptStatus.OPEN):
        raise InvariantError("only an open prompt may remain active")
    if game.last_prompt and (not game.last_prompt.closed or game.last_prompt.status == PromptStatus.OPEN):
        raise InvariantError("last prompt must be closed")


def assert_room_invariants(room: Room) -> None:
    assert_card_uniqueness(room)
    if room.phase == RoomPhase.LOBBY and room.active_game is not None:
        if room.active_game.status.value == "ACTIVE":
            raise InvariantError("lobby cannot keep an active game")
    if room.active_game is not None:
        assert_single_current_player(room.active_game)
        assert_single_prompt(room.active_game)
