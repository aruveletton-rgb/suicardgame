import pytest

from backend.app.engine.command_handler import CommandError
from backend.tests.test_special_card_resolvers import activate, make_started_room, respond, special, uno


def test_wang_reverse_control_continues_until_controller_turn():
    room, players, game = make_started_room(player_count=4)
    game.discard_pile = [uno("uno_blue_5")]
    game.current_color = game.discard_pile[-1].color
    game.current_player_id = players[0].player_id
    wang = special("wang")
    blue_reverse = uno("uno_blue_reverse")
    players[0].hand = [uno("uno_yellow_1")]
    players[1].hand = [wang, blue_reverse]
    players[2].hand = [uno("uno_red_2")]
    players[3].hand = [uno("uno_red_3")]

    activate(room, players[1], wang, {"target_player_id": players[0].player_id})
    respond(room, players[1], "control_play", {"card_id": blue_reverse.card_id}, action_id="wang-reverse")

    assert game.direction == -1
    assert game.current_prompt is not None
    assert game.current_prompt.responder_ids == [players[1].player_id]
    assert game.current_player_id == players[3].player_id

    respond(room, players[1], "control_pass", action_id="wang-pass-p3")
    assert game.current_player_id == players[2].player_id
    respond(room, players[1], "control_pass", action_id="wang-pass-p2")
    assert game.current_prompt is None
    assert game.current_player_id == players[1].player_id


def test_wang_non_controller_cannot_operate_control_prompt():
    room, players, game = make_started_room(player_count=3)
    game.discard_pile = [uno("uno_blue_5")]
    game.current_color = game.discard_pile[-1].color
    game.current_player_id = players[0].player_id
    wang = special("wang")
    players[0].hand = [uno("uno_yellow_1")]
    players[1].hand = [wang]

    activate(room, players[1], wang, {"target_player_id": players[0].player_id})

    with pytest.raises(CommandError) as excinfo:
        respond(room, players[2], "control_pass", action_id="wrong-wang-controller")
    assert excinfo.value.code == "NOT_PROMPT_RESPONDER"
