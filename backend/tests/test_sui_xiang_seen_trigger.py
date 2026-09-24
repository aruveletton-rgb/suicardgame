from backend.app.engine.special_effects import trigger_seen_card
from backend.app.repositories.json_store import room_from_snapshot, room_to_snapshot
from backend.tests.test_special_card_resolvers import make_started_room, special, uno


def test_sui_xiang_seen_event_triggers_once_and_persists_pending_action():
    room, players, game = make_started_room()
    sui_xiang = special("sui_xiang")
    players[0].hand = [sui_xiang]
    players[1].hand = [uno("uno_red_1")]
    game.deck = [uno("uno_blue_1"), uno("uno_green_2")]

    result = trigger_seen_card(
        room,
        observer_player_id=players[1].player_id,
        owner_player_id=players[0].player_id,
        card=sui_xiang,
        event_id="seen-sui-xiang-1",
        source="effect_reveal",
    )

    assert result is not None
    assert result["special_kind"] == "sui_xiang"
    assert result["pending"] is True
    assert game.current_prompt is not None
    assert game.effect_queue[0]["seen_event_id"] == "seen-sui-xiang-1"
    assert "seen-sui-xiang-1" in game.special_state["sui_xiang_seen_event_ids"]

    duplicate = trigger_seen_card(
        room,
        observer_player_id=players[1].player_id,
        owner_player_id=players[0].player_id,
        card=sui_xiang,
        event_id="seen-sui-xiang-1",
        source="effect_reveal",
    )
    assert duplicate is None

    restored = room_from_snapshot(room_to_snapshot(room))
    assert restored.active_game is not None
    assert restored.active_game.current_prompt is not None
    assert restored.active_game.effect_queue[0]["seen_event_id"] == "seen-sui-xiang-1"


def test_sui_xiang_public_zone_seen_trigger_has_no_owner_hand_leak():
    room, players, game = make_started_room()
    sui_xiang = special("sui_xiang")
    game.reveal_area.append(sui_xiang)
    players[0].hand = [uno("uno_red_1")]
    players[1].hand = [uno("uno_yellow_1")]
    game.deck = [uno("uno_blue_1"), uno("uno_green_2")]

    result = trigger_seen_card(
        room,
        observer_player_id=players[0].player_id,
        owner_player_id=None,
        card=sui_xiang,
        event_id="public-sui-xiang-1",
        source="public_zone",
    )

    assert result is not None
    assert result["special_kind"] == "sui_xiang"
    assert game.current_prompt is not None
    assert game.effect_queue[0]["source_player_id"] == players[0].player_id
    assert sui_xiang not in game.reveal_area
