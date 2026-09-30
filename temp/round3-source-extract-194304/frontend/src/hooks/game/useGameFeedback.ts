import { useEffect, useRef, useState } from 'react';
import type { ActiveGameState, RoomState } from '../../types';

type FeedbackEvent = {
  id: number;
  message: string;
};

function playerName(room: RoomState | null, playerId: string | null): string {
  return room?.players.find((player) => player.player_id === playerId)?.nickname ?? '玩家';
}

export function useGameFeedback(room: RoomState | null, game: ActiveGameState | null): FeedbackEvent | null {
  const previousRef = useRef<ActiveGameState | null>(null);
  const sequenceRef = useRef(0);
  const [feedback, setFeedback] = useState<FeedbackEvent | null>(null);

  useEffect(() => {
    const previous = previousRef.current;
    previousRef.current = game;
    if (!previous || !game || previous.game_id !== game.game_id) return;

    let message = '';
    if (previous.top_discard?.card_id !== game.top_discard?.card_id && game.top_discard) {
      message = `${playerName(room, previous.current_player_id)}打出一张牌`;
    } else if (game.deck_count < previous.deck_count) {
      message = '牌堆发生摸牌移动';
    } else if (previous.current_player_id !== game.current_player_id) {
      message = `回合转交给 ${playerName(room, game.current_player_id)}`;
    }

    if (!message) return;
    sequenceRef.current += 1;
    const next = { id: sequenceRef.current, message };
    setFeedback(next);
    const timer = window.setTimeout(() => {
      setFeedback((current) => current?.id === next.id ? null : current);
    }, 1800);
    return () => window.clearTimeout(timer);
  }, [game, room]);

  return feedback;
}
