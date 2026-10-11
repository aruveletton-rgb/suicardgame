from backend.tests.test_special_card_resolvers import activate, make_started_room, respond, special, uno


def reveal(room, player):
    effect = room.active_game.effect_queue[0]
    shown = set(effect["displayed_colors"][player.player_id])
    cards_by_color = {card.color: card for card in player.hand if card.color is not None and card.color.value not in shown}
    return respond(room, player, "submit_cards", {"card_ids": [card.card_id for card in cards_by_color.values()]})


def four_colors(value=1):
    return [uno(f"uno_{color}_{value}") for color in ("red", "yellow", "green", "blue")]


def test_chongyue_does_not_fill_source_or_future_players_before_their_display_step():
    room, players, game = make_started_room()
    chongyue = special("chongyue")
    players[0].hand = [chongyue, uno("uno_red_1")]
    players[1].hand = four_colors(2)
    players[2].hand = [uno("uno_red_3")]
    before_deck = list(game.deck)

    result = activate(room, players[0], chongyue)
    effect = game.effect_queue[0]

    assert result["special_kind"] == "chongyue"
    assert result["pending"] is True
    assert effect["phase"] == "reveal"
    assert effect["acting_player_id"] == players[1].player_id
    assert all(colors == [] for colors in effect["displayed_colors"].values())
    assert all(count == 0 for count in effect["drawn_until_four"].values())
    assert len(players[0].hand) == 1
    assert len(players[2].hand) == 1
    assert game.deck == before_deck
    assert game.current_prompt.responder_ids == [players[1].player_id]


def test_qualified_source_must_display_four_concrete_cards_before_challenger_penalty():
    room, players, game = make_started_room()
    chongyue = special("chongyue")
    players[0].hand = [chongyue, *four_colors(1), uno("uno_red_9")]
    players[1].hand = four_colors(2)
    players[2].hand = four_colors(3)
    game.deck = [
        uno("uno_red_9"),
        uno("uno_yellow_9"),
        uno("uno_green_9"),
        uno("uno_blue_9"),
        uno("uno_red_8"),
    ]

    activate(room, players[0], chongyue)
    reveal(room, players[1])
    before = len(players[1].hand)
    result = respond(room, players[1], "challenge")
    effect = game.effect_queue[0]

    assert result["challenge_result"] == "challenge_failed"
    assert effect["phase"] == "source_check"
    assert effect["acting_player_id"] == players[0].player_id
    assert len(players[1].hand) == before
    reveal(room, players[0])
    assert len(players[1].hand) == before + 4
    assert game.current_prompt.responder_ids == [players[2].player_id]
    assert len(effect["displayed_cards"][players[0].player_id]) == 4
    displayed_ids = {item["card_id"] for item in effect["displayed_cards"][players[0].player_id]}
    assert displayed_ids <= {item.card_id for item in players[0].hand}
    assert len(displayed_ids) == 4
