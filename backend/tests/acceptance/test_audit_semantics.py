"""Behavioral acceptance for the eight failures captured in the 2026-09-28 audit.

These checks intentionally exercise public command/rule/runtime behavior instead
of preserving the evidence package's former private function layout.
"""

from __future__ import annotations

import asyncio
from time import time

import backend.app.main as main
from backend.app.domain.room import Prompt, PromptKind
from backend.app.engine.command_handler import (
    Command,
    expire_wild_draw_four_challenge,
    pause_expired_step,
    process_command,
)
from backend.app.engine.special_effects import (
    _maybe_open_nian_claim_or_advance,
    activate_special,
    respond_special_prompt,
)
from backend.app.repositories.json_store import JsonSnapshotStore
from backend.tests.test_special_card_resolvers import make_started_room, special, uno


def _answer(room, player, response: str, payload: dict | None = None):
    prompt = room.active_game.current_prompt
    assert prompt is not None
    return respond_special_prompt(room, player.player_id, prompt.prompt_id, response, payload or {})


def _pass_activation_reactions(room) -> None:
    game = room.active_game
    while game.current_prompt is not None:
        effect = next(item for item in game.effect_queue if item.get("prompt_id") == game.current_prompt.prompt_id)
        if effect.get("type") != "sui_activation_reaction":
            return
        _answer(room, room.player(game.current_prompt.responder_ids[0]), "pass")


def _install_expired_plus_four(room, source_id: str, target_id: str) -> Prompt:
    game = room.active_game
    now = time()
    prompt = Prompt(
        prompt_id="acceptance-plus-four",
        kind=PromptKind.WILD_DRAW_FOUR_CHALLENGE,
        source_player_id=source_id,
        source_card_id=None,
        responder_ids=[target_id],
        legal_responses=["challenge", "decline_challenge"],
        created_at=now - 10,
        deadline_at=now - 0.01,
        default_action="decline_challenge",
        state_version=room.state_version,
        game_id=game.game_id,
        game_epoch=game.game_epoch,
    )
    game.current_prompt = prompt
    game.current_player_id = target_id
    game.turn_deadline_at = None
    game.effect_queue.append(
        {
            "type": "wild_draw_four_challenge",
            "prompt_id": prompt.prompt_id,
            "source_player_id": source_id,
            "target_player_id": target_id,
            "challenge_result": "legal",
            "source_would_win": False,
        }
    )
    return prompt


def test_audit_1_completed_turn_with_sui_remaining_opens_challenge():
    room, players, game = make_started_room()
    played = uno("uno_red_7")
    players[0].hand = [played, special("ji"), uno("uno_blue_1")]
    players[1].hand = [uno("uno_green_2")]
    players[2].hand = [uno("uno_yellow_3")]
    game.discard_pile = [uno("uno_red_5")]
    game.current_color = game.discard_pile[-1].color

    process_command(
        room,
        Command(
            action_id="acceptance-has-sui",
            room_id=room.room_id,
            player_id=players[0].player_id,
            command_type="PLAY_CARD",
            payload={"card_id": played.card_id},
        ),
    )

    assert game.current_prompt is not None
    assert game.current_prompt.kind == PromptKind.HAS_SUI_CHALLENGE
    assert game.current_prompt.source_player_id == players[0].player_id


def test_audit_2_required_nian_discard_timeout_pauses_same_step():
    room, players, game = make_started_room()
    now = time()
    prompt = Prompt(
        prompt_id="acceptance-nian-required",
        kind=PromptKind.NIAN_TURN_END_DISCARD,
        source_player_id=players[0].player_id,
        source_card_id=None,
        responder_ids=[players[0].player_id],
        legal_responses=["discard_card"],
        created_at=now,
        deadline_at=now + 30,
        default_action="discard_card",
        state_version=room.state_version,
        required=True,
        game_id=game.game_id,
        game_epoch=game.game_epoch,
    )
    game.current_prompt = prompt
    game.turn_deadline_at = None
    game.effect_queue.append({"type": "nian_turn_end_discard", "prompt_id": prompt.prompt_id})
    current_player_id = game.current_player_id

    assert pause_expired_step(room, prompt_id=prompt.prompt_id, now=prompt.deadline_at)
    assert game.pause_state is not None
    assert game.current_prompt is prompt
    assert game.current_player_id == current_player_id
    assert game.effect_queue[-1]["prompt_id"] == prompt.prompt_id


def test_audit_3_nian_waits_for_gang_before_awarding_claim():
    room, players, game = make_started_room()
    game.special_state["nian"] = {"enabled": True}
    discarded = uno("uno_red_7")
    chi_cards = [uno("uno_blue_5"), uno("uno_green_6")]
    gang_cards = [uno("uno_red_7"), uno("uno_blue_7"), uno("uno_green_7")]
    players[1].hand = chi_cards.copy()
    players[2].hand = gang_cards.copy()

    _maybe_open_nian_claim_or_advance(room, game, players[0].player_id, discarded, 1)
    _answer(room, players[1], "chi", {"card_ids": [card.card_id for card in chi_cards]})

    assert players[1].hand == chi_cards
    assert game.current_prompt is not None
    assert game.current_prompt.responder_ids == [players[2].player_id]
    _answer(room, players[2], "gang", {"card_ids": [card.card_id for card in gang_cards]})
    assert game.current_player_id == players[2].player_id
    assert players[1].hand == chi_cards
    assert players[2].hand == []


def test_audit_4_wang_allows_nested_plus_four_and_restores_chain():
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
    _pass_activation_reactions(room)
    result = _answer(
        room,
        players[2],
        "control_play",
        {"card_id": plus_four.card_id, "chosen_color": "green"},
    )
    assert result["nested_kind"] == "wild_draw_four"
    assert game.current_prompt is not None
    assert set(game.current_prompt.legal_responses) == {"challenge", "decline_challenge"}
    assert game.current_prompt.responder_ids == [players[1].player_id]
    _answer(room, players[1], "decline_challenge")
    assert not any(effect.get("type") == "wang" for effect in game.effect_queue)
    assert game.current_player_id == players[2].player_id


def test_audit_5_immediate_ling_opens_reaction_before_mutating_target():
    room, players, game = make_started_room()
    ling = special("ling")
    players[0].hand = [ling, uno("uno_red_1"), uno("uno_blue_2"), uno("uno_green_3")]
    players[1].hand = [special("zuole")]
    players[2].hand = [uno("uno_yellow_4")]
    before = [card.card_id for card in players[1].hand]

    activate_special(room, players[0].player_id, {"card_id": ling.card_id})

    assert game.current_prompt is not None
    assert game.current_prompt.kind == PromptKind.SUI_REACTION
    assert [card.card_id for card in players[1].hand] == before


def test_audit_6_plus_four_expiry_is_consumed_server_side():
    room, players, game = make_started_room(player_count=2)
    prompt = _install_expired_plus_four(room, players[0].player_id, players[1].player_id)
    before = len(players[1].hand)

    assert expire_wild_draw_four_challenge(room, prompt.prompt_id, now=prompt.deadline_at + 1)
    assert len(players[1].hand) == before + 4
    assert game.current_prompt is not None
    assert game.current_prompt.prompt_id != prompt.prompt_id


def test_audit_7_timeout_successor_window_is_scheduled(tmp_path, monkeypatch):
    room, players, game = make_started_room(player_count=2)
    prompt = _install_expired_plus_four(room, players[0].player_id, players[1].player_id)
    monkeypatch.setattr(main, "snapshot_store", JsonSnapshotStore(tmp_path))

    async def exercise() -> None:
        main._schedule_prompt_expiry(room)
        assert (room.room_id, prompt.prompt_id) in main.prompt_expiry_tasks
        await asyncio.sleep(0.05)
        assert game.current_prompt is not None
        assert game.current_prompt.prompt_id != prompt.prompt_id
        assert (room.room_id, game.current_prompt.prompt_id) in main.prompt_expiry_tasks
        for task in list(main.prompt_expiry_tasks.values()):
            task.cancel()
        main.prompt_expiry_tasks.clear()
        main.prompt_expiry_fingerprints.clear()

    asyncio.run(exercise())


def test_audit_8_normal_turn_has_90_second_pause_path():
    room, players, game = make_started_room(player_count=2)
    assert game.turn_deadline_at is not None
    assert 89 <= game.turn_deadline_at - time() <= 90
    before_hands = [len(player.hand) for player in players]
    current_player_id = game.current_player_id

    assert pause_expired_step(room, prompt_id=None, now=game.turn_deadline_at)
    assert game.pause_state is not None
    assert game.pause_state.step_kind == PromptKind.TURN_MAIN.value
    assert game.current_player_id == current_player_id
    assert [len(player.hand) for player in players] == before_hands
