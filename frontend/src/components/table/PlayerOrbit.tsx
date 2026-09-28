import type { PlayerState } from '../../types';

type PlayerOrbitProps = {
  players: PlayerState[];
  currentPlayerId?: string | null;
  youPlayerId?: string | null;
};

export function PlayerOrbit({ players, currentPlayerId, youPlayerId }: PlayerOrbitProps) {
  const ordered = [...players].sort((left, right) => left.seat_index - right.seat_index);
  const youIndex = Math.max(0, ordered.findIndex((player) => player.player_id === youPlayerId));
  const aroundYou = ordered.length
    ? [...ordered.slice(youIndex), ...ordered.slice(0, youIndex)]
    : ordered;

  return (
    <div className={`player-orbit players-rail player-orbit--${Math.max(2, aroundYou.length)}`} aria-label="围桌座位">
      {aroundYou.map((player, index) => {
        const isYou = player.player_id === youPlayerId;
        return (
          <article
            className={[
              'orbit-seat seat',
              `orbit-seat--${isYou ? 'you' : `opponent-${index}`}`,
              player.player_id === currentPlayerId ? 'is-current' : '',
              player.online ? '' : 'is-offline',
            ].filter(Boolean).join(' ')}
            key={player.player_id}
          >
            <span className="orbit-seat__avatar" aria-hidden="true">{player.nickname.slice(0, 1).toUpperCase()}</span>
            <span className="orbit-seat__identity">
              <strong>{player.nickname}{isYou ? '（你）' : ''}</strong>
              <small>{player.is_host ? '房主 · ' : ''}{player.hand_count} 张 · {player.online ? '在线' : '离线'}</small>
            </span>
          </article>
        );
      })}
    </div>
  );
}
