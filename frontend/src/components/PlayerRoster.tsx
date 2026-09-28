import { Crown, UserCheck, UserRoundX } from 'lucide-react';
import type { PlayerState } from '../types';
import { AvatarBadge } from './product/AvatarBadge';

export type PlayerRosterProps = {
  players: PlayerState[];
  activePlayerId?: string | null;
  currentPlayerId?: string | null;
  compact?: boolean;
  maxSeats?: number;
};

export function PlayerRoster({
  players,
  activePlayerId,
  currentPlayerId,
  compact = false,
  maxSeats = 5,
}: PlayerRosterProps) {
  const orderedPlayers = [...players].sort((a, b) => a.seat_index - b.seat_index);
  const occupiedBySeat = new Map(orderedPlayers.map((player) => [player.seat_index, player]));
  const seats = Array.from({ length: maxSeats }, (_, seatIndex) => occupiedBySeat.get(seatIndex) ?? null);

  return (
    <div className={compact ? 'player-roster product-roster is-compact' : 'player-roster product-roster'}>
      {seats.map((player, seatIndex) => {
        if (!player) {
          return (
            <div className="seat player-row product-roster__seat is-empty" data-seat-index={seatIndex} key={`empty-${seatIndex}`}>
              <span className="product-roster__empty-avatar" aria-hidden="true">{seatIndex + 1}</span>
              <span className="player-row__identity"><strong>空座位</strong><span>等待玩家加入</span></span>
              <span className="player-row__state">可加入</span>
            </div>
          );
        }

        const stateClasses = [
          'seat',
          'player-row',
          'product-roster__seat',
          currentPlayerId === player.player_id ? 'is-current' : '',
          activePlayerId === player.player_id ? 'is-you' : '',
          player.online ? '' : 'is-offline',
        ].filter(Boolean).join(' ');

        return (
          <div className={stateClasses} data-seat-index={player.seat_index} key={player.player_id}>
            <AvatarBadge avatarId={player.avatar_id} label={player.nickname} size="small" />
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
              {player.online ? (player.ready ? '已准备' : '未准备') : '离线'}
            </span>
          </div>
        );
      })}
    </div>
  );
}
