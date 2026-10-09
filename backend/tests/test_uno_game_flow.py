from backend.app.domain.cards import build_core_uno_deck
from backend.app.domain.room import Room, new_player
from backend.app.engine.command_handler import Command, process_command
from backend.tests.ready_helpers import decline_has_sui_prompts


def make_room(player_count=3):
    host = new_player("host", 0, is_host=True)
    players = [host]
    for index in range(1, player_count):
        players.append(new_player(f"p{index}", index))
    return Room(room_id="FLOW1", host_player_id=host.player_id, players=players), players


def ready_and_start(room, players):
    for player in players:
        process_command(room, Command(action_id=f"ready-{player.player_id}", room_id=room.room_id, player_id=player.player_id, command_type="READY"))
    process_command(room, Command(action_id="start", room_id=room.room_id, player_id=players[0].player_id, command_type="START_GAME", payload={"seed": 3}))
    return room.active_game


def card(asset_key):
    return next(item for item in build_core_uno_deck() if item.asset_key == asset_key)


def set_simple_state(room, players, *, current_index=0, hand=None, discard=None, deck=None):
    game = room.active_game
    assert game is not None
    for player in players:
        player.hand = []
    players[current_index].hand = hand or []
    game.current_player_id = players[current_index].player_id
    game.discard_pile = discard or [card("uno_red_5")]
    game.current_color = game.discard_pile[-1].color
    game.deck = deck or []
    game.current_prompt = None
    game.direction = 1
    return game


def play(room, player, card_to_play, **payload):
    result = process_command(
        room,
        Command(
            action_id=f"play-{card_to_play.card_id}",
            room_id=room.room_id,
            player_id=player.player_id,
            command_type="PLAY_CARD",
            payload={"card_id": card_to_play.card_id, **payload},
        ),
    )
    decline_has_sui_prompts(room, action_prefix=f"decline-after-{card_to_play.kind}")
    return result


def test_number_play_advances_to_next_player():
    room, players = make_room(3)
    ready_and_start(room, players)
    red_7 = card("uno_red_7")
    game = set_simple_state(room, players, hand=[red_7, card("uno_blue_9")])

    play(room, players[0], red_7)

    assert game.current_player_id == players[1].player_id


def test_draw_card_draws_until_playable_and_keeps_turn():
    room, players = make_room(3)
    ready_and_start(room, players)
    drawn = card("uno_red_1")
    game = set_simple_state(room, players, hand=[], deck=[drawn])

    result = process_command(
        room,
        Command(action_id="draw-1", room_id=room.room_id, player_id=players[0].player_id, command_type="DRAW_CARD"),
    )
    assert result["drawn_count"] == 1
    assert players[0].hand == [drawn]
    assert result["drawn_until_playable"] is True
    assert game.current_player_id == players[0].player_id


def test_skip_reverse_draw_two_and_wild_draw_four_apply_turn_effects():
    room, players = make_room(3)
    ready_and_start(room, players)

    skip = card("uno_red_skip")
    game = set_simple_state(room, players, hand=[skip, card("uno_blue_9")])
    play(room, players[0], skip)
    assert game.current_player_id == players[2].player_id

    reverse = card("uno_red_reverse")
    game = set_simple_state(room, players, hand=[reverse, card("uno_blue_9")])
    play(room, players[0], reverse)
    assert game.direction == -1
    assert game.current_player_id == players[2].player_id

    draw_two = card("uno_red_draw_two")
    game = set_simple_state(room, players, hand=[draw_two, card("uno_blue_9")], deck=[card("uno_blue_1"), card("uno_green_2")])
    play(room, players[0], draw_two)
    assert len(players[1].hand) == 2
    assert game.current_player_id == players[2].player_id

    wild_draw_four = card("uno_wild_draw_four")
    game = set_simple_state(
        room,
        players,
        hand=[wild_draw_four, card("uno_green_9")],
        deck=[card("uno_blue_2"), card("uno_green_3"), card("uno_yellow_4"), card("uno_red_6")],
    )
    result = play(room, players[0], wild_draw_four, chosen_color="blue")
    assert game.current_prompt is not None
    process_command(
        room,
        Command(
            action_id="decline-wild-draw-four",
            room_id=room.room_id,
            player_id=players[1].player_id,
            command_type="RESPOND_TO_PROMPT",
            payload={
                "prompt_id": game.current_prompt.prompt_id,
                "response": "decline_challenge",
            },
        ),
    )
    decline_has_sui_prompts(room, action_prefix="decline-after-wild-four")
    assert len(players[1].hand) == 4
    assert game.current_color == "blue"
    assert game.current_player_id == players[2].player_id


def test_draw_card_reshuffles_discard_but_keeps_top_card():
    room, players = make_room(2)
    ready_and_start(room, players)
    top = card("uno_green_2")
    game = set_simple_state(
        room,
        players,
        hand=[],
        deck=[],
        discard=[card("uno_red_5"), card("uno_blue_1"), top],
    )

    process_command(
        room,
        Command(action_id="draw-reshuffle", room_id=room.room_id, player_id=players[0].player_id, command_type="DRAW_CARD"),
    )

    assert len(players[0].hand) == 2
    assert game.discard_pile == [top]
    assert game.current_color == top.color
