from time import time

import pytest

from backend.app.domain.room import Prompt, PromptKind
from backend.app.engine.command_handler import Command, CommandError, pause_expired_step, process_command
from backend.app.engine.special_effects import expire_special_prompt
from backend.app.repositories.json_store import room_from_snapshot, room_to_snapshot
from backend.tests.ready_helpers import pass_sui_activation_reactions
from backend.tests.test_chongyue_exact_rules import four_colors, reveal
from backend.tests.test_special_card_resolvers import activate, make_started_room, respond, special, uno


def setup_flow(*, direction=1, source_index=0):
    room, players, game = make_started_room()
    card = special("chongyue")
    for index, player in enumerate(players):
        player.hand = four_colors(index + 1)
    source = players[source_index]
    source.hand.insert(0, card)
    game.direction = direction
    game.current_player_id = source.player_id
    activate(room, source, card)
    return room, players, game


def test_reverse_order_starts_with_next_player_then_source_last():
    room, players, game = setup_flow(direction=-1, source_index=2)
    effect = game.effect_queue[0]
    assert effect["reveal_order"] == [players[1].player_id, players[0].player_id, players[2].player_id]
    reveal(room, players[1])
    respond(room, players[1], "decline_challenge")
    assert game.current_prompt.responder_ids == [players[0].player_id]
    reveal(room, players[0])
    respond(room, players[0], "decline_challenge")
    assert game.current_prompt.responder_ids == [players[2].player_id]
    reveal(room, players[2])
    assert game.current_prompt is None
    assert game.current_player_id == players[1].player_id


def test_each_manual_draw_is_exactly_one_card_and_all_drawn_faces_are_public():
    room, players, game = setup_flow()
    players[1].hand = [uno("uno_red_2")]
    game.deck = [uno("uno_blue_4"), uno("uno_green_4"), uno("uno_yellow_4"), uno("uno_wild"), uno("uno_red_4")]
    reveal(room, players[1])
    effect = game.effect_queue[0]
    for draw_index in range(5):
        before = len(players[1].hand)
        respond(room, players[1], "draw_one", action_id=f"one-{draw_index}")
        assert len(players[1].hand) == before + 1
        assert effect["drawn_until_four"][players[1].player_id] == draw_index + 1
        assert len(effect["displayed_cards"][players[1].player_id]) == draw_index + 2
    assert effect["phase"] == "challenge"
    assert effect["displayed_colors"][players[1].player_id] == ["red", "yellow", "green", "blue"]


def test_successful_challenge_fills_source_manually_and_stops_future_players():
    room, players, game = setup_flow()
    players[0].hand = [uno("uno_red_1")]
    players[2].hand = [uno("uno_red_3")]
    game.deck = [uno("uno_red_9"), uno("uno_blue_4"), uno("uno_green_4"), uno("uno_yellow_4")]
    future_hand = list(players[2].hand)
    reveal(room, players[1])
    respond(room, players[1], "challenge")
    effect = game.effect_queue[0]
    assert effect["challenge_result"] == "challenge_succeeded"
    assert effect["phase"] == "source_check"
    assert len(players[0].hand) == 1
    reveal(room, players[0])
    assert effect["phase"] == "source_draw"
    for draw_index in range(3):
        respond(room, players[0], "draw_one", action_id=f"fill-{draw_index}")
    assert game.current_prompt is None
    assert players[2].hand == future_hand
    assert len(players[1].hand) == 4
    assert len(players[0].hand) == 4
    assert len(game.deck) == 1


@pytest.mark.parametrize("bad_selection", ["duplicate", "same_color", "foreign", "missing", "colorless"])
def test_invalid_display_does_not_mutate_hands_or_effect(bad_selection):
    room, players, game = setup_flow()
    player = players[1]
    player.hand.extend([uno("uno_red_7"), uno("uno_wild")])
    selected = [card.card_id for card in player.hand[:4]]
    if bad_selection == "duplicate":
        selected[1] = selected[0]
    elif bad_selection == "same_color":
        selected[1] = player.hand[4].card_id
    elif bad_selection == "foreign":
        selected[1] = players[0].hand[1].card_id
    elif bad_selection == "missing":
        selected.pop()
    else:
        selected[1] = player.hand[-1].card_id
    before = room_to_snapshot(room)
    with pytest.raises(CommandError):
        respond(room, player, "submit_cards", {"card_ids": selected}, action_id="bad")
    assert room_to_snapshot(room) == before


def test_required_timeout_keeps_display_step_and_optional_challenge_advances():
    room, players, game = setup_flow()
    prompt = game.current_prompt
    assert prompt.required
    assert prompt.deadline_at - prompt.created_at == 180
    assert not expire_special_prompt(room, prompt.prompt_id, now=prompt.deadline_at + 1)
    assert game.current_prompt is prompt
    reveal(room, players[1])
    challenge = game.current_prompt
    assert not challenge.required
    assert challenge.deadline_at - challenge.created_at == 10
    assert expire_special_prompt(room, challenge.prompt_id, now=challenge.deadline_at + 1)
    assert game.current_prompt.responder_ids == [players[2].player_id]


def test_draw_command_is_idempotent_and_stale_prompt_cannot_draw_again():
    room, players, game = setup_flow()
    players[1].hand = [uno("uno_red_2")]
    reveal(room, players[1])
    prompt_id = game.current_prompt.prompt_id
    command = Command(action_id="same-draw", room_id=room.room_id, player_id=players[1].player_id,
                      command_type="RESPOND_TO_PROMPT", payload={"prompt_id": prompt_id, "response": "draw_one"})
    first = process_command(room, command)
    before = room_to_snapshot(room)
    assert process_command(room, command) == first
    assert room_to_snapshot(room) == before
    with pytest.raises(CommandError) as error:
        process_command(room, Command(action_id="stale-draw", room_id=room.room_id, player_id=players[1].player_id,
                                     command_type="RESPOND_TO_PROMPT", payload=command.payload))
    assert error.value.code == "STALE_PROMPT"


def test_exhausted_deck_finishes_without_filling_future_players():
    room, players, game = setup_flow()
    players[1].hand = [uno("uno_red_2")]
    players[2].hand = [uno("uno_red_3")]
    game.deck = []
    game.reshuffle_count = 1
    reveal(room, players[1])
    result = respond(room, players[1], "draw_one")
    assert result["deck_exhausted"] is True
    assert game.current_prompt is None
    assert len(players[2].hand) == 1


def test_partial_public_display_survives_snapshot_without_duplicate_card_ownership():
    room, players, game = setup_flow()
    players[1].hand = [uno("uno_red_2")]
    reveal(room, players[1])
    respond(room, players[1], "draw_one")
    restored = room_from_snapshot(room_to_snapshot(room))
    assert restored.active_game.effect_queue == game.effect_queue
    shown = restored.active_game.effect_queue[0]["displayed_cards"][players[1].player_id]
    assert {card["card_id"] for card in shown} <= {card.card_id for card in restored.player(players[1].player_id).hand}


def test_repeat_failed_challenge_reuses_source_public_colors():
    room, players, game = setup_flow()
    reveal(room, players[1])
    respond(room, players[1], "challenge")
    reveal(room, players[0])
    effect = game.effect_queue[0]
    source_display = list(effect["displayed_cards"][players[0].player_id])
    reveal(room, players[2])
    before = len(players[2].hand)
    respond(room, players[2], "challenge")
    assert game.current_prompt is None
    assert len(players[2].hand) == before + 4
    result = game.special_state["chongyue_result"]
    assert result["displayed_cards"][players[0].player_id] == source_display
    assert "source_qualified_at_challenge" not in result


def immune_flow(protected_index):
    room, players, game = make_started_room()
    card = special("chongyue")
    zuole = special("zuole")
    players[0].hand = [card, uno("uno_red_1")]
    players[1].hand = [zuole, *four_colors(2)]
    players[2].hand = four_colors(3)
    process_command(room, Command(action_id="start-chongyue", room_id=room.room_id, player_id=players[0].player_id,
                                  command_type="ACTIVATE_SPECIAL", payload={"card_id": card.card_id}))
    respond(room, players[1], "use_zuole", {"card_id": zuole.card_id, "target_player_id": players[protected_index].player_id})
    respond(room, players[2], "pass")
    respond(room, players[0], "pass")
    return room, players, game


def test_source_immunity_skips_its_fill_but_continues_other_players():
    room, players, game = immune_flow(0)
    reveal(room, players[1])
    respond(room, players[1], "challenge")
    assert game.effect_queue[0]["challenge_result"] == "source_immune"
    assert game.current_prompt.responder_ids == [players[2].player_id]
    assert len(players[0].hand) == 1
    reveal(room, players[2])
    respond(room, players[2], "decline_challenge")
    assert game.current_prompt is None
    assert len(players[0].hand) == 1
    assert game.special_state["chongyue_result"]["displayed_cards"][players[0].player_id] == []


def test_other_immunity_skips_display_and_prevents_challenge_penalty():
    room, players, game = immune_flow(1)
    players[0].hand = four_colors(1)
    effect = game.effect_queue[0]
    assert effect["phase"] == "challenge"
    before = len(players[1].hand)
    respond(room, players[1], "challenge")
    reveal(room, players[0])
    assert len(players[1].hand) == before
    assert effect["displayed_cards"][players[1].player_id] == []
    assert game.current_prompt.responder_ids == [players[2].player_id]


@pytest.mark.parametrize("response", ["decline_challenge", "challenge", "timeout"])
def test_legacy_phase_less_prompt_is_finishable_without_new_display_steps(response):
    room, players, game = make_started_room()
    players[0].hand = four_colors(1)
    players[1].hand = four_colors(2)
    players[2].hand = four_colors(3)
    created_at = time()
    prompt = Prompt(prompt_id="legacy", kind=PromptKind.CHONGYUE_CHALLENGE,
                    source_player_id=players[0].player_id, source_card_id="legacy-card", responder_ids=[players[1].player_id],
                    legal_responses=["challenge", "decline_challenge"], created_at=created_at, deadline_at=created_at + 10,
                    default_action="decline_challenge", state_version=room.state_version)
    game.current_prompt = prompt
    game.effect_queue = [{"type": "chongyue", "source_player_id": players[0].player_id,
                          "prompt_id": "legacy", "responder_ids": [player.player_id for player in players[1:]],
                          "responder_index": 0, "displayed_colors": {}, "drawn_until_four": {}}]
    restored = room_from_snapshot(room_to_snapshot(room))
    before = len(restored.player(players[0].player_id).hand)
    if response == "timeout":
        assert expire_special_prompt(restored, "legacy", now=created_at + 11)
    else:
        respond(restored, restored.player(players[1].player_id), response)
    assert "phase" not in restored.active_game.effect_queue[0]
    respond(restored, restored.player(players[2].player_id), "decline_challenge")
    assert restored.active_game.current_prompt is None
    assert len(restored.player(players[0].player_id).hand) == before


def test_wang_parent_is_resumed_after_nested_chongyue():
    room, players, game = make_started_room()
    wang, card = special("wang"), special("chongyue")
    players[0].hand = [card, uno("uno_blue_1")]
    players[1].hand = four_colors(2)
    players[2].hand = [wang, *four_colors(3)]
    game.deck = [uno("uno_red_9"), uno("uno_yellow_1"), uno("uno_green_1"), uno("uno_red_1")]
    activate(room, players[2], wang, {"target_player_id": players[0].player_id})
    respond(room, players[2], "control_play", {"card_id": card.card_id})
    pass_sui_activation_reactions(room, action_prefix="nested")
    child = next(effect for effect in game.effect_queue if effect["type"] == "chongyue")
    assert child["parent_wang_source_card_id"] == wang.card_id
    while game.current_prompt is not None and "control_play" not in game.current_prompt.legal_responses:
        player = room.player(game.current_prompt.responder_ids[0])
        if "submit_cards" in game.current_prompt.legal_responses:
            shown = set(child["displayed_colors"][player.player_id])
            options = {card.color: card.card_id for card in player.hand if card.color is not None and card.color.value not in shown}
            respond(room, player, "submit_cards", {"card_ids": list(options.values())}, action_id=game.current_prompt.prompt_id)
        elif "draw_one" in game.current_prompt.legal_responses:
            respond(room, player, "draw_one", action_id=game.current_prompt.prompt_id)
        else:
            respond(room, player, "decline_challenge", action_id=game.current_prompt.prompt_id)
    assert "control_play" in game.current_prompt.legal_responses
    assert game.current_prompt.responder_ids == [players[2].player_id]
    assert game.current_player_id == players[1].player_id
    assert len([effect for effect in game.effect_queue if effect["type"] == "wang"]) == 1


@pytest.mark.parametrize("phase", ["reveal", "draw", "source_draw"])
def test_required_chongyue_step_pauses_and_resumes_without_any_automatic_action(phase):
    room, players, game = setup_flow()
    if phase in {"draw", "source_draw"}:
        players[1].hand = [uno("uno_red_2")]
        reveal(room, players[1])
    if phase == "source_draw":
        players[0].hand = []
        while game.effect_queue[0]["phase"] != "challenge":
            respond(room, players[1], "draw_one", action_id=game.current_prompt.prompt_id)
        respond(room, players[1], "challenge")
    effect_before = dict(game.effect_queue[0])
    prompt = game.current_prompt
    hands_before = [list(player.hand) for player in players]
    assert pause_expired_step(room, prompt_id=prompt.prompt_id, now=prompt.deadline_at + 1)
    assert [player.hand for player in players] == hands_before
    assert game.effect_queue[0] == effect_before
    restored = room_from_snapshot(room_to_snapshot(room))
    old_prompt_id = restored.active_game.current_prompt.prompt_id
    process_command(restored, Command(action_id="continue", room_id=room.room_id, player_id=players[0].player_id,
                                      command_type="CONTINUE_WAITING"))
    new_prompt = restored.active_game.current_prompt
    assert new_prompt.prompt_id != old_prompt_id
    assert new_prompt.deadline_at - new_prompt.created_at == 180
    assert restored.active_game.effect_queue[0]["phase"] == phase
    assert restored.active_game.pause_state is None


@pytest.mark.parametrize("protect_source", [False, True])
def test_zuole_activated_during_required_chongyue_phase_skips_the_protected_step(protect_source):
    room, players, game = setup_flow()
    zuole = special("zuole")
    players[2].hand.append(zuole)
    target_id = players[1].player_id
    if protect_source:
        players[0].hand = [uno("uno_red_1")]
        reveal(room, players[1])
        respond(room, players[1], "challenge")
        reveal(room, players[0])
        target_id = players[0].player_id
        assert game.effect_queue[0]["phase"] == "source_draw"
    before = len(room.player(target_id).hand)
    process_command(room, Command(action_id="late-zuole", room_id=room.room_id, player_id=players[2].player_id,
                                  command_type="ACTIVATE_SPECIAL", payload={"card_id": zuole.card_id, "target_player_id": target_id}))
    assert len(room.player(target_id).hand) == before
    assert game.effect_queue[0]["phase"] == ("reveal" if protect_source else "challenge")
    assert game.current_prompt.responder_ids == [players[2 if protect_source else 1].player_id]
