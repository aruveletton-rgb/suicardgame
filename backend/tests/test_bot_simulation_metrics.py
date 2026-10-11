from __future__ import annotations

import json
import sys

import pytest

from backend.app.domain.cards import build_core_uno_deck
from backend.app.engine.command_handler import Command
from scripts import bot_simulation as simulation


def _card(key):
    return next(card for card in build_core_uno_deck() if card.asset_key == key)


def _controlled_start(monkeypatch, *, playable=False):
    start = simulation.start_game

    def controlled(room, seed):
        start(room, seed)
        game = room.active_game
        game.discard_pile = [_card("uno_red_5")]
        game.current_color = game.discard_pile[-1].color
        room.player(game.current_player_id).hand = [
            _card("uno_red_7" if playable else "uno_blue_9")
        ]
        game.deck = [_card("uno_red_1")]

    monkeypatch.setattr(simulation, "start_game", controlled)


@pytest.mark.parametrize(
    "kind,payload,playable,error,fallback_success,fallback_errors,stall",
    [
        ("UNKNOWN_COMMAND", {}, False, "UNKNOWN_COMMAND", 1, {}, None),
        ("PLAY_CARD", {"card_id": "absent"}, True, "CARD_NOT_IN_HAND", 0,
         {"DRAW_NOT_ALLOWED": 1}, "fallback:DRAW_NOT_ALLOWED"),
        ("DRAW_CARD", {}, True, "DRAW_NOT_ALLOWED", 0, {}, "command:DRAW_NOT_ALLOWED"),
    ],
)
def test_real_command_errors_and_fallbacks_are_reported(
    monkeypatch, kind, payload, playable, error, fallback_success, fallback_errors, stall
):
    _controlled_start(monkeypatch, playable=playable)

    def rejected_policy(room):
        return Command("probe", room.room_id, room.active_game.current_player_id, kind, payload)

    monkeypatch.setattr(simulation, "choose_bot_command", rejected_policy)
    result = simulation.run_game(simulation.make_room(2), seed=1, max_steps=1)
    assert result["primary_command_rejection_count"] == 1
    assert result["primary_command_rejections"] == {error: 1}
    assert result["fallback_success_count"] == fallback_success
    assert result["fallback_rejection_count"] == sum(fallback_errors.values())
    assert result["fallback_rejections"] == fallback_errors
    assert result["stall_reason"] == stall


def test_summary_includes_successful_fallbacks_and_primary_errors(monkeypatch, capsys):
    _controlled_start(monkeypatch)
    monkeypatch.setattr(simulation, "choose_bot_command", lambda room: Command(
        "probe", room.room_id, room.active_game.current_player_id, "UNKNOWN_COMMAND", {}
    ))
    monkeypatch.setattr(sys, "argv", ["bot_simulation.py", "--games", "2", "--max-steps", "1"])
    with pytest.raises(SystemExit) as exc:
        simulation.main()
    assert exc.value.code == 1
    summary = json.loads(capsys.readouterr().out)["summary"]
    assert summary["primary_command_rejection_count"] == 2
    assert summary["primary_command_rejections"] == {"UNKNOWN_COMMAND": 2}
    assert summary["fallback_success_count"] == 2
    assert summary["fallback_rejection_count"] == 0
    assert summary["fallback_rejections"] == {}


def test_winner_seat_is_stable_across_seeded_runs():
    first = simulation.run_game(simulation.make_room(2), seed=1, max_steps=20_000)
    second = simulation.run_game(simulation.make_room(2), seed=1, max_steps=20_000)
    assert first["finished"] and second["finished"]
    assert first["winner"] is not None
    assert first["winner_seat_index"] in (0, 1)
    assert {key: value for key, value in first.items() if key != "winner"} == {
        key: value for key, value in second.items() if key != "winner"
    }
