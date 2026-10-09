import { useEffect } from 'react';
import { ShieldCheck, Users } from 'lucide-react';
import { avatarOptions } from '../../data/avatars';
import type { AvatarId } from '../../types';
import { CardView } from '../CardView';
import { AvatarBadge } from './AvatarBadge';

const NICKNAME_KEY = 'suicardgame.nickname.v1';

export type EntryPanelProps = {
  nickname: string;
  avatarId: AvatarId;
  roomCode: string;
  busy?: boolean;
  error?: string;
  onNicknameChange: (nickname: string) => void;
  onAvatarChange: (avatarId: AvatarId) => void;
  onRoomCodeChange: (roomCode: string) => void;
  onCreate: () => void;
  onJoin: () => void;
};

export function readRememberedNickname(storage: Pick<Storage, 'getItem'> | null = typeof window === 'undefined' ? null : window.localStorage) {
  return storage?.getItem(NICKNAME_KEY)?.slice(0, 24) ?? '';
}

export function readInviteRoomCode(href = typeof window === 'undefined' ? '' : window.location.href) {
  if (!href) return '';
  try {
    return new URL(href).searchParams.get('room')?.trim().toUpperCase().slice(0, 6) ?? '';
  } catch {
    return '';
  }
}

export function EntryPanel({
  nickname,
  avatarId,
  roomCode,
  busy = false,
  error,
  onNicknameChange,
  onAvatarChange,
  onRoomCodeChange,
  onCreate,
  onJoin,
}: EntryPanelProps) {
  useEffect(() => {
    if (!nickname) {
      const remembered = readRememberedNickname();
      if (remembered) onNicknameChange(remembered);
    }
    if (!roomCode) {
      const invitedRoom = readInviteRoomCode();
      if (invitedRoom) onRoomCodeChange(invitedRoom);
    }
  }, []); // Initial hydration only; the parent remains the source of truth.

  const updateNickname = (value: string) => {
    const next = value.slice(0, 24);
    onNicknameChange(next);
    try {
      window.localStorage.setItem(NICKNAME_KEY, next);
    } catch {
      // Storage may be disabled. Entry still works with parent-owned state.
    }
  };

  return (
    <main className="product-entry" data-testid="entry-panel">
      <div className="product-entry__frame">
        <aside className="product-entry__intro">
          <p className="product-kicker">岁牌 × 经典 UNO</p>
          <h1>战术牌桌，辨色也辨形</h1>
          <p>2–5 人实时联机。普通 UNO 四色保留清晰符号，岁牌响应与结算由服务端统一裁决。</p>
          <div className="product-entry__cards" aria-label="岁牌示例">
            <CardView assetKey="sui_wang" variant="preview" />
            <CardView assetKey="sui_nian" variant="preview" />
            <CardView assetKey="sui_chongyue" variant="preview" />
          </div>
          <div className="product-entry__facts">
            <span><ShieldCheck size={17} />私有手牌只发给授权玩家</span>
            <span><Users size={17} />全部在座者在线且准备后开局</span>
          </div>
        </aside>

        <section className="product-entry__form" aria-labelledby="entry-title">
          <div>
            <p className="product-kicker">进入牌桌</p>
            <h2 id="entry-title">创建房间或加入好友</h2>
            <p>昵称仅保存在本机；头像使用内置角色素材。</p>
          </div>

          <label className="product-field">
            <span>昵称</span>
            <input
              data-testid="nickname"
              value={nickname}
              maxLength={24}
              autoComplete="nickname"
              placeholder="输入 1–24 个字符"
              onChange={(event) => updateNickname(event.target.value)}
            />
          </label>

          <fieldset className="product-avatar-picker">
            <legend>选择头像</legend>
            <div>
              {avatarOptions.map((avatar) => (
                <button
                  key={avatar.id}
                  type="button"
                  className={avatarId === avatar.id ? 'is-selected' : ''}
                  aria-pressed={avatarId === avatar.id}
                  aria-label={`选择${avatar.label}头像`}
                  onClick={() => onAvatarChange(avatar.id)}
                >
                  <AvatarBadge avatarId={avatar.id} size="small" />
                  <span>{avatar.label}</span>
                </button>
              ))}
            </div>
          </fieldset>

          <button data-testid="create-room" className="product-primary" type="button" disabled={busy || !nickname.trim()} onClick={onCreate}>
            {busy ? '正在连接…' : '创建房间'}
          </button>

          <div className="product-entry__divider"><span>或加入邀请房间</span></div>
          <div className="product-entry__join">
            <input
              data-testid="join-code"
              aria-label="房间号"
              inputMode="text"
              maxLength={6}
              placeholder="6 位房间号"
              value={roomCode}
              onChange={(event) => onRoomCodeChange(event.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 6))}
            />
            <button data-testid="join-room" type="button" disabled={busy || !nickname.trim() || roomCode.length !== 6} onClick={onJoin}>加入</button>
          </div>
          {error ? <p className="product-error" role="alert">{error}</p> : null}
        </section>
      </div>
    </main>
  );
}
