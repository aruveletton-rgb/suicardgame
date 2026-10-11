import pytest

from backend.app.domain.cards import Card, CardColor, iter_uno_specs
from backend.app.domain.room import GameStatus, Room, RoomPhase, new_player
from backend.app.engine.command_handler import Command, CommandError, process_command
from backend.app.engine.invariants import assert_room_invariants, card_locations
from backend.tests.ready_helpers import ready_all


def card(asset_key):
    return Card.from_spec(next(spec for spec in iter_uno_specs() if spec.asset_key == asset_key))


def started_room(player_count=2, seed=5):
    players = [new_player(f"p{index}", index, is_host=index == 0) for index in range(player_count)]
    room = Room("ACTIONS01", players[0].player_id, players)
    ready_all(room)
    process_command(room, Command("start", room.room_id, players[0].player_id, "START_GAME", {"seed": seed}))
    return room, players, room.active_game


@pytest.mark.parametrize("player_count,seed,discard,color,total", [
    (2, 3, ["uno_wild", "uno_blue_skip"], CardColor.BLUE, 120),
    (2, 7, ["uno_wild_draw_four", "uno_green_reverse"], CardColor.GREEN, 120),
    (2, 256, ["uno_wild_draw_four", "uno_wild", "uno_red_skip"], CardColor.RED, 120),
    (4, 24, ["uno_wild", "uno_yellow_4"], CardColor.YELLOW, 126),
    (4, 45, ["uno_wild_draw_four", "uno_red_reverse"], CardColor.RED, 126),
    (4, 258, ["uno_wild", "uno_wild_draw_four", "uno_blue_6"], CardColor.BLUE, 126),
])
def test_opening_keeps_wilds_and_reveals_first_colored_card(player_count, seed, discard, color, total):
    room, players, game = started_room(player_count, seed)
    assert [item.asset_key for item in game.discard_pile] == discard
    assert game.current_color == color
    assert game.current_player_id == players[0].player_id
    assert game.direction == 1
    assert game.current_prompt is None
    assert [len(player.hand) for player in players] == [7] * player_count
    assert len(game.shop.goods) == 8
    assert len(card_locations(room)) == total
    assert_room_invariants(room)


def test_each_draw_adds_one_card_and_requires_another_action_until_playable():
    room, players, game = started_room()
    player = players[0]
    player.hand = [card("uno_yellow_9")]
    players[1].hand = [card("uno_green_6")]
    game.current_player_id = player.player_id
    game.discard_pile = [card("uno_blue_2")]
    game.current_color = CardColor.BLUE
    game.deck = [card("uno_blue_5"), card("uno_green_7"), card("uno_red_3")]
    deadline = game.turn_deadline_at
    for index, expected in enumerate(["uno_red_3", "uno_green_7", "uno_blue_5"]):
        command = Command(f"draw-{index}", room.room_id, player.player_id, "DRAW_CARD")
        result = process_command(room, command)
        assert result["drawn_count"] == 1
        assert result["drawn_until_playable"] is (index == 2)
        assert len(player.hand) == index + 2
        assert player.hand[-1].asset_key == expected
        assert len(game.deck) == 2 - index
        assert game.current_player_id == player.player_id
        assert game.turn_deadline_at == deadline
        assert room.phase == RoomPhase.IN_GAME
        assert game.status == GameStatus.ACTIVE
        assert process_command(room, command) == result
        assert len(player.hand) == index + 2
    with pytest.raises(CommandError) as rejected:
        process_command(room, Command("draw-when-playable", room.room_id, player.player_id, "DRAW_CARD"))
    assert rejected.value.code == "DRAW_NOT_ALLOWED"
    assert len(player.hand) == 4
    assert_room_invariants(room)


def test_single_illegal_draw_does_not_finish_when_discard_can_be_recycled():
    room, players, game = started_room()
    player = players[0]
    player.hand = [card("uno_yellow_9")]
    game.current_player_id = player.player_id
    game.discard_pile = [card("uno_blue_5"), card("uno_blue_2")]
    game.current_color = CardColor.BLUE
    game.deck = [card("uno_red_3")]
    first = process_command(room, Command("draw-last-deck-card", room.room_id, player.player_id, "DRAW_CARD"))
    assert first["drawn_count"] == 1
    assert first["drawn_until_playable"] is False
    assert game.status == GameStatus.ACTIVE
    assert room.phase == RoomPhase.IN_GAME
    assert game.reshuffle_count == 0
    second = process_command(room, Command("draw-recycled-card", room.room_id, player.player_id, "DRAW_CARD"))
    assert second["drawn_count"] == 1
    assert second["drawn_until_playable"] is True
    assert game.reshuffle_count == 1
    assert player.hand[-1].asset_key == "uno_blue_5"
    assert game.current_player_id == player.player_id
    assert_room_invariants(room)


def test_last_unplayable_draw_finishes_only_when_no_more_cards_are_available():
    room, players, game = started_room()
    player = players[0]
    player.hand = [card("uno_yellow_9")]
    game.current_player_id = player.player_id
    game.discard_pile = [card("uno_blue_2")]
    game.current_color = CardColor.BLUE
    game.deck = [card("uno_red_3")]
    result = process_command(room, Command("draw-exhausted", room.room_id, player.player_id, "DRAW_CARD"))
    assert result["drawn_count"] == 1
    assert result["finished_by_deck_exhausted"] is True
    assert game.status == GameStatus.FINISHED
    assert room.phase == RoomPhase.ROUND_RESULT
    assert game.turn_deadline_at is None


@pytest.mark.parametrize("player_count", [2, 3])
@pytest.mark.parametrize("direction", [1, -1])
@pytest.mark.parametrize("asset_key,draw_count", [("uno_red_draw_two", 2), ("uno_wild_draw_four", 4)])
def test_penalty_draw_gives_affected_player_the_next_turn(player_count, direction, asset_key, draw_count):
    room, players, game = started_room(player_count)
    source = players[0]
    target = players[direction % player_count]
    penalty = card(asset_key)
    source.hand = [penalty, card("uno_green_9")]
    for player in players[1:]:
        player.hand = [card("uno_blue_7"), card("uno_red_4")]
    game.current_player_id = source.player_id
    game.direction = direction
    game.discard_pile = [card("uno_red_5")]
    game.current_color = CardColor.RED
    game.deck = [card("uno_green_1") for _ in range(4)]
    result = process_command(room, Command("play-penalty", room.room_id, source.player_id, "PLAY_CARD", {
        "card_id": penalty.card_id, "chosen_color": "blue",
    }))
    assert result["drawn_count"] == 0
    assert result["next_player_id"] == target.player_id
    assert game.special_state["action_stack"] == {"kind": penalty.kind, "count": draw_count}
    assert len(target.hand) == 2
    accepted = process_command(room, Command("accept-penalty", room.room_id, target.player_id, "ACCEPT_STACK"))
    assert accepted["drawn_count"] == draw_count
    assert len(target.hand) == 2 + draw_count
    assert "action_stack" not in game.special_state
    assert game.current_player_id == target.player_id
    assert game.current_prompt is None
    assert game.status == GameStatus.ACTIVE
    playable = target.hand[0 if asset_key == "uno_wild_draw_four" else 1]
    process_command(room, Command("play-after-penalty", room.room_id, target.player_id, "PLAY_CARD", {
        "card_id": playable.card_id,
    }))
    assert playable not in target.hand
    assert game.discard_pile[-1] == playable
    assert game.current_player_id == players[(2 * direction) % player_count].player_id
    assert_room_invariants(room)


@pytest.mark.parametrize("asset_key,draw_count", [("uno_red_draw_two", 2), ("uno_wild_draw_four", 4)])
def test_final_penalty_card_draws_before_finishing_the_game(asset_key, draw_count):
    room, players, game = started_room()
    penalty = card(asset_key)
    players[0].hand = [penalty]
    players[1].hand = [card("uno_blue_7")]
    game.current_player_id = players[0].player_id
    game.discard_pile = [card("uno_red_5")]
    game.current_color = CardColor.RED
    game.deck = [card("uno_green_1") for _ in range(4)]
    result = process_command(room, Command("final-penalty", room.room_id, players[0].player_id, "PLAY_CARD", {
        "card_id": penalty.card_id, "chosen_color": "blue",
    }))
    assert result["drawn_count"] == draw_count
    assert len(players[1].hand) == 1 + draw_count
    assert game.status == GameStatus.FINISHED
    assert game.winner_player_id == players[0].player_id
