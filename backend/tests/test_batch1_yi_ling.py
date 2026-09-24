from __future__ import annotations

from fastapi.testclient import TestClient

import backend.app.main as main
from backend.app.domain.cards import Card, SPECIAL_BY_KIND, build_core_uno_deck


def clear_rooms() -> None:
    with main.rooms_lock:
        main.rooms.clear()


def auth_header(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['session_id']}"}


def uno(asset_key: str):
    return next(item for item in build_core_uno_deck() if item.asset_key == asset_key)


def special(kind: str) -> Card:
    return Card.from_spec(SPECIAL_BY_KIND[kind])


def command(client: TestClient, room_code: str, session: dict, player_id: str, command_type: str, payload=None, action_id="cmd", expected_state_version=None):
    body = {
        "action_id": action_id,
        "player_id": player_id,
        "command_type": command_type,
        "payload": payload or {},
    }
    if expected_state_version is not None:
        body["expected_state_version"] = expected_state_version
    return client.post(f"/api/v1/rooms/{room_code}/commands", json=body, headers=auth_header(session))


def make_started_room(client: TestClient, player_count: int = 3):
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    players = [host]
    for index in range(1, player_count):
        players.append(client.post(f"/api/v1/rooms/{host['room_code']}/join", json={"nickname": f"p{index}"}).json())
    start = command(client, host["room_code"], host, host["player_id"], "START_GAME", {"seed": 806}, "start")
    assert start.status_code == 200
    return host["room_code"], host, players


def room_summary(room_code: str):
    room = main.rooms[room_code]
    game = room.active_game
    assert game is not None
    return {
        "state_version": room.state_version,
        "current_player_id": game.current_player_id,
        "deck_count": len(game.deck),
        "discard_ids": [card.card_id for card in game.discard_pile],
        "hands": {player.player_id: [card.card_id for card in player.hand] for player in room.players},
    }


def assert_unchanged(room_code: str, before) -> None:
    with main.rooms_lock:
        assert room_summary(room_code) == before


def configure_yi(room_code: str, players: list[dict], *, support_kind: str = "valid_sum_8"):
    yi = special("yi")
    red_three = uno("uno_red_3")
    blue_five = uno("uno_blue_5")
    red_skip = uno("uno_red_skip")
    blue_six = uno("uno_blue_6")
    extra = uno("uno_yellow_9")
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        host = room.player(players[0]["player_id"])
        first_other = room.player(players[1]["player_id"])
        second_other = room.player(players[2]["player_id"])
        if support_kind == "non_number":
            host.hand = [yi, red_three, red_skip, extra]
            support = [red_three, red_skip]
        elif support_kind == "sum_not_8":
            host.hand = [yi, red_three, blue_six, extra]
            support = [red_three, blue_six]
        elif support_kind == "not_owned":
            host.hand = [yi, red_three, extra]
            first_other.hand = [blue_five]
            support = [red_three, blue_five]
        else:
            host.hand = [yi, red_three, blue_five, extra]
            support = [red_three, blue_five]
        if support_kind != "not_owned":
            first_other.hand = [uno("uno_green_1")]
        second_other.hand = [uno("uno_yellow_2")]
        game.current_player_id = host.player_id
        game.discard_pile = [uno("uno_red_5")]
        game.current_color = game.discard_pile[-1].color
        game.deck = [uno("uno_blue_1"), uno("uno_green_2"), uno("uno_yellow_3"), uno("uno_red_4")]
        game.current_prompt = None
        game.effect_queue = []
        before = room_summary(room_code)
    return yi, support, before


def configure_ling_counts(room_code: str, players: list[dict], host_cards: list, other_hands: list[list], deck_cards: list | None = None, discard_cards: list | None = None):
    ling = special("ling")
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        room.player(players[0]["player_id"]).hand = [ling, *host_cards]
        for index, hand in enumerate(other_hands, start=1):
            room.player(players[index]["player_id"]).hand = list(hand)
        game.current_player_id = players[0]["player_id"]
        game.discard_pile = list(discard_cards or [uno("uno_red_5")])
        game.current_color = game.discard_pile[-1].color
        game.deck = list(deck_cards or [uno("uno_blue_1"), uno("uno_green_2"), uno("uno_yellow_3"), uno("uno_red_4"), uno("uno_blue_5"), uno("uno_green_6"), uno("uno_yellow_7"), uno("uno_red_8")])
        game.current_prompt = None
        game.effect_queue = []
        before = room_summary(room_code)
    return ling, before


def test_yi_valid_activation_sum_8_discards_payment_and_draws_for_others_only():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    yi, support, before = configure_yi(room_code, players)

    response = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {"card_id": yi.card_id, "pair_card_ids": [card.card_id for card in support]},
        "yi-valid",
        expected_state_version=before["state_version"],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["special_kind"] == "yi"
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        hands = {player.player_id: player.hand for player in room.players}
        assert yi not in hands[host["player_id"]]
        assert all(card not in hands[host["player_id"]] for card in support)
        assert yi in game.discard_pile
        assert all(card in game.discard_pile for card in support)
        assert len(hands[host["player_id"]]) == len(before["hands"][host["player_id"]]) - 3
        assert len(hands[players[1]["player_id"]]) == len(before["hands"][players[1]["player_id"]]) + 1
        assert len(hands[players[2]["player_id"]]) == len(before["hands"][players[2]["player_id"]]) + 1
        assert len(game.deck) == before["deck_count"] - 2
        assert len(game.discard_pile) == len(before["discard_ids"]) + 3
        assert game.current_player_id == host["player_id"]
    clear_rooms()


def test_yi_reject_non_number_support_without_side_effects():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    yi, support, before = configure_yi(room_code, players, support_kind="non_number")

    response = command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": yi.card_id, "pair_card_ids": [card.card_id for card in support]}, "yi-non-number")

    assert response.status_code == 400
    assert_unchanged(room_code, before)
    clear_rooms()


def test_yi_reject_sum_not_8_without_side_effects():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    yi, support, before = configure_yi(room_code, players, support_kind="sum_not_8")

    response = command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": yi.card_id, "pair_card_ids": [card.card_id for card in support]}, "yi-bad-sum")

    assert response.status_code == 400
    assert_unchanged(room_code, before)
    clear_rooms()


def test_yi_reject_support_card_not_owned_without_side_effects():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    yi, support, before = configure_yi(room_code, players, support_kind="not_owned")

    response = command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": yi.card_id, "pair_card_ids": [card.card_id for card in support]}, "yi-not-owned")

    assert response.status_code == 400
    assert_unchanged(room_code, before)
    clear_rooms()


def test_ling_valid_activation_equalizes_to_snapshot_max_and_advances_turn():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    ling, before = configure_ling_counts(
        room_code,
        players,
        [uno("uno_red_1"), uno("uno_blue_2")],
        [
            [uno("uno_red_2"), uno("uno_blue_3"), uno("uno_green_4"), uno("uno_yellow_5"), uno("uno_red_6")],
            [uno("uno_green_1")],
        ],
    )

    response = command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": ling.card_id}, "ling-valid", expected_state_version=before["state_version"])

    assert response.status_code == 200
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        assert [len(player.hand) for player in room.seats_in_order()] == [5, 5, 5]
        assert len(game.deck) == before["deck_count"] - 7
        assert ling in game.discard_pile
        assert game.current_player_id == players[1]["player_id"]
    clear_rooms()


def test_ling_all_equal_no_extra_draw_from_snapshot_max():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    ling, before = configure_ling_counts(
        room_code,
        players,
        [uno("uno_red_1"), uno("uno_blue_2")],
        [
            [uno("uno_red_2"), uno("uno_blue_3"), uno("uno_green_4")],
            [uno("uno_yellow_2"), uno("uno_red_6"), uno("uno_blue_6")],
        ],
    )

    response = command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": ling.card_id}, "ling-equal")

    assert response.status_code == 200
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        assert [len(player.hand) for player in room.seats_in_order()] == [2, 3, 3]
        assert len(game.deck) == before["deck_count"]
        assert ling in game.discard_pile
    clear_rooms()


def test_ling_user_below_max_also_draws_to_snapshot_max():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    ling, _before = configure_ling_counts(
        room_code,
        players,
        [uno("uno_red_1")],
        [
            [uno("uno_red_2"), uno("uno_blue_3"), uno("uno_green_4"), uno("uno_yellow_5")],
            [uno("uno_green_1"), uno("uno_blue_1")],
        ],
    )

    response = command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": ling.card_id}, "ling-user-below")

    assert response.status_code == 200
    with main.rooms_lock:
        room = main.rooms[room_code]
        assert [len(player.hand) for player in room.seats_in_order()] == [4, 4, 4]
    clear_rooms()


def test_ling_deck_reshuffle_when_needed_preserves_card_counts():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    deck = [uno("uno_blue_1"), uno("uno_green_2")]
    discard = [uno("uno_red_5"), uno("uno_yellow_3"), uno("uno_blue_4"), uno("uno_green_4"), uno("uno_yellow_4")]
    ling, before = configure_ling_counts(
        room_code,
        players,
        [uno("uno_red_1")],
        [
            [uno("uno_red_2"), uno("uno_blue_3"), uno("uno_green_5"), uno("uno_yellow_5")],
            [uno("uno_green_1")],
        ],
        deck_cards=deck,
        discard_cards=discard,
    )
    before_total = sum(len(hand) for hand in before["hands"].values()) + before["deck_count"] + len(before["discard_ids"])

    response = command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": ling.card_id}, "ling-reshuffle")

    assert response.status_code == 200
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        after_total = sum(len(player.hand) for player in room.players) + len(game.deck) + len(game.discard_pile)
        assert [len(player.hand) for player in room.seats_in_order()] == [4, 4, 4]
        assert after_total == before_total
        assert game.discard_pile[-1] == ling
    clear_rooms()
