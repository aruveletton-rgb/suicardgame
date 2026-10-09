from backend.app.domain.cards import Card, CardColor, CardCategory, SPECIAL_BY_KIND, iter_uno_specs, build_game_deck
from backend.app.domain.room import Room, RoomPhase, new_player
from backend.app.engine.command_handler import Command, CommandError, process_command


def _uno(asset_key: str) -> Card:
    spec = next(spec for spec in iter_uno_specs() if spec.asset_key == asset_key)
    return Card.from_spec(spec)


def _started_room() -> tuple[Room, list]:
    players = [new_player("host", 0, is_host=True), new_player("guest", 1)]
    room = Room("RULES01", players[0].player_id, players, phase=RoomPhase.LOBBY)
    for player in players:
        process_command(room, Command(f"ready-{player.player_id}", room.room_id, player.player_id, "READY", {"ready": True}))
    process_command(room, Command("start", room.room_id, players[0].player_id, "START_GAME", {"seed": 7}))
    return room, players


def test_removed_cards_are_not_dealt_but_cannot_field_remains():
    deck, field = build_game_deck(3)
    kinds = {card.kind for card in deck}
    assert not kinds.intersection({"ji", "nian", "sui_xiang", "fuzhou"})
    assert [card.kind for card in field] == ["cannot"]


def test_wild_draw_four_draws_without_challenge_prompt():
    room, players = _started_room()
    game = room.active_game
    assert game is not None
    source, target = players
    plus_four = _uno("uno_wild_draw_four")
    source.hand = [plus_four, _uno("uno_red_1")]
    target.hand = []
    game.discard_pile = [_uno("uno_blue_2")]
    game.current_color = CardColor.BLUE
    game.deck = [_uno("uno_red_3"), _uno("uno_green_4"), _uno("uno_yellow_5"), _uno("uno_blue_6")]
    game.current_player_id = source.player_id

    result = process_command(room, Command("play-plus-four", room.room_id, source.player_id, "PLAY_CARD", {
        "card_id": plus_four.card_id,
        "chosen_color": "red",
    }))

    assert result["drawn_count"] == 4
    assert game.current_prompt is None
    assert game.current_player_id == target.player_id
    assert all(card.category != CardCategory.WILD for card in game.shop.goods)


def test_draw_is_rejected_when_a_legal_card_exists():
    room, players = _started_room()
    game = room.active_game
    assert game is not None
    player = players[0]
    playable = _uno("uno_red_7")
    player.hand = [playable]
    game.discard_pile = [_uno("uno_red_2")]
    game.current_color = CardColor.RED
    game.current_player_id = player.player_id

    try:
        process_command(room, Command("draw-with-playable", room.room_id, player.player_id, "DRAW_CARD"))
    except CommandError as exc:
        assert exc.code == "DRAW_NOT_ALLOWED"
    else:
        raise AssertionError("DRAW_CARD must be rejected when a legal card exists")


def test_draw_continues_until_first_legal_card_and_keeps_turn():
    room, players = _started_room()
    game = room.active_game
    assert game is not None
    player = players[0]
    player.hand = [_uno("uno_yellow_9")]
    game.discard_pile = [_uno("uno_blue_2")]
    game.current_color = CardColor.BLUE
    game.current_player_id = player.player_id
    # DRAW_CARD pops from the end: red 3 is illegal, blue 5 is the first legal draw.
    game.deck = [_uno("uno_blue_5"), _uno("uno_red_3")]

    result = process_command(room, Command("draw-until-playable", room.room_id, player.player_id, "DRAW_CARD"))

    assert result["drawn_count"] == 2
    assert result["drawn_until_playable"] is True
    assert game.current_player_id == player.player_id
    assert any(card.asset_key == "uno_blue_5" for card in player.hand)
