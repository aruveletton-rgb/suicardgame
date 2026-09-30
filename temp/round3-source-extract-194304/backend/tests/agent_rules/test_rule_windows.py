import pytest

from backend.app.domain.room import GameStatus, PromptKind, RoomPhase
from backend.app.engine.command_handler import Command, CommandError, process_command
from backend.app.engine.special_effects import (
    activate_special,
    expire_special_prompt,
    open_has_sui_challenge,
    respond_special_prompt,
    trigger_seen_card,
)
from backend.tests.test_special_card_resolvers import make_started_room, special, uno


def _answer(room, player, response, payload=None):
    prompt = room.active_game.current_prompt
    assert prompt is not None
    return respond_special_prompt(room, player.player_id, prompt.prompt_id, response, payload or {})


def _pass_activation_reaction(room):
    game = room.active_game
    while game.current_prompt is not None:
        effect = next(
            item for item in game.effect_queue if item.get("prompt_id") == game.current_prompt.prompt_id
        )
        if effect.get("type") != "sui_activation_reaction":
            return
        _answer(room, room.player(game.current_prompt.responder_ids[0]), "pass")


def test_nian_collects_chi_then_awards_later_gang_without_consuming_loser():
    room, players, game = make_started_room()
    game.special_state["nian"] = {"enabled": True}
    red_seven = uno("uno_red_7")
    chi_cards = [uno("uno_blue_5"), uno("uno_green_6")]
    gang_cards = [uno("uno_red_7"), uno("uno_blue_7"), uno("uno_green_7")]
    players[1].hand = chi_cards.copy()
    players[2].hand = gang_cards.copy()
    from backend.app.engine.special_effects import _maybe_open_nian_claim_or_advance

    _maybe_open_nian_claim_or_advance(room, game, players[0].player_id, red_seven, 1)
    assert game.current_prompt.kind == PromptKind.NIAN_CLAIM_WINDOW
    _answer(room, players[1], "chi", {"card_ids": [card.card_id for card in chi_cards]})
    assert players[1].hand == chi_cards
    assert game.current_prompt.responder_ids == [players[2].player_id]
    _answer(room, players[2], "gang", {"card_ids": [card.card_id for card in gang_cards]})
    assert game.current_prompt is None
    assert game.current_player_id == players[2].player_id
    assert players[1].hand == chi_cards
    assert players[2].hand == []


def test_ling_reaction_allows_self_protecting_zuole_and_higher_rank_evade():
    room, players, game = make_started_room()
    ling = special("ling")
    zuole = special("zuole")
    wang = special("wang")
    players[0].hand = [ling, uno("uno_red_1")]
    players[1].hand = [zuole]
    players[2].hand = [wang]
    result = activate_special(room, players[0].player_id, {"card_id": ling.card_id})
    assert result["pending"] is True
    assert game.current_prompt.kind == PromptKind.SUI_REACTION
    _answer(room, players[1], "use_zuole", {"card_id": zuole.card_id, "target_player_id": players[1].player_id})
    _answer(room, players[2], "evade", {"card_id": wang.card_id})
    _answer(room, players[0], "pass")
    while game.current_prompt is not None:
        prompt = game.current_prompt
        _answer(room, room.player(prompt.responder_ids[0]), "decline_challenge")
    assert game.current_prompt is None
    assert game.current_player_id == players[1].player_id
    assert len(players[1].hand) == 0
    assert len(players[2].hand) == 0
    assert wang in game.discard_pile


def test_yi_waits_for_zuole_then_skips_protected_target():
    room, players, game = make_started_room()
    yi = special("yi")
    two = uno("uno_red_2")
    six = uno("uno_blue_6")
    zuole = special("zuole")
    players[0].hand = [yi, two, six]
    players[1].hand = [zuole]
    players[2].hand = []

    result = activate_special(
        room,
        players[0].player_id,
        {"card_id": yi.card_id, "pair_card_ids": [two.card_id, six.card_id]},
    )
    assert result["reaction_pending"] is True
    assert len(players[2].hand) == 0
    _answer(
        room,
        players[1],
        "use_zuole",
        {"card_id": zuole.card_id, "target_player_id": players[1].player_id},
    )
    _answer(room, players[2], "pass")
    _answer(room, players[0], "pass")

    assert players[1].hand == []
    assert len(players[2].hand) == 1
    assert yi in game.discard_pile
    assert zuole in game.discard_pile


def test_shu_rank_evasion_discards_counter_without_activating_it():
    room, players, game = make_started_room()
    shu = special("shu")
    wang = special("wang")
    red_cards = [uno("uno_red_1"), uno("uno_red_2"), uno("uno_red_3")]
    players[0].hand = [shu, *red_cards]
    players[1].hand = [wang]
    players[2].hand = []

    activate_special(room, players[0].player_id, {"card_id": shu.card_id, "chosen_color": "red"})
    _answer(room, players[1], "evade", {"card_id": wang.card_id})
    _answer(room, players[2], "pass")
    _answer(room, players[0], "pass")

    assert players[1].hand == []
    assert players[2].hand == red_cards
    assert wang in game.discard_pile
    assert not any(effect.get("source_card_id") == wang.card_id for effect in game.effect_queue)


def test_shu_invalid_explicit_remainder_target_is_atomic_and_same_action_id_can_retry():
    room, players, game = make_started_room()
    shu = special("shu")
    red_cards = [uno("uno_red_1"), uno("uno_red_2"), uno("uno_red_3")]
    players[0].hand = [shu, *red_cards, uno("uno_blue_9")]
    players[1].hand = []
    players[2].hand = [uno("uno_green_4")]
    action_id = "shu-invalid-then-retry"
    state_version = room.state_version
    current_player_id = game.current_player_id
    hand_ids = [[card.card_id for card in player.hand] for player in players]

    with pytest.raises(CommandError) as exc_info:
        process_command(
            room,
            Command(
                action_id=action_id,
                room_id=room.room_id,
                player_id=players[0].player_id,
                command_type="ACTIVATE_SPECIAL",
                payload={
                    "card_id": shu.card_id,
                    "chosen_color": "red",
                    "remainder_player_id": players[2].player_id,
                },
            ),
        )
    assert exc_info.value.code == "SPECIAL_TARGET_INVALID"
    assert room.state_version == state_version
    assert game.current_player_id == current_player_id
    assert game.current_prompt is None
    assert game.effect_queue == []
    assert action_id not in room.processed_actions
    assert [[card.card_id for card in player.hand] for player in players] == hand_ids

    result = process_command(
        room,
        Command(
            action_id=action_id,
            room_id=room.room_id,
            player_id=players[0].player_id,
            command_type="ACTIVATE_SPECIAL",
            payload={
                "card_id": shu.card_id,
                "chosen_color": "red",
                "remainder_player_id": players[1].player_id,
            },
        ),
    )
    assert result["special_kind"] == "shu_reaction"
    assert game.current_prompt is not None
    assert game.current_player_id == current_player_id
    assert action_id in room.processed_actions


def test_shu_omitted_unique_remainder_target_leaves_one_card_and_advances_without_has_sui():
    room, players, game = make_started_room()
    shu = special("shu")
    red_cards = [uno("uno_red_1"), uno("uno_red_2"), uno("uno_red_3")]
    remaining = uno("uno_blue_9")
    players[0].hand = [shu, *red_cards, remaining]
    players[1].hand = []
    players[2].hand = [uno("uno_green_4")]

    activate_special(room, players[0].player_id, {"card_id": shu.card_id, "chosen_color": "red"})
    _pass_activation_reaction(room)

    assert players[0].hand == [remaining]
    assert len(players[1].hand) == 2
    assert len(players[2].hand) == 2
    assert game.uno_pending_player_id == players[0].player_id
    while game.current_prompt is not None:
        prompt = game.current_prompt
        _answer(room, room.player(prompt.responder_ids[0]), "decline_challenge")
    assert game.current_player_id == players[1].player_id
    assert game.uno_pending_player_id == players[0].player_id


def test_shu_empty_hand_finishes_after_effect_without_has_sui_card():
    room, players, game = make_started_room()
    shu = special("shu")
    red_cards = [uno("uno_red_1"), uno("uno_red_2"), uno("uno_red_3")]
    players[0].hand = [shu, *red_cards]
    players[1].hand = []
    players[2].hand = [uno("uno_green_4")]

    activate_special(room, players[0].player_id, {"card_id": shu.card_id, "chosen_color": "red"})
    _pass_activation_reaction(room)

    assert players[0].hand == []
    assert game.current_prompt is None
    assert game.status == GameStatus.FINISHED
    assert game.winner_player_id == players[0].player_id
    assert room.phase == RoomPhase.ROUND_RESULT


def test_wang_target_can_evade_before_control_begins():
    room, players, game = make_started_room()
    game.discard_pile = [uno("uno_blue_5")]
    game.current_color = game.discard_pile[-1].color
    wang = special("wang")
    chongyue = special("chongyue")
    players[0].hand = [uno("uno_yellow_1"), chongyue]
    players[1].hand = [wang]
    players[2].hand = []

    activate_special(room, players[1].player_id, {"card_id": wang.card_id, "target_player_id": players[0].player_id})
    _answer(room, players[2], "pass")
    _answer(room, players[0], "evade", {"card_id": chongyue.card_id})
    result = _answer(room, players[1], "pass")

    assert result["evaded"] is True
    assert game.current_prompt is None
    assert game.current_player_id == players[0].player_id
    assert chongyue in game.discard_pile


def test_optional_activation_reaction_expiry_advances_each_responder_and_applies_effect():
    room, players, game = make_started_room()
    yi = special("yi")
    two = uno("uno_red_2")
    six = uno("uno_blue_6")
    players[0].hand = [yi, two, six]
    players[1].hand = []
    players[2].hand = []
    activate_special(
        room,
        players[0].player_id,
        {"card_id": yi.card_id, "pair_card_ids": [two.card_id, six.card_id]},
    )

    for _ in range(3):
        prompt = game.current_prompt
        assert prompt is not None
        assert expire_special_prompt(room, prompt.prompt_id, now=prompt.deadline_at + 1) is True

    assert game.current_prompt is None
    assert len(players[1].hand) == 1
    assert len(players[2].hand) == 1


def test_has_sui_freezes_eligible_card_and_requires_source_to_choose_transfer():
    room, players, game = make_started_room(player_count=2)
    yi = special("yi")
    players[0].hand = [yi]
    players[1].hand = [uno("uno_blue_1")]
    assert open_has_sui_challenge(room, players[0].player_id) is True
    assert game.current_prompt.kind == PromptKind.HAS_SUI_CHALLENGE
    _answer(room, players[1], "challenge")
    assert game.current_prompt.required is True
    assert game.current_prompt.deadline_at - game.current_prompt.created_at == 30
    assert game.current_prompt.private_options_by_responder[players[0].player_id] == [yi.card_id]
    _answer(room, players[0], "give_card", {"card_id": yi.card_id})
    assert yi in players[1].hand
    assert yi not in players[0].hand
    assert len(players[0].hand) == 4
    assert game.current_player_id == players[1].player_id


def test_has_sui_window_does_not_reveal_private_sui_category():
    room, players, game = make_started_room(player_count=2)
    players[0].hand = [uno("uno_red_1")]
    players[1].hand = [uno("uno_blue_2")]

    assert open_has_sui_challenge(room, players[0].player_id) is True
    assert game.current_prompt is not None
    assert game.current_prompt.kind == PromptKind.HAS_SUI_CHALLENGE
    _answer(room, players[1], "challenge")
    assert len(players[1].hand) == 5
    assert game.current_prompt is None
    assert game.current_player_id == players[1].player_id


def test_has_sui_public_window_is_same_before_private_challenge_choice():
    room_a, players_a, game_a = make_started_room(player_count=2)
    players_a[0].hand = [uno("uno_red_1")]
    players_a[1].hand = [uno("uno_blue_2")]
    assert open_has_sui_challenge(room_a, players_a[0].player_id) is True
    prompt_a = game_a.current_prompt

    room_b, players_b, game_b = make_started_room(player_count=2)
    players_b[0].hand = [special("yi")]
    players_b[1].hand = [uno("uno_blue_2")]
    assert open_has_sui_challenge(room_b, players_b[0].player_id) is True
    prompt_b = game_b.current_prompt

    assert prompt_a is not None and prompt_b is not None
    assert prompt_a.kind == prompt_b.kind == PromptKind.HAS_SUI_CHALLENGE
    assert len(prompt_a.responder_ids) == len(prompt_b.responder_ids)
    assert prompt_a.legal_responses == prompt_b.legal_responses
    assert prompt_a.required is False and prompt_b.required is False
    assert prompt_a.private_options_by_responder == {}
    assert prompt_b.private_options_by_responder == {}


def test_has_sui_closest_challenger_wins_and_later_challenger_has_no_cost():
    room, players, game = make_started_room()
    source_card = special("yi")
    players[0].hand = [source_card]
    players[1].hand = [uno("uno_blue_1")]
    players[2].hand = [uno("uno_green_2")]
    game.deck = [uno("uno_red_3"), uno("uno_yellow_4"), uno("uno_blue_5"), uno("uno_green_6")]

    assert open_has_sui_challenge(room, players[0].player_id) is True
    _answer(room, players[1], "challenge")
    _answer(room, players[2], "challenge")
    assert game.current_prompt is not None
    assert game.current_prompt.required is True
    _answer(room, players[0], "give_card", {"card_id": source_card.card_id})

    assert source_card in players[1].hand
    assert source_card not in players[2].hand
    assert len(players[2].hand) == 1
    assert game.status == GameStatus.ACTIVE
    assert game.current_player_id == players[1].player_id


def test_last_card_has_sui_success_does_not_finish_after_source_receives_cards():
    room, players, game = make_started_room(player_count=2)
    source_card = special("yi")
    players[0].hand = [source_card]
    players[1].hand = [uno("uno_blue_1")]
    game.deck = [uno("uno_red_2"), uno("uno_yellow_3"), uno("uno_green_4"), uno("uno_blue_5")]

    assert open_has_sui_challenge(room, players[0].player_id, finish_player_id=players[0].player_id) is True
    _answer(room, players[1], "challenge")
    _answer(room, players[0], "give_card", {"card_id": source_card.card_id})

    assert len(players[0].hand) == 4
    assert game.status == GameStatus.ACTIVE
    assert game.winner_player_id is None
    assert game.current_player_id == players[1].player_id


def test_seen_events_queue_and_resolve_by_direction_distance():
    room, players, game = make_started_room()
    first = special("sui_xiang")
    farther = special("sui_xiang")
    nearer = special("sui_xiang")
    players[0].hand = [first, uno("uno_red_1"), uno("uno_yellow_1"), uno("uno_green_1"), uno("uno_blue_1")]
    players[1].hand = [farther, uno("uno_red_2"), uno("uno_yellow_2"), uno("uno_green_2"), uno("uno_blue_2")]
    players[2].hand = [nearer, uno("uno_red_3"), uno("uno_yellow_3"), uno("uno_green_3"), uno("uno_blue_3")]
    game.deck = [uno("uno_blue_2"), uno("uno_green_3"), uno("uno_yellow_4"), uno("uno_red_5")]

    first_result = trigger_seen_card(
        room,
        observer_player_id=players[0].player_id,
        owner_player_id=players[0].player_id,
        card=first,
        event_id="seen-first",
        source="simultaneous",
    )
    assert first_result is not None
    trigger_seen_card(
        room,
        observer_player_id=players[2].player_id,
        owner_player_id=players[1].player_id,
        card=farther,
        event_id="seen-farther",
        source="simultaneous",
        event_source_player_id=players[0].player_id,
    )
    trigger_seen_card(
        room,
        observer_player_id=players[1].player_id,
        owner_player_id=players[2].player_id,
        card=nearer,
        event_id="seen-nearer",
        source="simultaneous",
        event_source_player_id=players[0].player_id,
    )
    assert [event["event_id"] for event in game.special_state["pending_seen_events"]] == ["seen-nearer", "seen-farther"]

    while game.current_prompt is not None:
        prompt = game.current_prompt
        effect = next(item for item in game.effect_queue if item.get("prompt_id") == prompt.prompt_id)
        if effect.get("seen_event_id") == "seen-nearer":
            break
        assert expire_special_prompt(room, prompt.prompt_id, now=prompt.deadline_at + 1) is True
    assert game.current_prompt is not None
    effect = next(item for item in game.effect_queue if item.get("prompt_id") == game.current_prompt.prompt_id)
    assert effect["seen_event_id"] == "seen-nearer"


def test_wang_nested_wild_draw_four_resolves_and_restores_control_chain():
    room, players, game = make_started_room(player_count=4)
    game.discard_pile = [uno("uno_blue_5")]
    game.current_color = game.discard_pile[-1].color
    wang = special("wang")
    plus_four = uno("uno_wild_draw_four")
    players[0].hand = [uno("uno_yellow_1")]
    players[1].hand = [uno("uno_red_2")]
    players[2].hand = [wang, plus_four]
    players[3].hand = [uno("uno_green_3")]
    activate_special(room, players[2].player_id, {"card_id": wang.card_id, "target_player_id": players[0].player_id})
    _pass_activation_reaction(room)
    result = _answer(room, players[2], "control_play", {"card_id": plus_four.card_id, "chosen_color": "green"})
    assert result["nested_kind"] == "wild_draw_four"
    assert game.current_prompt.responder_ids == [players[1].player_id]
    _answer(room, players[1], "decline_challenge")
    assert game.current_player_id == players[2].player_id
    assert game.current_prompt is None
    assert game.status == GameStatus.FINISHED
    assert game.winner_player_id == players[2].player_id
    assert not any(effect.get("type") == "wang" for effect in game.effect_queue)


def test_wang_can_activate_nested_ling_then_resume_control():
    room, players, game = make_started_room(player_count=4)
    game.discard_pile = [uno("uno_blue_5")]
    game.current_color = game.discard_pile[-1].color
    wang = special("wang")
    ling = special("ling")
    players[0].hand = [uno("uno_yellow_1")]
    players[1].hand = [uno("uno_red_2")]
    players[2].hand = [wang, ling]
    players[3].hand = [uno("uno_green_3")]
    activate_special(room, players[2].player_id, {"card_id": wang.card_id, "target_player_id": players[0].player_id})
    _pass_activation_reaction(room)
    result = _answer(room, players[2], "control_play", {"card_id": ling.card_id})
    assert result["nested_kind"] == "ling"
    for expected in [players[3], players[0], players[1], players[2]]:
        assert game.current_prompt.responder_ids == [expected.player_id]
        _answer(room, expected, "pass")
    assert game.current_player_id == players[1].player_id
    assert game.current_prompt is not None
    assert game.current_prompt.responder_ids == [players[2].player_id]
    assert any(effect.get("type") == "wang" for effect in game.effect_queue)
