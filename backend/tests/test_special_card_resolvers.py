import pytest

import backend.app.main as main
from backend.app.domain.cards import Card, SPECIAL_BY_KIND, build_core_uno_deck
from backend.app.domain.room import GameStatus, Room, RoomPhase, new_player
from backend.app.engine.command_handler import Command, CommandError, process_command
from backend.app.repositories.json_store import room_from_snapshot, room_to_snapshot
from backend.tests.ready_helpers import decline_has_sui_prompts, pass_sui_activation_reactions


def uno(asset_key):
    return next(item for item in build_core_uno_deck() if item.asset_key == asset_key)


def special(kind):
    return Card.from_spec(SPECIAL_BY_KIND[kind])


def make_started_room(player_count=3):
    host = new_player("host", 0, is_host=True)
    players = [host]
    for index in range(1, player_count):
        players.append(new_player(f"p{index}", index))
    room = Room(room_id="SUI001", host_player_id=host.player_id, players=players)
    for player in players:
        process_command(
            room,
            Command(
                action_id=f"ready-{player.player_id}",
                room_id=room.room_id,
                player_id=player.player_id,
                command_type="READY",
            ),
        )
    process_command(
        room,
        Command(
            action_id="start",
            room_id=room.room_id,
            player_id=host.player_id,
            command_type="START_GAME",
            payload={"seed": 13},
        ),
    )
    game = room.active_game
    assert game is not None
    for player in players:
        player.hand = []
    game.current_player_id = host.player_id
    game.discard_pile = [uno("uno_red_5")]
    game.current_color = game.discard_pile[-1].color
    game.current_prompt = None
    game.effect_queue = []
    game.special_state = {}
    game.direction = 1
    game.deck = [
        uno("uno_red_1"),
        uno("uno_yellow_2"),
        uno("uno_green_3"),
        uno("uno_blue_4"),
        uno("uno_red_6"),
        uno("uno_yellow_7"),
        uno("uno_green_8"),
        uno("uno_blue_9"),
    ]
    return room, players, game


def activate(room, player, special_card, payload=None, action_id=None):
    result = process_command(
        room,
        Command(
            action_id=action_id or f"activate-{special_card.kind}-{special_card.card_id}",
            room_id=room.room_id,
            player_id=player.player_id,
            command_type="ACTIVATE_SPECIAL",
            payload={"card_id": special_card.card_id, **(payload or {})},
        ),
    )
    settled = pass_sui_activation_reactions(room, action_prefix=f"pass-{special_card.kind}")
    decline_has_sui_prompts(room, action_prefix=f"decline-after-{special_card.kind}")
    return settled or result


def respond(room, player, response, payload=None, action_id=None):
    game = room.active_game
    assert game is not None and game.current_prompt is not None
    result = process_command(
        room,
        Command(
            action_id=action_id or f"respond-{response}-{player.player_id}",
            room_id=room.room_id,
            player_id=player.player_id,
            command_type="RESPOND_TO_PROMPT",
            payload={"prompt_id": game.current_prompt.prompt_id, "response": response, **(payload or {})},
        ),
    )
    decline_has_sui_prompts(room, action_prefix=f"decline-after-{response}")
    return result


def test_ling_equalizes_all_hands_to_original_max_and_advances():
    room, players, game = make_started_room()
    ling = special("ling")
    players[0].hand = [ling]
    players[1].hand = [uno("uno_red_1"), uno("uno_blue_2"), uno("uno_green_3")]
    players[2].hand = [uno("uno_yellow_4"), uno("uno_red_6")]

    result = activate(room, players[0], ling)

    assert result["special_kind"] == "ling"
    assert [len(player.hand) for player in players] == [3, 3, 3]
    assert game.current_player_id == players[1].player_id


def test_yi_discards_sum_eight_pair_and_other_players_draw():
    room, players, game = make_started_room()
    yi = special("yi")
    two = uno("uno_red_2")
    six = uno("uno_blue_6")
    players[0].hand = [yi, two, six]

    activate(room, players[0], yi, {"pair_card_ids": [two.card_id, six.card_id]})

    assert players[0].hand == []
    assert len(players[1].hand) == 1
    assert len(players[2].hand) == 1
    assert game.current_player_id == players[0].player_id


def test_shu_distributes_selected_color_and_validates_remainder_target():
    room, players, game = make_started_room()
    shu = special("shu")
    red_cards = [uno("uno_red_1"), uno("uno_red_2"), uno("uno_red_3")]
    players[0].hand = [shu, *red_cards]

    activate(room, players[0], shu, {"chosen_color": "red", "remainder_player_id": players[1].player_id})

    assert players[0].hand == []
    assert len(players[1].hand) == 2
    assert len(players[2].hand) == 1
    assert game.current_player_id == players[0].player_id
    assert game.status == GameStatus.FINISHED
    assert room.phase == RoomPhase.ROUND_RESULT
    assert game.winner_player_id == players[0].player_id


def test_ji_uses_ordered_color_discard_prompt_and_source_cap():
    room, players, game = make_started_room()
    ji = special("ji")
    p1_red = uno("uno_red_1")
    source_red = uno("uno_red_2")
    players[0].hand = [ji, source_red]
    players[1].hand = [p1_red]

    activate(room, players[0], ji, {"chosen_color": "red"})
    assert game.current_prompt is not None
    assert game.current_prompt.responder_ids == [players[1].player_id]
    respond(room, players[1], "submit_cards", {"card_ids": [p1_red.card_id]})
    respond(room, players[2], "pass")
    respond(room, players[0], "submit_cards", {"card_ids": [source_red.card_id]})

    assert players[0].hand == []
    assert players[1].hand == []
    assert game.current_prompt is None
    assert game.current_player_id == players[1].player_id


def test_yu_four_color_payment_opens_ordered_response_and_can_stop():
    room, players, game = make_started_room()
    yu = special("yu")
    payment = [uno("uno_red_1"), uno("uno_yellow_2"), uno("uno_green_3"), uno("uno_blue_4")]
    players[0].hand = [yu, *payment]

    activate(room, players[0], yu, {"payment_card_ids": [item.card_id for item in payment]})
    assert game.current_prompt is not None
    respond(room, players[1], "decline")
    assert game.current_prompt.responder_ids == [players[0].player_id]
    respond(room, players[0], "stop")

    assert game.current_prompt is None
    assert game.current_player_id == players[1].player_id


def test_zuole_marks_one_player_immune_to_current_sui_effect():
    room, players, game = make_started_room()
    ji = special("ji")
    zuole = special("zuole")
    players[0].hand = [ji]
    players[2].hand = [zuole]
    activate(room, players[0], ji, {"chosen_color": "red"})

    result = activate(room, players[2], zuole, {"target_player_id": players[2].player_id})

    assert result["special_kind"] == "zuole"
    assert players[2].player_id in game.effect_queue[0]["immune_player_ids"]


def test_xi_substitutes_for_a_passive_required_card_and_is_discarded():
    room, players, game = make_started_room()
    ji = special("ji")
    xi = special("xi")
    players[0].hand = [ji]
    players[1].hand = [xi]
    activate(room, players[0], ji, {"chosen_color": "red"})

    respond(room, players[1], "use_xi")

    assert xi not in players[1].hand
    assert xi in game.discard_pile
    assert game.effect_queue[0]["total_discarded"] == 1


def test_nian_enables_game_scoped_rule_state_and_persists():
    room, players, game = make_started_room()
    nian = special("nian")
    players[0].hand = [nian]

    activate(room, players[0], nian)
    restored = room_from_snapshot(room_to_snapshot(room))

    assert game.special_state["nian_rules_enabled"] is True
    assert restored.active_game is not None
    assert restored.active_game.special_state["nian_rules_enabled"] is True


def test_sui_xiang_reveals_colored_card_and_resolves_each_player():
    room, players, game = make_started_room()
    sui_xiang = special("sui_xiang")
    matching = uno("uno_blue_1")
    players[0].hand = [sui_xiang, matching]
    game.deck = [
        uno("uno_red_1"),
        uno("uno_yellow_2"),
        uno("uno_green_3"),
        uno("uno_blue_5"),
        uno("uno_red_6"),
        uno("uno_yellow_7"),
        uno("uno_green_8"),
        uno("uno_blue_9"),
        uno("uno_blue_4"),
    ]

    activate(room, players[0], sui_xiang)
    assert game.current_prompt is not None
    respond(room, players[0], "submit_cards", {"card_ids": [matching.card_id]})
    respond(room, players[1], "draw_four")
    respond(room, players[2], "draw_four")

    assert game.current_prompt is None
    assert game.current_player_id == players[1].player_id
    assert matching in game.discard_pile


def test_chongyue_challenge_summary_does_not_publish_private_hands():
    room, players, game = make_started_room()
    chongyue = special("chongyue")
    source_colors = [
        uno("uno_red_1"),
        uno("uno_yellow_2"),
        uno("uno_green_3"),
        uno("uno_blue_4"),
    ]
    players[0].hand = [chongyue, *source_colors]
    players[1].hand = [
        uno("uno_red_1"),
        uno("uno_yellow_2"),
        uno("uno_green_3"),
        uno("uno_blue_4"),
    ]
    players[2].hand = [
        uno("uno_red_1"),
        uno("uno_yellow_2"),
        uno("uno_green_3"),
        uno("uno_blue_4"),
    ]

    activate(room, players[0], chongyue)
    public_state = main._serialize_room_state(room)

    assert game.current_prompt is not None
    assert "hand" not in public_state["players"][0]
    assert "card_ids" not in str(public_state["active_game"].get("pending_action", {}))
    respond(room, players[1], "decline_challenge")
    respond(room, players[2], "decline_challenge")
    assert game.current_prompt is None


def test_wang_rejects_playable_target_and_controls_blocked_target_until_controller_turn():
    room, players, game = make_started_room()
    wang = special("wang")
    players[0].hand = [uno("uno_green_9")]
    players[1].hand = [wang]

    activate(room, players[1], wang, {"target_player_id": players[0].player_id})
    assert game.current_prompt is not None
    assert game.current_prompt.responder_ids == [players[1].player_id]
    respond(room, players[1], "control_pass")

    assert game.current_prompt is None
    assert game.current_player_id == players[1].player_id

    room2, players2, _game2 = make_started_room()
    wang2 = special("wang")
    players2[0].hand = [uno("uno_red_7")]
    players2[1].hand = [wang2]
    with pytest.raises(CommandError) as exc_info:
        activate(room2, players2[1], wang2, {"target_player_id": players2[0].player_id})
    assert exc_info.value.code == "SPECIAL_TIMING_INVALID"


def test_cannot_shop_buy_and_refresh_are_once_per_turn():
    room, players, game = make_started_room()
    payment = uno("uno_red_2")
    good = uno("uno_red_7")
    players[0].hand = [payment]
    game.shop.goods = [good]

    buy = process_command(
        room,
        Command(
            action_id="buy-good",
            room_id=room.room_id,
            player_id=players[0].player_id,
            command_type="BUY_SHOP_GOOD",
            payload={"good_card_id": good.card_id, "payment_card_id": payment.card_id},
        ),
    )
    assert buy["bought_card_id"] == good.card_id
    assert good in players[0].hand

    with pytest.raises(CommandError) as exc_info:
        process_command(
            room,
            Command(
                action_id="buy-again",
                room_id=room.room_id,
                player_id=players[0].player_id,
                command_type="BUY_SHOP_GOOD",
                payload={"good_card_id": good.card_id, "payment_card_id": good.card_id},
            ),
        )
    assert exc_info.value.code == "SHOP_BUY_LIMIT"

    game.shop.refreshed_this_turn_by.clear()
    game.deck.extend([uno("uno_red_1"), uno("uno_blue_2"), uno("uno_green_3"), uno("uno_yellow_4")])
    refresh = process_command(
        room,
        Command(
            action_id="refresh-shop",
            room_id=room.room_id,
            player_id=players[0].player_id,
            command_type="REFRESH_SHOP",
        ),
    )
    assert refresh["shop_count"] > 0
    with pytest.raises(CommandError) as refresh_error:
        process_command(
            room,
            Command(
                action_id="refresh-again",
                room_id=room.room_id,
                player_id=players[0].player_id,
                command_type="REFRESH_SHOP",
            ),
        )
    assert refresh_error.value.code == "SHOP_REFRESH_LIMIT"


def test_fuzhou_gift_window_moves_gift_then_discards_fuzhou():
    room, players, game = make_started_room()
    fuzhou = special("fuzhou")
    gift = uno("uno_green_3")
    players[0].hand = [fuzhou]
    players[1].hand = [gift]

    activate(room, players[0], fuzhou)
    respond(room, players[1], "give_card", {"card_id": gift.card_id})
    respond(room, players[2], "decline")

    assert gift in players[0].hand
    assert fuzhou in game.discard_pile
    assert game.current_prompt is None
    assert game.current_player_id == players[1].player_id


def test_drawing_fuzhou_automatically_opens_gift_window():
    room, players, game = make_started_room()
    fuzhou = special("fuzhou")
    game.deck = [fuzhou]

    result = process_command(
        room,
        Command(
            action_id="draw-fuzhou",
            room_id=room.room_id,
            player_id=players[0].player_id,
            command_type="DRAW_CARD",
        ),
    )

    assert result["triggered_special"] == "fuzhou"
    assert game.current_prompt is not None
    assert game.current_player_id == players[0].player_id
    assert fuzhou in game.reveal_area
    respond(room, players[1], "decline")
    respond(room, players[2], "decline")
    assert fuzhou in game.discard_pile
    assert game.current_player_id == players[1].player_id


def test_drawing_sui_xiang_automatically_opens_color_response_window():
    room, players, game = make_started_room()
    sui_xiang = special("sui_xiang")
    game.deck = [
        uno("uno_red_1"),
        uno("uno_yellow_2"),
        uno("uno_green_3"),
        uno("uno_blue_4"),
        uno("uno_red_6"),
        uno("uno_yellow_7"),
        uno("uno_green_8"),
        uno("uno_blue_9"),
        uno("uno_red_5"),
        sui_xiang,
    ]

    result = process_command(
        room,
        Command(
            action_id="draw-sui-xiang",
            room_id=room.room_id,
            player_id=players[0].player_id,
            command_type="DRAW_CARD",
        ),
    )

    assert result["triggered_special"] == "sui_xiang"
    assert game.current_prompt is not None
    assert game.current_prompt.responder_ids == [players[0].player_id]


def test_special_pending_action_round_trips_and_completed_effect_does_not_stall():
    room, players, game = make_started_room()
    ji = special("ji")
    players[0].hand = [ji]
    activate(room, players[0], ji, {"chosen_color": "red"})

    restored = room_from_snapshot(room_to_snapshot(room))
    assert restored.active_game is not None
    assert restored.active_game.current_prompt is not None
    assert restored.active_game.effect_queue[0]["type"] == "ji"

    respond(room, players[1], "pass")
    respond(room, players[2], "pass")
    respond(room, players[0], "pass")
    assert game.current_prompt is None
    assert game.current_player_id == players[1].player_id
