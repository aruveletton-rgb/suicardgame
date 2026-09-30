import { Home, RotateCcw, Trophy } from 'lucide-react';
import type { PlayerState } from '../../types';
import { AvatarBadge } from './AvatarBadge';

export type GameResultProps = {
  players: PlayerState[];
  winnerPlayerId: string | null;
  outcome?: 'completed' | 'aborted';
  rematchPending?: boolean;
  canManage?: boolean;
  onRematch: () => void;
  onReturnLobby: () => void;
};

export function GameResult({
  players,
  winnerPlayerId,
  outcome = 'completed',
  rematchPending = false,
  canManage = true,
  onRematch,
  onReturnLobby,
}: GameResultProps) {
  const winner = outcome === 'completed' ? players.find((player) => player.player_id === winnerPlayerId) : null;
  return (
    <section className="product-result" aria-label="本局结算" data-testid="game-result">
      <header>
        <span className={outcome === 'aborted' ? 'is-aborted' : ''}><Trophy size={24} /></span>
        <div>
          <p className="product-kicker">本局结算</p>
          <h2>{outcome === 'aborted' ? '本局已中止' : winner ? `${winner.nickname} 获胜` : '本局已结束'}</h2>
          <p>{outcome === 'aborted' ? '中止不按剩余牌数产生胜者。' : '以下为服务端结算时的剩余手牌数。'}</p>
        </div>
      </header>
      <ol className="product-result__players">
        {[...players].sort((a, b) => a.seat_index - b.seat_index).map((player) => (
          <li key={player.player_id} className={player.player_id === winner?.player_id ? 'is-winner' : ''}>
            <AvatarBadge avatarId={player.avatar_id} label={player.nickname} />
            <span><strong>{player.nickname}</strong><small>座位 {player.seat_index + 1}{player.is_host ? ' · 房主' : ''}</small></span>
            <b>{player.hand_count} 张</b>
          </li>
        ))}
      </ol>
      <div className="product-result__actions">
        <button className="product-primary" type="button" disabled={!canManage || rematchPending} onClick={onRematch}><RotateCcw size={17} />{rematchPending ? '等待重新准备…' : '再来一局'}</button>
        <button type="button" disabled={!canManage} onClick={onReturnLobby}><Home size={17} />返回大厅</button>
      </div>
      <p className="product-result__hint">{canManage ? '再来一局会先返回大厅，所有玩家需要重新准备。' : '等待房主选择再来一局或返回大厅。'}</p>
    </section>
  );
}
