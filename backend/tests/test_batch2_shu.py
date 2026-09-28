from __future__ import annotations

from fastapi.testclient import TestClient
from httpx import Response
import pytest

import backend.app.main as main
from backend.tests.ready_helpers import decline_has_sui_prompts, pass_sui_activation_reactions, ready_all_http
from backend.app.domain.cards import Card, SPECIAL_BY_KIND, build_core_uno_deck
from backend.app.engine.command_handler import CommandError


def clear_rooms() -> None:
    with main.rooms_lock:
        main.rooms.clear()


def auth_header(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['session_id']}"}


def uno(asset_key: str):
    return next(item for item in build_core_uno_deck() if item.asset_key == asset_key)


def special(kind: str) -> Card:
    return Card.from_spec(SPECIAL_BY_KIND[kind])


def command(
    client: TestClient,
    room_code: str,
    session: dict,
    player_id: str,
    command_type: str,
    payload=None,
    action_id="cmd",
    expected_state_version=None,
    settle_activation=True,
):
    body = {
        "action_id": action_id,
        "player_id": player_id,
        "command_type": command_type,
        "payload": payload or {},
    }
    if expected_state_version is not None:
        body["expected_state_version"] = expected_state_version
    response = client.post(f"/api/v1/rooms/{room_code}/commands", json=body, headers=auth_header(session))
    if response.status_code == 200 and command_type == "ACTIVATE_SPECIAL" and settle_activation:
        try:
            settled = settle_special_activation(room_code, action_id)
        except CommandError as exc:
            return Response(status_code=400, json={"detail": {"error": exc.code, "message": str(exc)}})
        if settled is not None:
            return Response(status_code=200, json=settled)
    return response


def settle_special_activation(room_code: str, action_id: str):
    with main.rooms_lock:
        settled = pass_sui_activation_reactions(main.rooms[room_code], action_prefix=f"settle-{action_id}")
        decline_has_sui_prompts(main.rooms[room_code], action_prefix=f"decline-{action_id}")
    return settled


def make_started_room(client: TestClient, player_count: int = 3):
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    players = [host]
    for index in range(1, player_count):
        players.append(client.post(f"/api/v1/rooms/{host['room_code']}/join", json={"nickname": f"p{index}"}).json())
    ready_all_http(client, host["room_code"], players)
    start = command(client, host["room_code"], host, host["player_id"], "START_GAME", {"seed": 907}, "start")
    assert start.status_code == 200
    return host["room_code"], host, players


def state_summary(room_code: str):
    room = main.rooms[room_code]
    game = room.active_game
    assert game is not None
    return {
        "state_version": room.state_version,
        "current_player_id": game.current_player_id,
        "deck_ids": [card.card_id for card in game.deck],
        "discard_ids": [card.card_id for card in game.discard_pile],
        "hands": {player.player_id: [card.card_id for card in player.hand] for player in room.players},
    }


def all_card_ids(room_code: str) -> list[str]:
    room = main.rooms[room_code]
    game = room.active_game
    assert game is not None
    ids: list[str] = []
    ids.extend(card.card_id for card in game.deck)
    ids.extend(card.card_id for card in game.discard_pile)
    for player in room.players:
        ids.extend(card.card_id for card in player.hand)
    return ids


def assert_unchanged(room_code: str, before) -> None:
    with main.rooms_lock:
        assert state_summary(room_code) == before


def configure_shu(
    room_code: str,
    players: list[dict],
    *,
    host_red_count: int,
    other_hands: list[list],
):
    shu = special("shu")
    red_cards = [uno(f"uno_red_{index}") for index in range(1, host_red_count + 1)]
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        room.player(players[0]["player_id"]).hand = [shu, *red_cards, uno("uno_blue_9")]
        for index, hand in enumerate(other_hands, start=1):
            room.player(players[index]["player_id"]).hand = list(hand)
        game.current_player_id = players[0]["player_id"]
        game.discard_pile = [uno("uno_red_5")]
        game.current_color = game.discard_pile[-1].color
        game.deck = [uno("uno_blue_1"), uno("uno_green_2"), uno("uno_yellow_3"), uno("uno_red_4")]
        game.current_prompt = None
        game.effect_queue = []
        before = state_summary(room_code)
        before_all_ids = all_card_ids(room_code)
    return shu, red_cards, before, before_all_ids


def test_shu_valid_even_distribution():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu, red_cards, before, _before_all_ids = configure_shu(
        room_code,
        players,
        host_red_count=4,
        other_hands=[[uno("uno_green_1")], [uno("uno_yellow_2")]],
    )

    response = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {"card_id": shu.card_id, "chosen_color": "red"},
        "shu-even",
        expected_state_version=before["state_version"],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["special_kind"] == "shu"
    assert body["chosen_color"] == "red"
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        host_hand = room.player(host["player_id"]).hand
        first_other = room.player(players[1]["player_id"]).hand
        second_other = room.player(players[2]["player_id"]).hand
        red_ids = {card.card_id for card in red_cards}
        assert shu not in host_hand
        assert shu in game.discard_pile
        assert not red_ids.intersection(card.card_id for card in host_hand)
        assert len([card for card in first_other if card.card_id in red_ids]) == 2
        assert len([card for card in second_other if card.card_id in red_ids]) == 2
        assert len(game.deck) == len(before["deck_ids"])
        assert len(game.discard_pile) == len(before["discard_ids"]) + 1
    clear_rooms()


def test_shu_valid_remainder_to_unique_fewest_player():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu, red_cards, before, _before_all_ids = configure_shu(
        room_code,
        players,
        host_red_count=5,
        other_hands=[[uno("uno_green_1")], [uno("uno_yellow_2"), uno("uno_blue_2"), uno("uno_green_3")]],
    )

    response = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {"card_id": shu.card_id, "chosen_color": "red"},
        "shu-unique-fewest",
    )

    assert response.status_code == 200
    with main.rooms_lock:
        room = main.rooms[room_code]
        red_ids = {card.card_id for card in red_cards}
        first_other_red = [card for card in room.player(players[1]["player_id"]).hand if card.card_id in red_ids]
        second_other_red = [card for card in room.player(players[2]["player_id"]).hand if card.card_id in red_ids]
        assert len(first_other_red) == 3
        assert len(second_other_red) == 2
    clear_rooms()


def test_shu_remainder_requires_choice_when_fewest_tied():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu, _red_cards, before, _before_all_ids = configure_shu(
        room_code,
        players,
        host_red_count=5,
        other_hands=[[uno("uno_green_1")], [uno("uno_yellow_2")]],
    )

    response = command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": shu.card_id, "chosen_color": "red"}, "shu-tied-missing")

    assert response.status_code == 400
    assert_unchanged(room_code, before)
    clear_rooms()


def test_shu_reject_invalid_remainder_recipient():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu, _red_cards, before, _before_all_ids = configure_shu(
        room_code,
        players,
        host_red_count=5,
        other_hands=[[uno("uno_green_1")], [uno("uno_yellow_2"), uno("uno_blue_2")]],
    )

    response = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {"card_id": shu.card_id, "chosen_color": "red", "remainder_recipient_id": players[2]["player_id"]},
        "shu-invalid-remainder",
    )

    assert response.status_code == 400
    assert_unchanged(room_code, before)
    clear_rooms()


def test_shu_reject_current_player_as_remainder_recipient():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu, _red_cards, before, _before_all_ids = configure_shu(
        room_code,
        players,
        host_red_count=5,
        other_hands=[[uno("uno_green_1")], [uno("uno_yellow_2")]],
    )

    response = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {"card_id": shu.card_id, "chosen_color": "red", "remainder_recipient_id": host["player_id"]},
        "shu-current-remainder",
    )

    assert response.status_code == 400
    assert_unchanged(room_code, before)
    clear_rooms()


def test_shu_remainder_recipient_id_selects_tied_fewest_player():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu, red_cards, _before, _before_all_ids = configure_shu(
        room_code,
        players,
        host_red_count=5,
        other_hands=[[uno("uno_green_1")], [uno("uno_yellow_2")]],
    )

    response = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {"card_id": shu.card_id, "chosen_color": "red", "remainder_recipient_id": players[2]["player_id"]},
        "shu-tied-valid",
    )

    assert response.status_code == 200
    with main.rooms_lock:
        room = main.rooms[room_code]
        red_ids = {card.card_id for card in red_cards}
        first_other_red = [card for card in room.player(players[1]["player_id"]).hand if card.card_id in red_ids]
        second_other_red = [card for card in room.player(players[2]["player_id"]).hand if card.card_id in red_ids]
        assert len(first_other_red) == 2
        assert len(second_other_red) == 3
    clear_rooms()


def test_shu_reject_color_count_less_than_other_players():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu, _red_cards, before, _before_all_ids = configure_shu(
        room_code,
        players,
        host_red_count=1,
        other_hands=[[uno("uno_green_1")], [uno("uno_yellow_2")]],
    )

    response = command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": shu.card_id, "chosen_color": "red"}, "shu-too-few")

    assert response.status_code == 400
    assert_unchanged(room_code, before)
    clear_rooms()


def test_shu_reject_invalid_color():
    clear_rooms()
    client = TestClient(main.app)
    for color in ("invalid", "wild", "none", ""):
        room_code, host, players = make_started_room(client)
        shu, _red_cards, before, _before_all_ids = configure_shu(
            room_code,
            players,
            host_red_count=4,
            other_hands=[[uno("uno_green_1")], [uno("uno_yellow_2")]],
        )

        response = command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": shu.card_id, "chosen_color": color}, f"shu-bad-color-{color}")

        assert response.status_code == 400
        assert_unchanged(room_code, before)
    clear_rooms()


def test_shu_only_moves_current_players_cards():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    other_red = uno("uno_red_7")
    shu, red_cards, _before, _before_all_ids = configure_shu(
        room_code,
        players,
        host_red_count=4,
        other_hands=[[other_red], [uno("uno_yellow_2")]],
    )

    response = command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": shu.card_id, "chosen_color": "red"}, "shu-current-only")

    assert response.status_code == 200
    with main.rooms_lock:
        room = main.rooms[room_code]
        red_ids = {card.card_id for card in red_cards}
        assert other_red in room.player(players[1]["player_id"]).hand
        assert not any(card.card_id in red_ids for card in room.player(host["player_id"]).hand)
        assert sum(card.card_id in red_ids for member in room.players[1:] for card in member.hand) == 4
    clear_rooms()


def test_shu_does_not_draw_or_duplicate_cards():
    clear_rooms()


def step7r_sanitized_state_summary(room_code: str) -> dict:
    """State proof without hand contents, snapshots, or session material."""
    room = main.rooms[room_code]
    game = room.active_game
    assert game is not None
    return {
        "state_version": room.state_version,
        "current_player_id": game.current_player_id,
        "direction": game.direction,
        "hand_counts": {player.player_id: len(player.hand) for player in room.players},
        "draw_pile_count": len(game.deck),
        "discard_pile_count": len(game.discard_pile),
        "top_discard_card_id": game.discard_pile[-1].card_id if game.discard_pile else None,
        "game_status": game.status.value,
        "room_phase": room.phase.value,
        "winner_player_id": game.winner_player_id,
        "uno_pending_player_id": game.uno_pending_player_id,
        "uno_catchable_by": sorted(game.uno_catchable_by),
        "last_uno_event": game.last_uno_event,
        "processed_action_ids": sorted(room.processed_actions),
    }


def step7r_configure_shu(
    room_code: str,
    players: list[dict],
    *,
    red_count: int = 5,
    host_remaining: int = 1,
    other_hand_counts: tuple[int, int] = (1, 1),
    direction: int = 1,
):
    shu = special("shu")
    red_cards = [uno(f"uno_red_{index}") for index in range(1, red_count + 1)]
    remaining_assets = ["uno_blue_9", "uno_green_8", "uno_yellow_7"]
    other_assets = (
        ["uno_green_1", "uno_green_2", "uno_green_3"],
        ["uno_yellow_1", "uno_yellow_2", "uno_yellow_3"],
    )
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        room.player(players[0]["player_id"]).hand = [
            shu,
            *red_cards,
            *(uno(asset_key) for asset_key in remaining_assets[:host_remaining]),
        ]
        for player, count, assets in zip(players[1:], other_hand_counts, other_assets):
            room.player(player["player_id"]).hand = [uno(asset_key) for asset_key in assets[:count]]
        game.current_player_id = players[0]["player_id"]
        game.direction = direction
        game.discard_pile = [uno("uno_red_5")]
        game.current_color = game.discard_pile[-1].color
        game.deck = [uno("uno_blue_1"), uno("uno_green_4"), uno("uno_yellow_4"), uno("uno_red_6")]
        game.current_prompt = None
        game.effect_queue = []
        game.uno_pending_player_id = None
        game.uno_catchable_by = []
        game.last_uno_event = None
        game.winner_player_id = None
    return shu


def test_step7r_shu_legacy_remainder_player_id_is_compatible():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu = step7r_configure_shu(room_code, players)

    response = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {
            "card_id": shu.card_id,
            "chosen_color": "red",
            "remainder_player_id": players[1]["player_id"],
        },
        "step7r-shu-legacy-only",
    )

    assert response.status_code == 200
    after = step7r_sanitized_state_summary(room_code)
    assert after["hand_counts"][players[1]["player_id"]] == 4
    assert after["hand_counts"][players[2]["player_id"]] == 3
    clear_rooms()


def test_step7r_shu_both_remainder_fields_same_apply_once():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu = step7r_configure_shu(room_code, players)
    before = step7r_sanitized_state_summary(room_code)
    target_id = players[2]["player_id"]

    response = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {
            "card_id": shu.card_id,
            "chosen_color": "red",
            "remainder_recipient_id": target_id,
            "remainder_player_id": target_id,
        },
        "step7r-shu-both-same",
        settle_activation=False,
    )

    assert response.status_code == 200
    after_activation = step7r_sanitized_state_summary(room_code)
    assert after_activation["state_version"] == before["state_version"] + 1

    settle_special_activation(room_code, "step7r-shu-both-same")
    after_settlement = step7r_sanitized_state_summary(room_code)
    assert after_settlement["discard_pile_count"] == before["discard_pile_count"] + 1
    assert after_settlement["hand_counts"][players[1]["player_id"]] == 3
    assert after_settlement["hand_counts"][target_id] == 4
    clear_rooms()


def test_step7r_shu_conflicting_remainder_fields_are_rejected():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu = step7r_configure_shu(room_code, players)

    response = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {
            "card_id": shu.card_id,
            "chosen_color": "red",
            "remainder_recipient_id": players[1]["player_id"],
            "remainder_player_id": players[2]["player_id"],
        },
        "step7r-shu-conflict-rejected",
    )

    assert response.status_code == 400
    clear_rooms()


def test_step7r_shu_conflicting_remainder_fields_leave_state_unchanged():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu = step7r_configure_shu(room_code, players)
    before = step7r_sanitized_state_summary(room_code)

    command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {
            "card_id": shu.card_id,
            "chosen_color": "red",
            "remainder_recipient_id": players[1]["player_id"],
            "remainder_player_id": players[2]["player_id"],
        },
        "step7r-shu-conflict-unchanged",
    )

    assert step7r_sanitized_state_summary(room_code) == before
    clear_rooms()


@pytest.mark.parametrize("recipient_case", ["missing", "current", "non_minimum", "nonexistent"])
def test_step7r_invalid_remainder_recipient_rejected_without_state_change(recipient_case: str):
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    other_hand_counts = (1, 2) if recipient_case == "non_minimum" else (1, 1)
    shu = step7r_configure_shu(room_code, players, other_hand_counts=other_hand_counts)
    before = step7r_sanitized_state_summary(room_code)
    payload = {"card_id": shu.card_id, "chosen_color": "red"}
    if recipient_case == "current":
        payload["remainder_recipient_id"] = host["player_id"]
    elif recipient_case == "non_minimum":
        payload["remainder_recipient_id"] = players[2]["player_id"]
    elif recipient_case == "nonexistent":
        payload["remainder_recipient_id"] = "missing-player"

    response = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        payload,
        f"step7r-shu-invalid-{recipient_case}",
    )

    assert response.status_code == 400
    assert step7r_sanitized_state_summary(room_code) == before
    clear_rooms()


def test_step7r_shu_duplicate_action_id_preserves_full_sanitized_state():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu = step7r_configure_shu(room_code, players, red_count=4, host_remaining=2)
    before = step7r_sanitized_state_summary(room_code)
    payload = {"card_id": shu.card_id, "chosen_color": "red"}

    first = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        payload,
        "step7r-shu-replay",
        expected_state_version=before["state_version"],
        settle_activation=False,
    )
    after_first = step7r_sanitized_state_summary(room_code)
    replay = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        payload,
        "step7r-shu-replay",
        expected_state_version=before["state_version"],
        settle_activation=False,
    )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert step7r_sanitized_state_summary(room_code) == after_first
    clear_rooms()


def test_step7r_shu_stale_version_preserves_full_sanitized_state():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu = step7r_configure_shu(room_code, players, red_count=4, host_remaining=2)
    before = step7r_sanitized_state_summary(room_code)

    response = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {"card_id": shu.card_id, "chosen_color": "red"},
        "step7r-shu-stale",
        expected_state_version=before["state_version"] - 1,
    )

    assert response.status_code == 400
    assert step7r_sanitized_state_summary(room_code) == before
    clear_rooms()


@pytest.mark.parametrize("direction,expected_index", [(1, 1), (-1, 2)])
def test_step7r_successful_shu_advances_exactly_once(direction: int, expected_index: int):
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu = step7r_configure_shu(
        room_code,
        players,
        red_count=4,
        host_remaining=2,
        direction=direction,
    )

    response = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {"card_id": shu.card_id, "chosen_color": "red"},
        f"step7r-shu-turn-{direction}",
    )

    assert response.status_code == 200
    after = step7r_sanitized_state_summary(room_code)
    assert after["direction"] == direction
    assert after["current_player_id"] == players[expected_index]["player_id"]
    clear_rooms()


def test_step7r_shu_two_cards_remaining_continues_without_uno_or_winner():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu = step7r_configure_shu(room_code, players, red_count=4, host_remaining=2)

    response = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {"card_id": shu.card_id, "chosen_color": "red"},
        "step7r-shu-two-left",
    )

    assert response.status_code == 200
    after = step7r_sanitized_state_summary(room_code)
    assert after["hand_counts"][host["player_id"]] == 2
    assert after["game_status"] == "ACTIVE"
    assert after["room_phase"] == "IN_GAME"
    assert after["winner_player_id"] is None
    assert after["uno_pending_player_id"] is None
    assert after["uno_catchable_by"] == []
    clear_rooms()


def test_step7r_shu_one_card_remaining_opens_uno_window_and_snapshots_match():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu = step7r_configure_shu(room_code, players, red_count=4, host_remaining=1)

    response = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {"card_id": shu.card_id, "chosen_color": "red"},
        "step7r-shu-one-left",
    )

    assert response.status_code == 200
    after = step7r_sanitized_state_summary(room_code)
    assert after["hand_counts"][host["player_id"]] == 1
    assert after["uno_pending_player_id"] == host["player_id"]
    assert after["uno_catchable_by"] == sorted(player["player_id"] for player in players[1:])
    with main.rooms_lock:
        room = main.rooms[room_code]
        public = main._public_snapshot(room)
        host_private = main._private_snapshot(room, host["player_id"])
        guest_private = main._private_snapshot(room, players[1]["player_id"])
    public_uno = public["state"]["active_game"]["uno"]
    assert public_uno["pending_player_id"] == host["player_id"]
    assert host_private["state"]["active_game"]["uno"] == public_uno
    assert guest_private["state"]["active_game"]["uno"] == public_uno
    assert host_private["you"]["uno"]["must_declare"] is True
    assert guest_private["you"]["uno"]["can_catch_player_id"] == host["player_id"]
    assert all("hand" not in player for player in public["state"]["players"])
    assert all("hand" not in player for player in guest_private["state"]["players"])
    clear_rooms()


def test_step7r_shu_empty_hand_finishes_once_and_blocks_old_commands():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu = step7r_configure_shu(room_code, players, red_count=4, host_remaining=0)

    first = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {"card_id": shu.card_id, "chosen_color": "red"},
        "step7r-shu-game-end",
        settle_activation=False,
    )

    assert first.status_code == 200
    settle_special_activation(room_code, "step7r-shu-game-end")
    after_first = step7r_sanitized_state_summary(room_code)
    assert after_first["hand_counts"][host["player_id"]] == 0
    assert after_first["game_status"] == "FINISHED"
    assert after_first["room_phase"] == "ROUND_RESULT"
    assert after_first["winner_player_id"] == host["player_id"]

    replay = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {"card_id": shu.card_id, "chosen_color": "red"},
        "step7r-shu-game-end",
        settle_activation=False,
    )
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert step7r_sanitized_state_summary(room_code) == after_first

    with main.rooms_lock:
        waiting_card_id = main.rooms[room_code].player(players[1]["player_id"]).hand[0].card_id
    old_command = command(
        client,
        room_code,
        players[1],
        players[1]["player_id"],
        "PLAY_CARD",
        {"card_id": waiting_card_id},
        "step7r-command-after-game-end",
    )
    assert old_command.status_code == 400
    assert step7r_sanitized_state_summary(room_code) == after_first
    clear_rooms()


def test_step7r_invalid_shu_preserves_turn_direction_uno_and_game_state():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu = step7r_configure_shu(
        room_code,
        players,
        red_count=1,
        host_remaining=2,
        direction=-1,
    )
    with main.rooms_lock:
        game = main.rooms[room_code].active_game
        assert game is not None
        game.uno_pending_player_id = players[2]["player_id"]
        game.uno_catchable_by = [host["player_id"], players[1]["player_id"]]
        game.last_uno_event = {"type": "pending", "player_id": players[2]["player_id"]}
    before = step7r_sanitized_state_summary(room_code)

    response = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {"card_id": shu.card_id, "chosen_color": "red"},
        "step7r-invalid-lifecycle",
    )

    assert response.status_code == 400
    assert step7r_sanitized_state_summary(room_code) == before
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu, _red_cards, before, before_all_ids = configure_shu(
        room_code,
        players,
        host_red_count=4,
        other_hands=[[uno("uno_green_1")], [uno("uno_yellow_2")]],
    )

    response = command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": shu.card_id, "chosen_color": "red"}, "shu-no-dup")

    assert response.status_code == 200
    with main.rooms_lock:
        after_all_ids = all_card_ids(room_code)
        game = main.rooms[room_code].active_game
        assert game is not None
        assert sorted(after_all_ids) == sorted(before_all_ids)
        assert len(after_all_ids) == len(set(after_all_ids))
        assert [card.card_id for card in game.deck] == before["deck_ids"]
        assert len(game.discard_pile) == len(before["discard_ids"]) + 1
    clear_rooms()
