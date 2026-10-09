"""Audit-only behavioral probes. No changes to product sources or legacy tests."""
import asyncio
import time
import pytest
import backend.app.main as main
from backend.app.engine.command_handler import Command, process_command
from backend.app.engine.special_effects import expire_special_prompt
from backend.tests.test_special_card_resolvers import make_started_room, uno, special, activate, respond

def play(room, player, card, action='audit-play'):
    return process_command(room, Command(action_id=action, room_id=room.room_id,
        player_id=player.player_id, command_type='PLAY_CARD',
        payload={'card_id': card.card_id, 'chosen_color': 'red'}))

def test_has_sui_window_after_turn_with_sui_remaining():
    room, p, g = make_started_room()
    c = uno('uno_red_7')
    p[0].hand = [c, special('ji'), uno('uno_blue_1')]
    p[1].hand = [uno('uno_green_2')]
    p[2].hand = [uno('uno_yellow_3')]
    play(room, p[0], c)
    assert g.current_prompt is not None, 'No HAS_SUI window after completed turn'
    assert g.current_prompt.kind.value == 'HAS_SUI_CHALLENGE'

def test_required_nian_discard_timeout_does_not_advance():
    room, p, g = make_started_room()
    n = special('nian')
    p[0].hand = [n, uno('uno_blue_1'), uno('uno_green_2')]
    p[1].hand = [uno('uno_yellow_3')]
    p[2].hand = [uno('uno_blue_4')]
    activate(room, p[0], n)
    prompt = g.current_prompt
    before = g.current_player_id
    expire_special_prompt(room, prompt.prompt_id, now=prompt.deadline_at + 1)
    assert g.current_player_id == before, 'Required discard skipped; turn advanced instead of pausing'
    assert g.current_prompt is not None, 'Required action discarded instead of retained'

def test_nian_chi_cannot_finish_before_higher_priority_gang():
    room, p, g = make_started_room()
    g.special_state['nian'] = {'enabled': True, 'seen_claims': []}
    c, end = uno('uno_red_7'), uno('uno_blue_1')
    chi = [uno('uno_yellow_6'), uno('uno_green_8')]
    gang = [uno('uno_blue_7'), uno('uno_yellow_7'), uno('uno_green_7')]
    p[0].hand = [c, end, uno('uno_blue_2')]
    p[1].hand = chi + [uno('uno_red_9')]
    p[2].hand = gang + [uno('uno_blue_3')]
    play(room, p[0], c)
    respond(room, p[0], 'discard_card', {'card_id': end.card_id})
    respond(room, p[1], 'chi', {'card_ids': [x.card_id for x in chi]})
    assert g.current_prompt is not None, 'CHI immediately closes window; GANG holder never gets opportunity'

def test_wang_can_control_sui_card():
    room, p, g = make_started_room()
    g.discard_pile = [uno('uno_blue_5')]
    g.current_color = g.discard_pile[-1].color
    w, ling = special('wang'), special('ling')
    p[0].hand = [uno('uno_yellow_1')]
    p[1].hand = [w, ling, uno('uno_red_9')]
    p[2].hand = [uno('uno_red_2'), uno('uno_green_3')]
    activate(room, p[1], w, {'target_player_id': p[0].player_id})
    respond(room, p[1], 'control_play', {'card_id': ling.card_id})

def test_ling_offers_reaction_before_mutating_target_hand():
    room, p, g = make_started_room()
    ling = special('ling')
    p[0].hand = [ling, uno('uno_red_1'), uno('uno_blue_2'), uno('uno_green_3')]
    p[1].hand = [special('zuole')]
    p[2].hand = [uno('uno_yellow_4')]
    before = len(p[1].hand)
    activate(room, p[0], ling)
    assert len(p[1].hand) == before, 'Ling draws target cards immediately, before Zuole reaction'
    assert g.current_prompt is not None

def test_wild_draw_four_has_expiry_task():
    async def exercise():
        room, p, g = make_started_room()
        c = uno('uno_wild_draw_four')
        p[0].hand = [c, uno('uno_blue_2')]
        p[1].hand = [uno('uno_green_3')]
        p[2].hand = [uno('uno_blue_4')]
        play(room, p[0], c)
        main._schedule_prompt_expiry(room)
        key = (room.room_id, g.current_prompt.prompt_id)
        assert key in main.prompt_expiry_tasks, '+4 countdown exists but no expiry task is scheduled'
    asyncio.run(exercise())

def test_successor_prompt_after_timeout_has_expiry_task():
    async def exercise():
        room, p, g = make_started_room()
        y = special('yu')
        payment = [uno(f'uno_{color}_1') for color in ['red','yellow','green','blue']]
        p[0].hand = [y] + payment + [uno('uno_red_9')]
        p[1].hand = [uno('uno_blue_3')]
        p[2].hand = [uno('uno_green_4')]
        activate(room, p[0], y, {'payment_card_ids': [c.card_id for c in payment]})
        g.current_prompt.deadline_at = time.time() - 1
        previous = g.current_prompt.prompt_id
        main._schedule_prompt_expiry(room)
        await asyncio.sleep(0.03)
        assert g.current_prompt is not None and g.current_prompt.prompt_id != previous
        key = (room.room_id, g.current_prompt.prompt_id)
        assert key in main.prompt_expiry_tasks, 'Timeout opened a successor prompt without scheduling its deadline'
    asyncio.run(exercise())

def test_normal_turn_has_90_second_deadline_task():
    async def exercise():
        room, p, g = make_started_room()
        for n, player in enumerate(p):
            player.hand = [uno(f'uno_red_{n+1}')]
        main._schedule_prompt_expiry(room)
        assert any(key[0] == room.room_id for key in main.prompt_expiry_tasks), 'Ordinary turn has no timer task'
    asyncio.run(exercise())
