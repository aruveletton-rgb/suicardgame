from __future__ import annotations

import pytest

from backend.app.domain.cards import Card, iter_uno_specs
from backend.app.domain.room import Room, new_player
from backend.app.engine.bot import choose_bot_command, fallback_bot_prompt_command
from backend.app.engine.command_handler import Command, CommandError, process_command
from backend.app.engine.special_effects import expire_special_prompt
from backend.app.repositories.json_store import room_from_snapshot, room_to_snapshot
from backend.tests.ready_helpers import ready_all
from backend.tests.test_special_card_resolvers import activate, make_started_room as make_sui_room, respond, special, uno


def card(asset_key: str) -> Card:
    return Card.from_spec(next(spec for spec in iter_uno_specs() if spec.asset_key == asset_key))


def started_room(count: int = 3, *, bot_seats: tuple[int, ...] = ()):
    players = [new_player(f"p{seat}", seat, is_host=seat == 0, is_bot=seat in bot_seats) for seat in range(count)]
    room = Room("STACK01", players[0].player_id, players)
    ready_all(room)
    process_command(room, Command("start", room.room_id, players[0].player_id, "START_GAME", {"seed": 17}))
    game = room.active_game
    assert game is not None
    game.current_player_id = players[0].player_id
    game.discard_pile = [card("uno_red_5")]
    game.current_color = game.discard_pile[-1].color
    game.deck = [card("uno_green_1") for _ in range(20)]
    return room, players, game


def command(room, player, action_id, kind, payload=None):
    return process_command(room, Command(action_id, room.room_id, player.player_id, kind, payload or {}))


def test_draw_two_stacks_across_colors_then_accept_keeps_turn_and_is_idempotent():
    room, players, game = started_room()
    red_two = card("uno_red_draw_two")
    blue_two = card("uno_blue_draw_two")
    players[0].hand = [red_two, card("uno_green_9")]
    players[1].hand = [blue_two, card("uno_yellow_9")]
    players[2].hand = [card("uno_blue_7")]

    first = command(room, players[0], "red-two", "PLAY_CARD", {"card_id": red_two.card_id})
    assert first["drawn_count"] == 0
    assert game.special_state["action_stack"] == {"kind": "draw_two", "count": 2}
    assert game.current_player_id == players[1].player_id
    assert len(players[1].hand) == 2

    command(room, players[1], "blue-two", "PLAY_CARD", {"card_id": blue_two.card_id})
    assert game.special_state["action_stack"] == {"kind": "draw_two", "count": 4}
    assert game.current_color == blue_two.color
    assert game.current_player_id == players[2].player_id
    assert len(players[2].hand) == 1

    before_sequence = game.turn_sequence
    accepted = command(room, players[2], "accept-two", "ACCEPT_STACK")
    assert accepted["drawn_count"] == 4
    assert accepted["next_player_id"] == players[2].player_id
    assert len(players[2].hand) == 5
    assert "action_stack" not in game.special_state
    assert game.turn_sequence == before_sequence + 1
    assert command(room, players[2], "accept-two", "ACCEPT_STACK") == accepted
    assert len(players[2].hand) == 5
    command(room, players[2], "play-after-accept", "PLAY_CARD", {"card_id": players[2].hand[0].card_id})


def test_wild_draw_four_stacks_only_same_kind_and_requires_each_color_choice():
    room, players, game = started_room()
    first = card("uno_wild_draw_four")
    second = card("uno_wild_draw_four")
    players[0].hand = [first, card("uno_green_9")]
    players[1].hand = [second, card("uno_blue_9")]
    players[2].hand = [card("uno_blue_7")]

    command(room, players[0], "first-four", "PLAY_CARD", {"card_id": first.card_id, "chosen_color": "blue"})
    with pytest.raises(CommandError) as missing_color:
        command(room, players[1], "missing-color", "PLAY_CARD", {"card_id": second.card_id})
    assert missing_color.value.code == "COLOR_REQUIRED"
    assert game.special_state["action_stack"] == {"kind": "wild_draw_four", "count": 4}
    command(room, players[1], "second-four", "PLAY_CARD", {"card_id": second.card_id, "chosen_color": "green"})
    assert game.special_state["action_stack"] == {"kind": "wild_draw_four", "count": 8}
    assert game.current_color.value == "green"
    accepted = command(room, players[2], "accept-four", "ACCEPT_STACK")
    assert accepted["drawn_count"] == 8
    assert len(players[2].hand) == 9
    assert game.current_player_id == players[2].player_id


def test_skip_stack_skips_accumulated_seats_after_explicit_acceptance():
    room, players, game = started_room(5)
    first = card("uno_red_skip")
    second = card("uno_blue_skip")
    players[0].hand = [first, card("uno_green_9")]
    players[1].hand = [second, card("uno_yellow_9")]
    command(room, players[0], "skip-a", "PLAY_CARD", {"card_id": first.card_id})
    assert game.current_player_id == players[1].player_id
    assert game.special_state["action_stack"] == {"kind": "skip", "count": 1}
    command(room, players[1], "skip-b", "PLAY_CARD", {"card_id": second.card_id})
    assert game.current_player_id == players[2].player_id
    assert game.special_state["action_stack"] == {"kind": "skip", "count": 2}
    accepted = command(room, players[2], "accept-skip", "ACCEPT_STACK")
    assert accepted["drawn_count"] == 0
    assert game.current_player_id == players[4].player_id
    assert "action_stack" not in game.special_state


def test_pending_stack_blocks_other_actions_and_mixed_penalties():
    room, players, game = started_room()
    red_two = card("uno_red_draw_two")
    players[0].hand = [red_two, card("uno_green_9")]
    players[1].hand = [card("uno_wild_draw_four"), card("uno_blue_7")]
    command(room, players[0], "open-stack", "PLAY_CARD", {"card_id": red_two.card_id})
    before = (room.state_version, len(players[1].hand), len(game.deck))

    for index, (kind, payload) in enumerate([
        ("PLAY_CARD", {"card_id": players[1].hand[0].card_id, "chosen_color": "blue"}),
        ("DRAW_CARD", {}),
        ("ACTIVATE_SPECIAL", {"card_id": "missing"}),
        ("BUY_SHOP_GOOD", {}),
        ("REFRESH_SHOP", {}),
    ]):
        with pytest.raises(CommandError) as rejected:
            command(room, players[1], f"blocked-{index}", kind, payload)
        assert rejected.value.code in {"STACK_KIND_MISMATCH", "STACK_RESPONSE_REQUIRED"}
    assert before == (room.state_version, len(players[1].hand), len(game.deck))
    with pytest.raises(CommandError) as no_stack:
        command(room, players[0], "wrong-player-accept", "ACCEPT_STACK")
    assert no_stack.value.code == "NOT_YOUR_TURN"


@pytest.mark.parametrize("asset_key,count", [("uno_red_draw_two", 2), ("uno_wild_draw_four", 4)])
def test_final_penalty_card_draws_target_before_finishing(asset_key, count):
    room, players, game = started_room()
    final = card(asset_key)
    players[0].hand = [final]
    players[1].hand = [card("uno_blue_7")]
    result = command(room, players[0], "final", "PLAY_CARD", {"card_id": final.card_id, "chosen_color": "blue"})
    assert result["drawn_count"] == count
    assert len(players[1].hand) == 1 + count
    assert game.status.value == "FINISHED"
    assert game.winner_player_id == players[0].player_id
    assert "action_stack" not in game.special_state


def test_stack_snapshot_contains_only_public_scalars():
    room, players, game = started_room()
    penalty = card("uno_red_draw_two")
    players[0].hand = [penalty, card("uno_green_9")]
    command(room, players[0], "stack", "PLAY_CARD", {"card_id": penalty.card_id})
    snapshot = room_to_snapshot(room)
    restored = room_from_snapshot(snapshot)
    assert snapshot["active_game"]["special_state"]["action_stack"] == {"kind": "draw_two", "count": 2}
    assert restored.active_game.special_state["action_stack"] == {"kind": "draw_two", "count": 2}
    assert all("card_id" not in key for key in snapshot["active_game"]["special_state"]["action_stack"])


@pytest.mark.parametrize("has_matching", [True, False])
def test_bot_stacks_matching_card_or_accepts(has_matching):
    room, players, game = started_room(bot_seats=(1,))
    penalty = card("uno_red_draw_two")
    players[0].hand = [penalty, card("uno_green_9")]
    matching = card("uno_blue_draw_two")
    players[1].hand = [matching, card("uno_green_7")] if has_matching else [card("uno_green_7")]
    command(room, players[0], "stack", "PLAY_CARD", {"card_id": penalty.card_id})
    bot_command = choose_bot_command(room)
    assert bot_command is not None
    assert bot_command.command_type == ("PLAY_CARD" if has_matching else "ACCEPT_STACK")
    if has_matching:
        assert bot_command.payload["card_id"] == matching.card_id
    process_command(room, bot_command)


def test_bot_stacks_wild_draw_four_even_with_matching_color_in_hand():
    room, players, game = started_room(bot_seats=(1,))
    first = card("uno_wild_draw_four")
    second = card("uno_wild_draw_four")
    players[0].hand = [first, card("uno_green_9")]
    players[1].hand = [second, card("uno_blue_7")]
    command(room, players[0], "open-four", "PLAY_CARD", {"card_id": first.card_id, "chosen_color": "blue"})
    bot_command = choose_bot_command(room)
    assert bot_command is not None
    assert bot_command.command_type == "PLAY_CARD"
    assert bot_command.payload["card_id"] == second.card_id
    assert bot_command.payload["chosen_color"] in {"red", "yellow", "green", "blue"}
    process_command(room, bot_command)
    assert game.special_state["action_stack"] == {"kind": "wild_draw_four", "count": 8}


def test_bot_does_not_activate_wang_out_of_turn_during_human_stack_response():
    room, players, game = started_room(bot_seats=(2,))
    penalty = card("uno_red_draw_two")
    players[0].hand = [penalty, card("uno_green_9")]
    players[1].hand = [card("uno_green_7")]
    players[2].hand = [special("wang"), card("uno_blue_9")]
    command(room, players[0], "human-stack", "PLAY_CARD", {"card_id": penalty.card_id})
    assert game.current_player_id == players[1].player_id
    assert choose_bot_command(room) is None


def test_bot_wang_fallback_can_play_matching_wild_draw_four_in_stack():
    room, players, game = make_sui_room()
    players[2].is_bot = True
    wang = special("wang")
    first = uno("uno_wild_draw_four")
    second = uno("uno_wild_draw_four")
    players[0].hand = [uno("uno_green_9")]
    players[1].hand = [second, uno("uno_blue_7")]
    players[2].hand = [wang, first, uno("uno_green_8")]
    game.current_player_id = players[0].player_id
    game.discard_pile = [uno("uno_red_5")]
    game.current_color = game.discard_pile[-1].color
    activate(room, players[2], wang, {"target_player_id": players[0].player_id})
    respond(room, players[2], "control_play", {"card_id": first.card_id, "chosen_color": "blue"}, action_id="wang-first-four")
    assert game.current_prompt is not None
    game.current_prompt.default_action = "control_play"
    fallback = fallback_bot_prompt_command(room)
    assert fallback is not None
    assert fallback.payload["response"] == "control_play"
    assert fallback.payload["card_id"] == second.card_id


def test_wang_control_can_accept_draw_stack_and_keep_controlled_players_turn():
    room, players, game = make_sui_room()
    wang = special("wang")
    penalty = uno("uno_red_draw_two")
    playable = uno("uno_red_7")
    players[0].hand = [uno("uno_blue_9")]
    players[1].hand = [playable]
    players[2].hand = [wang, penalty, uno("uno_green_9")]
    game.current_player_id = players[0].player_id
    game.discard_pile = [uno("uno_red_5")]
    game.current_color = game.discard_pile[-1].color

    activate(room, players[2], wang, {"target_player_id": players[0].player_id})
    respond(room, players[2], "control_play", {"card_id": penalty.card_id}, action_id="wang-stack")
    assert game.special_state["action_stack"] == {"kind": "draw_two", "count": 2}
    assert game.current_player_id == players[1].player_id
    assert game.current_prompt is not None
    assert "control_accept_stack" in game.current_prompt.legal_responses

    before = len(players[1].hand)
    respond(room, players[2], "control_accept_stack", action_id="wang-accept")
    assert len(players[1].hand) == before + 2
    assert game.current_player_id == players[1].player_id
    assert "action_stack" not in game.special_state
    assert game.current_prompt is not None
    respond(room, players[2], "control_play", {"card_id": playable.card_id}, action_id="wang-after-accept")
    assert playable not in players[1].hand


@pytest.mark.parametrize("asset_key,expected_draw", [("uno_red_draw_two", 2), ("uno_red_skip", 0)])
def test_wang_stack_timeout_uses_accept_default(asset_key, expected_draw):
    room, players, game = make_sui_room()
    wang = special("wang")
    penalty = uno(asset_key)
    players[0].hand = [uno("uno_blue_9")]
    players[1].hand = [uno("uno_red_7")]
    players[2].hand = [wang, penalty, uno("uno_green_9")]
    game.current_player_id = players[0].player_id
    game.discard_pile = [uno("uno_red_5")]
    game.current_color = game.discard_pile[-1].color
    game.deck = [uno("uno_yellow_1") for _ in range(4)]

    activate(room, players[2], wang, {"target_player_id": players[0].player_id})
    respond(room, players[2], "control_play", {"card_id": penalty.card_id}, action_id="wang-timeout-stack")
    prompt = game.current_prompt
    assert prompt is not None
    assert prompt.default_action == "control_accept_stack"
    before = len(players[1].hand)
    assert expire_special_prompt(room, prompt.prompt_id, now=prompt.deadline_at + 1)
    assert len(players[1].hand) == before + expected_draw
    assert "action_stack" not in game.special_state
    assert game.current_player_id == players[1 if expected_draw else 2].player_id
