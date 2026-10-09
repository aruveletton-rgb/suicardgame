from backend.tests.test_special_card_resolvers import activate, make_started_room, respond, special, uno


def test_chongyue_draws_until_each_player_has_four_public_colors_before_challenge():
    room, players, game = make_started_room()
    chongyue = special("chongyue")
    players[0].hand = [chongyue, uno("uno_red_1")]
    players[1].hand = [uno("uno_red_2"), uno("uno_yellow_2"), uno("uno_green_2"), uno("uno_blue_2")]
    players[2].hand = [uno("uno_red_3"), uno("uno_yellow_3"), uno("uno_green_3"), uno("uno_blue_3")]
    game.deck = [uno("uno_red_9"), uno("uno_blue_4"), uno("uno_green_4"), uno("uno_yellow_4")]

    result = activate(room, players[0], chongyue)
    effect = game.effect_queue[0]

    assert result["special_kind"] == "chongyue"
    assert result["pending"] is True
    assert set(effect["displayed_colors"][players[0].player_id]) == {"red", "yellow", "green", "blue"}
    assert effect["drawn_until_four"][players[0].player_id] == 3
    assert len(players[0].hand) == 4
    assert game.current_prompt.responder_ids == [players[1].player_id]


def test_chongyue_failed_challenge_draws_four_for_challenger_and_keeps_private_hands_hidden():
    room, players, game = make_started_room()
    chongyue = special("chongyue")
    players[0].hand = [chongyue, uno("uno_red_1"), uno("uno_yellow_1"), uno("uno_green_1"), uno("uno_blue_1")]
    players[1].hand = [uno("uno_red_2"), uno("uno_yellow_2"), uno("uno_green_2"), uno("uno_blue_2")]
    players[2].hand = [uno("uno_red_3"), uno("uno_yellow_3"), uno("uno_green_3"), uno("uno_blue_3")]
    game.deck = [
        uno("uno_red_9"),
        uno("uno_yellow_9"),
        uno("uno_green_9"),
        uno("uno_blue_9"),
        uno("uno_red_8"),
    ]

    activate(room, players[0], chongyue)
    before = len(players[1].hand)
    result = respond(room, players[1], "challenge")
    effect = game.effect_queue[0]

    assert result["challenge_result"] == "challenge_failed"
    assert len(players[1].hand) == before + 4
    assert "displayed_cards" not in effect
    assert all(isinstance(color, str) for colors in effect["displayed_colors"].values() for color in colors)
