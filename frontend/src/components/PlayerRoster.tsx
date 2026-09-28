import { Crown, UserCheck, UserRoundX } from 'lucide-react';
import type { PlayerState } from '../types';

type PlayerRosterProps = {
  players: PlayerState[];
  activePlayerId?: string | null;
  currentPlayerId?: string | null;
  compact?: boolean;
};

export function PlayerRoster({ players, activePlayerId, currentPlayerId, compact = false }: PlayerRosterProps) {
  return (
    <div className={compact ? 'player-roster is-compact' : 'player-roster'}>
      {players.map((player) => {
        const stateClasses = [
          'seat',
          'player-row',
          currentPlayerId === player.player_id ? 'is-current' : '',
          activePlayerId === player.player_id ? 'is-you' : '',
          player.online ? '' : 'is-offline',
        ].filter(Boolean).join(' ');

        return (
          <div className={stateClasses} key={player.player_id}>
            <span className="player-row__avatar" aria-hidden="true">
              {player.nickname.slice(0, 1).toUpperCase()}
            </span>
            <span className="player-row__identity">
              <strong>
                {player.nickname}
                {activePlayerId === player.player_id ? <small>你</small> : null}
              </strong>
              <span>
                {player.is_host ? <><Crown size={13} />房主</> : <>座位 {player.seat_index + 1}</>}
                {!compact ? <> · {player.hand_count} 张牌</> : null}
              </span>
            </span>
            <span className={player.ready ? 'player-row__state is-ready' : 'player-row__state'}>
              {player.online ? <UserCheck size={15} /> : <UserRoundX size={15} />}
              {player.online ? (player.ready ? '已准备' : '在线') : '离线'}
            </span>
          </div>
        );
      })}
    </div>
  );
}
