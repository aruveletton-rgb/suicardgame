from time import time

import pytest

from backend.app import main
from backend.app.domain.room import Prompt, PromptKind
from backend.app.engine.bot import choose_bot_command
from backend.app.engine.command_handler import Command, process_command
from backend.app.engine.runtime import prompt_timeout_seconds
from backend.tests.test_chongyue_exact_rules import reveal
from backend.tests.test_special_card_resolvers import activate, make_started_room, respond, special, uno


def prompt_room(responses, phase):
    room, players, game = make_started_room()
    bot = players[1]
    bot.is_bot = True
    bot.hand = [uno(f"uno_{color}_{value}") for color, value in (
        ("red", 1), ("red", 2), ("yellow", 3), ("green", 4), ("blue", 5),
    )] + [uno("uno_wild")]
    now = time()
    prompt = Prompt(
        "chongyue-integration", PromptKind.SUI_PLAYER_RESPONSE, players[0].player_id,
        None, [bot.player_id], responses, now, now + 180, "submit_cards", room.state_version,
        required=True, game_id=game.game_id, game_epoch=game.game_epoch,
    )
    effect = {
        "type": "chongyue", "source_card_kind": "chongyue",
        "source_player_id": players[0].player_id, "prompt_id": prompt.prompt_id,
        "phase": phase, "acting_player_id": bot.player_id,
        "missing_colors": ["red", "yellow", "green", "blue"],
        "required_color_count": 4,
        "displayed_colors": {bot.player_id: []},
        "displayed_cards": {bot.player_id: []},
        "drawn_until_four": {bot.player_id: 0},
        "reveal_order": [member.player_id for member in players[1:] + players[:1]],
        "source_qualified": False,
    }
    game.current_prompt = prompt
    game.effect_queue = [effect]
    return room, bot, game, effect


def test_bot_selects_one_owned_card_for_each_missing_color_without_drawing():
    room, bot, _game, _effect = prompt_room(["submit_cards"], "reveal")
    command = choose_bot_command(room)
    assert command is not None
    assert command.payload["response"] == "submit_cards"
    selected = [card for card in bot.hand if card.card_id in command.payload["card_ids"]]
    assert len(selected) == 4
    assert {card.color.value for card in selected} == {"red", "yellow", "green", "blue"}
    assert len(bot.hand) == 6


@pytest.mark.parametrize("phase", ["draw", "source_draw"])
def test_bot_requests_only_one_draw_for_missing_color_steps(phase):
    room, _bot, _game, effect = prompt_room(["draw_one"], phase)
    effect["missing_colors"] = ["blue"]
    command = choose_bot_command(room)
    assert command is not None
    assert command.payload["response"] == "draw_one"
    assert "card_ids" not in command.payload


def test_bot_reveal_excludes_colors_already_displayed():
    room, bot, _game, effect = prompt_room(["submit_cards"], "source_check")
    effect["displayed_colors"][bot.player_id] = ["red"]
    effect["missing_colors"] = ["yellow", "green", "blue"]
    command = choose_bot_command(room)
    assert command is not None
    selected = [card for card in bot.hand if card.card_id in command.payload["card_ids"]]
    assert {card.color.value for card in selected} == {"yellow", "green", "blue"}


def test_required_single_draw_step_grants_180_seconds():
    _room, _bot, game, _effect = prompt_room(["draw_one"], "source_draw")
    assert prompt_timeout_seconds(game.current_prompt) == 180


def test_public_chongyue_payload_exposes_selected_cards_but_not_private_check():
    room, bot, _game, effect = prompt_room(["submit_cards"], "reveal")
    revealed = main._serialize_card(bot.hand[0])
    effect["displayed_cards"][bot.player_id] = [revealed]
    public = main._serialize_pending_action(room)["effect"]
    assert public["displayed_cards"][bot.player_id] == [revealed]
    assert public["acting_player_id"] == bot.player_id
    assert public["missing_colors"] == effect["missing_colors"]
    assert public["reveal_order"] == effect["reveal_order"]
    assert "source_qualified" not in public
    assert bot.hand[1].card_id not in str(public)


def test_catching_uno_refreshes_required_display_after_new_colors_arrive():
    room, players, game = make_started_room()
    source, actor, catcher = players
    card = special("chongyue")
    source.hand = [card, uno("uno_red_1")]
    actor.hand = [uno("uno_red_2")]
    catcher.hand = [uno("uno_red_3")]
    activate(room, source, card)
    reveal(room, actor)
    assert game.current_prompt.legal_responses == ["draw_one"]
    game.uno_pending_player_id = actor.player_id
    game.uno_catchable_by = [catcher.player_id]
    game.deck = [uno("uno_blue_4"), uno("uno_green_4"), uno("uno_yellow_4")]
    process_command(room, Command(
        "catch-during-display", room.room_id, catcher.player_id, "CATCH_UNO",
        {"target_player_id": actor.player_id},
    ))
    assert game.current_prompt.legal_responses == ["submit_cards"]
    selected = game.current_prompt.private_options_by_responder[actor.player_id]
    assert len(selected) == 2
    respond(room, actor, "submit_cards", {"card_ids": selected}, action_id="show-caught-colors")
    assert game.current_prompt.legal_responses == ["draw_one"]
    respond(room, actor, "draw_one")
    assert game.current_prompt.legal_responses == ["challenge", "decline_challenge"]


def test_other_effects_do_not_disclose_internal_challenge_results():
    room, _bot, _game, effect = prompt_room(["submit_cards"], "reveal")
    effect.update(type="wild_draw_four", challenge_result="illegal")
    public = main._serialize_pending_action(room)["effect"]
    assert "challenge_result" not in public
