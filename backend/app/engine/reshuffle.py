from __future__ import annotations

import random

from backend.app.domain.cards import Card
from backend.app.domain.room import GameState


def shuffle_recycled_cards(game: GameState, cards: list[Card]) -> None:
    if game.seed is None:
        random.shuffle(cards)
    else:
        random.Random(f"{game.seed}:reshuffle:{game.reshuffle_count}").shuffle(cards)
