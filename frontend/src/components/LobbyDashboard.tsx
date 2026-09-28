import { ArrowRight, BookOpen, Check, Clipboard, Link, Play, Radio, ShieldCheck, Sparkles, Users } from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';
import { specialRules } from '../data/rules';
import type { PrivatePlayerState, RoomState, SessionState } from '../types';
import { CardView } from './CardView';
import { PlayerRoster } from './PlayerRoster';
import { createPublicInviteUrl } from './product/invite';

type LobbyDashboardProps = {
  room: RoomState;
  session: SessionState;
  you: PrivatePlayerState | null;
  connectionState: 'connecting' | 'online' | 'offline';
  onCopyRoomCode: () => void;
  inviteUrl?: string;
  onCopyInviteLink?: (inviteUrl: string) => void;
  onOpenRules?: () => void;
  onToggleReady: () => void;
  onStartGame: () => void;
};

const connectionLabels = {
  connecting: '正在建立实时连接',
  online: '实时连接正常',
  offline: '实时连接已断开',
};

export function LobbyDashboard({
  room,
  session,
  you,
  connectionState,
  onCopyRoomCode,
  inviteUrl,
  onCopyInviteLink,
  onOpenRules,
  onToggleReady,
  onStartGame,
}: LobbyDashboardProps) {
  const onlineCount = room.players.filter((player) => player.online).length;
  const readyCount = room.players.filter((player) => player.ready).length;
  const allReady = room.players.length >= 2 && room.players.every((player) => player.online && player.ready);
  const canStart = allReady && connectionState === 'online';
  const featuredRules = specialRules.slice(0, 4);
  const publicInviteUrl = inviteUrl ?? createPublicInviteUrl(session.room_code);
  const waitingPlayers = room.players.filter((player) => !player.online || !player.ready);
  const copyInviteLink = () => {
    if (onCopyInviteLink) {
      onCopyInviteLink(publicInviteUrl);
      return;
    }
    void navigator.clipboard?.writeText(publicInviteUrl);
  };

  return (
    <section className="lobby-dashboard" aria-label="等待房间">
      <div className="lobby-dashboard__main">
        <section className="invite-panel">
          <p className="section-kicker"><Radio size={16} />邀请玩家</p>
          <h2>分享房间号，凑齐玩家后开始</h2>
          <button className="room-code-card" type="button" onClick={onCopyRoomCode}>
            <span>房间号</span>
            <strong data-testid="room-code">{session.room_code}</strong>
            <small><Clipboard size={15} />点击复制</small>
          </button>
          <div className="product-invite-link">
            <div className="product-invite-link__qr" aria-label="公开邀请二维码">
              <QRCodeSVG value={publicInviteUrl} size={96} bgColor="#f7f2e5" fgColor="#11191a" level="M" marginSize={1} />
            </div>
            <div>
              <strong>扫码或复制公开邀请链接</strong>
              <p>二维码只包含房间号，不包含 session 或重连令牌。</p>
              <button type="button" onClick={copyInviteLink}><Link size={15} />复制邀请链接</button>
            </div>
          </div>
          <div className="lobby-metrics" aria-label="房间状态">
            <div>
              <Users size={18} />
              <strong>{room.players.length}</strong>
              <span>已加入</span>
            </div>
            <div>
              <ShieldCheck size={18} />
              <strong>{onlineCount}</strong>
              <span>在线</span>
            </div>
            <div>
              <Check size={18} />
              <strong>{readyCount}</strong>
              <span>已准备</span>
            </div>
          </div>
        </section>

        <section className="lobby-progress">
          <div className="section-heading lobby-heading">
            <div>
              <p className="section-kicker">开局进度</p>
              <h2>下一步做什么</h2>
            </div>
            <span className={'connection-pill is-' + connectionState}>
              <span aria-hidden="true" />{connectionLabels[connectionState]}
            </span>
          </div>

          <ol className="progress-list">
            <li className={room.players.length >= 2 ? 'is-complete' : 'is-active'}>
              <span>1</span>
              <div><strong>邀请至少 1 位玩家</strong><small>当前 {room.players.length}/2，最多 5 人</small></div>
              {room.players.length >= 2 ? <Check size={18} /> : <ArrowRight size={18} />}
            </li>
            <li className={you?.ready ? 'is-complete' : room.players.length >= 2 ? 'is-active' : ''}>
              <span>2</span>
              <div><strong>确认自己的准备状态</strong><small>准备状态会同步给房间内所有玩家</small></div>
              {you?.ready ? <Check size={18} /> : <ArrowRight size={18} />}
            </li>
            <li className={canStart && you?.is_host ? 'is-active' : ''}>
              <span>3</span>
              <div><strong>由房主开始牌局</strong><small>{you?.is_host ? (allReady ? '所有在线玩家已准备' : '等待所有在座玩家准备') : '等待房主确认开始'}</small></div>
              <Play size={18} />
            </li>
          </ol>

          <div className="lobby-cta">
            <button data-testid="ready" type="button" onClick={onToggleReady}>
              {you?.ready ? '取消准备' : '我已准备'}
            </button>
            {you?.is_host ? (
              <button data-testid="start-game" className="primary" type="button" disabled={!canStart} onClick={onStartGame}>
                <Play size={18} />开始牌局
              </button>
            ) : (
              <p>你已进入房间，等待房主开始。</p>
            )}
          </div>
          {you?.is_host && !canStart ? <p className="cta-hint">至少 2 名玩家、全部在线并准备后才能开始。</p> : null}
          {waitingPlayers.length ? (
            <p className="product-waiting" data-testid="waiting-players">
              等待：{waitingPlayers.map((player) => `${player.nickname}${!player.online ? '（离线）' : '（未准备）'}`).join('、')}
            </p>
          ) : null}
        </section>
      </div>

      <div className="lobby-dashboard__secondary">
        <section className="roster-panel">
          <div className="section-heading lobby-heading">
            <div>
              <p className="section-kicker">房间成员</p>
              <h2>玩家状态</h2>
            </div>
            <span>{room.players.length}/5</span>
          </div>
          <PlayerRoster players={room.players} activePlayerId={you?.player_id} compact maxSeats={5} />
        </section>

        <section className="rules-preview">
          <div className="section-heading lobby-heading">
            <div>
              <p className="section-kicker"><Sparkles size={15} />岁牌机制</p>
              <h2>本局不只是 UNO</h2>
            </div>
            {onOpenRules ? <button type="button" onClick={onOpenRules}><BookOpen size={15} />完整图鉴</button> : <span>13 种特殊规则</span>}
          </div>
          <div className="rule-grid">
            {featuredRules.map((rule) => (
              <article className="rule-item" key={rule.assetKey}>
                <CardView assetKey={rule.assetKey} variant="rule" />
                <div>
                  <strong>{rule.name}</strong>
                  <small>{rule.timing}</small>
                  <p>{rule.summary}</p>
                </div>
              </article>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}
