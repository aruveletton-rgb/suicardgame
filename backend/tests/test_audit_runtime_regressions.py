from __future__ import annotations

import random

import pytest

from backend.app.domain.cards import build_core_uno_deck
from backend.app.domain.room import GameState, Room, new_player
from backend.app.engine import command_handler, special_effects
from backend.app.engine.command_handler import Command, CommandError, process_command
from backend.app.repositories.json_store import room_from_snapshot, room_to_snapshot


def _card(asset_key: str):
    return next(card for card in build_core_uno_deck() if card.asset_key == asset_key)


def _started_room() -> tuple[Room, str]:
    host = new_player("host", 0, is_host=True)
    guest = new_player("guest", 1)
    room = Room(room_id="AUDIT1", host_player_id=host.player_id, players=[host, guest])
    for player in (host, guest):
        _command(room, player.player_id, f"ready-{player.seat_index}", "READY")
    _command(room, host.player_id, "start", "START_GAME", {"seed": 17})
    return room, host.player_id


def _command(room: Room, player_id: str, action_id: str, kind: str, payload: dict | None = None):
    return process_command(room, Command(action_id, room.room_id, player_id, kind, payload or {}))


@pytest.mark.parametrize("asset_key", ["uno_red_skip", "uno_red_reverse"])
def test_two_player_action_starts_new_clock_even_when_player_is_unchanged(monkeypatch, asset_key):
    room, host_id = _started_room()
    game = room.active_game
    assert game is not None
    played = _card(asset_key)
    room.player(host_id).hand = [played, _card("uno_blue_1"), _card("uno_green_2")]
    game.discard_pile = [_card("uno_red_5")]
    game.current_color = game.discard_pile[-1].color
    game.deck = [_card("uno_yellow_1") for _ in range(12)]
    game.turn_deadline_at = 1090.0
    old_sequence = game.turn_sequence
    monkeypatch.setattr(command_handler, "time", lambda: 1030.0)

    payload = {"card_id": played.card_id}
    result = _command(room, host_id, "play-action", "PLAY_CARD", payload)

    if asset_key == "uno_red_skip":
        target_id = room.players[1].player_id
        assert result["next_player_id"] == target_id
        assert game.special_state["action_stack"] == {"kind": "skip", "count": 1}
        assert game.turn_sequence == old_sequence + 1
        assert game.turn_deadline_at == 1210.0
        accepted = _command(room, target_id, "accept-skip", "ACCEPT_STACK")
        assert accepted["next_player_id"] == host_id
        assert "action_stack" not in game.special_state
        assert game.turn_sequence == old_sequence + 2
        assert game.turn_deadline_at == 1210.0
    else:
        assert result["next_player_id"] == host_id
        assert game.turn_sequence == old_sequence + 1
        assert game.turn_deadline_at == 1210.0
    assert not command_handler.pause_expired_step(room, prompt_id=None, now=1090.0)
    restored = room_from_snapshot(room_to_snapshot(room)).active_game
    assert restored is not None
    assert restored.turn_sequence == game.turn_sequence
    assert restored.turn_deadline_at == 1210.0
    assert _command(room, host_id, "play-action", "PLAY_CARD", payload) == result
    assert game.turn_sequence == old_sequence + (2 if asset_key == "uno_red_skip" else 1)
    assert game.turn_deadline_at == 1210.0


@pytest.mark.parametrize("asset_key", ["uno_red_draw_two", "uno_wild_draw_four"])
def test_penalty_card_starts_next_players_180_second_clock(monkeypatch, asset_key):
    room, host_id = _started_room()
    game = room.active_game
    assert game is not None
    next_player_id = room.players[1].player_id
    played = _card(asset_key)
    room.player(host_id).hand = [played, _card("uno_blue_1"), _card("uno_green_2")]
    game.discard_pile = [_card("uno_red_5")]
    game.current_color = game.discard_pile[-1].color
    game.deck = [_card("uno_yellow_1") for _ in range(12)]
    game.turn_deadline_at = 1090.0
    old_sequence = game.turn_sequence
    monkeypatch.setattr(command_handler, "time", lambda: 1030.0)

    payload = {"card_id": played.card_id}
    if asset_key == "uno_wild_draw_four":
        payload["chosen_color"] = "blue"
    result = _command(room, host_id, "play-penalty", "PLAY_CARD", payload)

    assert result["next_player_id"] == next_player_id
    assert game.turn_sequence == old_sequence + 1
    assert game.turn_deadline_at == 1210.0
    assert not command_handler.pause_expired_step(room, prompt_id=None, now=1090.0)
    assert _command(room, host_id, "play-penalty", "PLAY_CARD", payload) == result
    assert game.turn_sequence == old_sequence + 1
    assert game.turn_deadline_at == 1210.0


def test_same_turn_shop_and_rejected_draw_do_not_extend_clock(monkeypatch):
    room, host_id = _started_room()
    game = room.active_game
    assert game is not None
    game.turn_deadline_at = 1090.0
    old_sequence = game.turn_sequence
    monkeypatch.setattr(command_handler, "time", lambda: 1030.0)

    _command(room, host_id, "refresh", "REFRESH_SHOP")
    assert game.turn_sequence == old_sequence
    assert game.turn_deadline_at == 1090.0
    with pytest.raises(CommandError) as exc:
        _command(room, host_id, "invalid-draw", "DRAW_CARD")
    assert exc.value.code == "DRAW_NOT_ALLOWED"
    assert game.turn_sequence == old_sequence
    assert game.turn_deadline_at == 1090.0

    room.player(host_id).hand = [_card("uno_blue_1")]
    game.discard_pile = [_card("uno_red_5")]
    game.current_color = game.discard_pile[-1].color
    game.deck = [_card("uno_red_7")]
    result = _command(room, host_id, "valid-draw", "DRAW_CARD")
    assert result["drawn_count"] == 1
    assert result["next_player_id"] == host_id
    assert game.turn_sequence == old_sequence
    assert game.turn_deadline_at == 1090.0


@pytest.mark.parametrize("reshuffle", [command_handler._reshuffle_discard_into_deck, special_effects._reshuffle])
def test_seeded_reshuffle_repeats_across_new_and_restored_games(reshuffle):
    keys = ["uno_red_1", "uno_blue_2", "uno_green_3", "uno_yellow_4", "uno_red_5", "uno_blue_6", "uno_green_7", "uno_yellow_8"]

    def game():
        return GameState(
            game_id="seeded", game_epoch=1, seed=42,
            discard_pile=[*(_card(key) for key in keys), _card("uno_red_9")],
        )

    first = game()
    second = game()
    host = new_player("host", 0, is_host=True)
    room = Room(room_id="AUDIT2", host_player_id=host.player_id, players=[host], active_game=game())
    restored = room_from_snapshot(room_to_snapshot(room)).active_game
    assert restored is not None

    random_state = random.getstate()
    try:
        random.seed(1)
        reshuffle(first)
        random.seed(2)
        reshuffle(second)
        random.seed(3)
        reshuffle(restored)
    finally:
        random.setstate(random_state)

    expected = [card.asset_key for card in first.deck]
    assert [card.asset_key for card in second.deck] == expected
    assert [card.asset_key for card in restored.deck] == expected
    assert all(item.reshuffle_count == 1 for item in (first, second, restored))
    assert all(len(item.discard_pile) == 1 for item in (first, second, restored))


@pytest.mark.parametrize("reshuffle", [command_handler._reshuffle_discard_into_deck, special_effects._reshuffle])
def test_unseeded_reshuffle_keeps_process_randomness(reshuffle):
    keys = ["uno_red_1", "uno_blue_2", "uno_green_3", "uno_yellow_4", "uno_red_5", "uno_blue_6", "uno_green_7", "uno_yellow_8"]
    first = GameState(game_id="first", game_epoch=1, discard_pile=[*(_card(key) for key in keys), _card("uno_red_9")])
    second = GameState(game_id="second", game_epoch=1, discard_pile=[*(_card(key) for key in keys), _card("uno_red_9")])
    random_state = random.getstate()
    try:
        random.seed(1)
        reshuffle(first)
        random.seed(2)
        reshuffle(second)
    finally:
        random.setstate(random_state)
    assert [card.asset_key for card in first.deck] != [card.asset_key for card in second.deck]
