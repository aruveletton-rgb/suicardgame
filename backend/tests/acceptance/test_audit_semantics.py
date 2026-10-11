from time import time

import backend.app.main as main
from backend.app.domain.room import PromptKind
from backend.app.engine.command_handler import Command, pause_expired_step, process_command
from backend.app.engine.special_effects import activate_special
from backend.tests.test_special_card_resolvers import make_started_room, special, uno


def test_ending_a_turn_with_a_sui_card_does_not_open_a_retired_challenge():
    room, players, game = make_started_room()
    played = uno("uno_red_7")
    players[0].hand = [played, special("yu"), uno("uno_blue_1")]
    players[1].hand = [uno("uno_green_2")]
    players[2].hand = [uno("uno_yellow_3")]
    game.discard_pile = [uno("uno_red_5")]
    game.current_color = game.discard_pile[-1].color

    process_command(
        room,
        Command(
            action_id="play-with-sui-left",
            room_id=room.room_id,
            player_id=players[0].player_id,
            command_type="PLAY_CARD",
            payload={"card_id": played.card_id},
        ),
    )

    assert game.current_prompt is None
    assert game.current_player_id == players[1].player_id


def test_ling_opens_reaction_before_mutating_target():
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


def test_normal_turn_has_180_second_pause_path():
    room, players, game = make_started_room(player_count=2)
    assert game.turn_deadline_at is not None
    assert 179 <= game.turn_deadline_at - time() <= 180
    before_hands = [len(player.hand) for player in players]
    current_player_id = game.current_player_id

    assert pause_expired_step(room, prompt_id=None, now=game.turn_deadline_at)
    assert game.pause_state is not None
    assert game.pause_state.step_kind == PromptKind.TURN_MAIN.value
    assert game.current_player_id == current_player_id
    assert [len(player.hand) for player in players] == before_hands
