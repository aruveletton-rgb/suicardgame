import { Copy, LogOut, RefreshCw, RotateCcw, ShieldCheck, Users } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { createRoom, joinRoom, reconnectRoom, roomWebSocketUrl } from './api';
import { CardView } from './components/CardView';
import { LobbyDashboard } from './components/LobbyDashboard';
import type { CardState, PendingAction, PrivatePlayerState, RoomState, ServerEvent, SessionState } from './types';

const SESSION_KEY = 'suicardgame.session.v1';
const COLORS: CardState['color'][] = ['red', 'yellow', 'green', 'blue'];

// crypto.randomUUID 仅在 HTTPS 或 localhost 可用；非 HTTPS 公网环境（HTTP 直连）需回退。
function genActionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'a-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
}

function responseLabel(response: string): string {
  const labels: Record<string, string> = {
    challenge: '质疑',
    decline_challenge: '不质疑',
    submit_cards: '提交所选牌',
    pass: '跳过',
    decline: '放弃',
    restart: '重新支付',
    stop: '停止效果',
    use_xi: '使用夕牌代替',
    give_card: '赠送主选牌',
    control_play: '代打主选牌',
    control_pass: '不出牌',
    discard_card: '弃掉主选牌',
    chi: '吃',
    peng: '碰',
    gang: '杠',
  };
  return labels[response] ?? response;
}

function playerName(room: RoomState | null, playerId: string | null | undefined): string {
  if (!room || !playerId) return '无';
  return room.players.find((player) => player.player_id === playerId)?.nickname ?? playerId.slice(0, 6);
}

function promptCardKind(pending: PendingAction): string {
  const sourceKind = pending.effect.source_card_kind;
  if (typeof sourceKind === 'string') return sourceKind;
  const effectType = pending.effect.type;
  return typeof effectType === 'string' ? effectType : pending.kind;
}

function promptTitle(kind: string): string {
  const titles: Record<string, string> = {
    nian: 'Nian 年牌：摸/弃与吃碰杠窗口',
    nian_claim: 'Nian 年牌：吃 / 碰 / 杠响应',
    nian_turn_end_discard: 'Nian 年牌：回合结束弃牌',
    chongyue: 'Chongyue 重岳牌：公开四色与质疑',
    wang: 'Wang 望牌：连续控制',
    sui_xiang: 'Sui Xiang 岁相牌：被看到后同色响应',
    cannot: 'Cannot 坎诺特牌：商店购买/刷新',
    fuzhou: 'Fuzhou 符咒牌：赠牌响应',
    wild_draw_four_challenge: 'Wild Draw Four 质疑',
    WILD_DRAW_FOUR_CHALLENGE: 'Wild Draw Four 质疑',
  };
  return titles[kind] ?? `特殊牌：${kind}`;
}

function promptHint(kind: string): string {
  const hints: Record<string, string> = {
    nian: '按当前窗口选择弃牌、吃、碰、杠或跳过；断线重连后会恢复这个窗口。',
    nian_claim: '选择两张成顺子的数字牌可吃；两张同点可碰；三张同点可杠。',
    nian_turn_end_discard: '请选择一张手牌作为年牌规则的回合结束弃牌。',
    chongyue: '系统只公开四色摘要和摸牌数量，不公开完整手牌。可质疑或放弃质疑。',
    wang: '控制者可以代被控制玩家出合法普通牌/动作牌，或选择不出牌。',
    sui_xiang: '按翻出的颜色提交一张同色牌；没有同色牌时摸四张；夕牌可作为替代。',
    cannot: '先选支付手牌，再点击商品购买；刷新按钮每名玩家每回合限一次。',
    fuzhou: '轮到你时可选择一张手牌赠给触发者，也可以放弃。',
    wild_draw_four_challenge: '被影响玩家可以质疑 +4 是否违规，或放弃质疑并摸四张。',
    WILD_DRAW_FOUR_CHALLENGE: '被影响玩家可以质疑 +4 是否违规，或放弃质疑并摸四张。',
  };
  return hints[kind] ?? '请选择合法响应；操作会通过后端 WebSocket 命令结算。';
}

function promptStatusLabel(status: PendingAction['status']): string {
  return {
    open: '开放',
    resolved: '已处理',
    expired: '已过期',
    cancelled: '已取消',
  }[status];
}

function batch1SpecialHint(card: CardState | null): string {
  if (card?.kind === 'yi') {
    return '易牌：弃置两张数字牌，点数之和必须为 8，使所有其他玩家各摸 1 张。请选择两张数字牌作为附加选择。';
  }
  if (card?.kind === 'ling') {
    return '令牌：所有手牌数低于当前最大手牌数的玩家摸牌，直到与最大手牌数相同。不需要目标或附加选择。';
  }
  if (card?.kind === 'shu') {
    return '黍牌：选择一种颜色，将你手中该颜色的所有牌平均分给其他玩家；若有剩余，交给手牌最少的玩家之一。';
  }
  return '';
}

function commandNotice(result: Record<string, unknown>): string {
  if (result.special_kind === 'yi') return '易牌生效：其他玩家各摸 1 张。';
  if (result.special_kind === 'ling') return '令牌生效：所有玩家手牌数补齐至当前最大值。';
  if (result.special_kind === 'shu') return '黍牌生效：已将所选颜色牌分给其他玩家。';
  return '操作已结算';
}

export function App() {
  const [nickname, setNickname] = useState('玩家');
  const [joinCode, setJoinCode] = useState('');
  const [session, setSession] = useState<SessionState | null>(null);
  const [room, setRoom] = useState<RoomState | null>(null);
  const [you, setYou] = useState<PrivatePlayerState | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [connectionState, setConnectionState] = useState<'connecting' | 'online' | 'offline'>('offline');
  const [primaryCardId, setPrimaryCardId] = useState<string | null>(null);
  const [supportCardIds, setSupportCardIds] = useState<string[]>([]);
  const [chosenColor, setChosenColor] = useState<NonNullable<CardState['color']>>('red');
  const [targetPlayerId, setTargetPlayerId] = useState('');
  const [declareUnoWithPlay, setDeclareUnoWithPlay] = useState(false);
  const [respondingPromptId, setRespondingPromptId] = useState<string | null>(null);
  const [promptNow, setPromptNow] = useState(() => Date.now());
  const socketRef = useRef<WebSocket | null>(null);
  const restoredRef = useRef(false);

  const activeGame = room?.active_game ?? null;
  const primaryCard = you?.hand.find((card) => card.card_id === primaryCardId) ?? null;
  const supportCards = useMemo(
    () => supportCardIds.map((cardId) => you?.hand.find((card) => card.card_id === cardId)).filter((card): card is CardState => Boolean(card)),
    [supportCardIds, you],
  );
  const selectedBatch1Hint = batch1SpecialHint(primaryCard);
  const isMyTurn = activeGame?.current_player_id === you?.player_id;
  const pending = activeGame?.pending_action ?? null;
  const hasOpenPrompt = pending?.status === 'open';
  const canRespond = Boolean(you && hasOpenPrompt && pending?.can_respond);
  const promptRemainingSeconds = pending && hasOpenPrompt
    ? Math.max(0, Math.ceil((pending.deadline_at * 1000 - promptNow) / 1000))
    : null;
  const selectableTargets = useMemo(
    () => room?.players.filter((player) => player.player_id !== you?.player_id) ?? [],
    [room, you],
  );
  const selectedShuColorCount = useMemo(
    () => primaryCard?.kind === 'shu' ? you?.hand.filter((card) => card.color === chosenColor).length ?? 0 : 0,
    [chosenColor, primaryCard, you],
  );
  const shuRemainderTargets = useMemo(() => {
    if (primaryCard?.kind !== 'shu' || !selectableTargets.length) return [];
    if (selectedShuColorCount < selectableTargets.length) return [];
    const remainder = selectedShuColorCount % selectableTargets.length;
    if (!remainder) return [];
    const fewest = Math.min(...selectableTargets.map((player) => player.hand_count));
    const candidates = selectableTargets.filter((player) => player.hand_count === fewest);
    return candidates.length > 1 ? candidates : [];
  }, [primaryCard, selectableTargets, selectedShuColorCount]);
  const shuNeedsRemainderTarget = primaryCard?.kind === 'shu' && shuRemainderTargets.length > 1;
  const targetOptions = shuNeedsRemainderTarget ? shuRemainderTargets : selectableTargets;
  const showTargetSelector = primaryCard?.kind !== 'shu' || shuNeedsRemainderTarget;
  const targetLabel = primaryCard?.kind === 'shu' ? '余牌给' : '目标';

  useEffect(() => {
    if (!targetPlayerId) return;
    if (!showTargetSelector || !targetOptions.some((player) => player.player_id === targetPlayerId)) {
      setTargetPlayerId('');
    }
  }, [showTargetSelector, targetOptions, targetPlayerId]);

  useEffect(() => {
    setRespondingPromptId(null);
    if (!pending || pending.status !== 'open') return;
    setPromptNow(Date.now());
    const timer = window.setInterval(() => setPromptNow(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, [pending?.prompt_id, pending?.status]);

  const saveSession = (nextSession: SessionState) => {
    localStorage.setItem(SESSION_KEY, JSON.stringify(nextSession));
    setSession(nextSession);
  };

  useEffect(() => {
    if (restoredRef.current) return;
    restoredRef.current = true;
    const stored = localStorage.getItem(SESSION_KEY);
    if (!stored) return;
    let previous: SessionState;
    try {
      previous = JSON.parse(stored) as SessionState;
    } catch {
      localStorage.removeItem(SESSION_KEY);
      return;
    }
    reconnectRoom(previous)
      .then((response) => {
        const nextSession: SessionState = {
          room_code: response.room_code,
          player_id: response.player_id,
          reconnect_token: response.reconnect_token ?? previous.reconnect_token,
          session_id: response.session_id,
          seat_index: response.seat_index,
          is_host: response.is_host,
        };
        const privateSnapshot = response.private_snapshot as {
          state: RoomState;
          you: PrivatePlayerState;
        };
        setRoom(privateSnapshot.state);
        setYou(privateSnapshot.you);
        saveSession(nextSession);
        setNotice('已恢复上次牌局');
      })
      .catch(() => {
        localStorage.removeItem(SESSION_KEY);
        setError('重连失败，请重新创建或加入房间');
      });
  }, []);

  useEffect(() => {
    if (!session) return;
    setConnectionState('connecting');
    const socket = new WebSocket(roomWebSocketUrl(session.room_code));
    socketRef.current = socket;
    socket.onopen = () => {
      socket.send(
        JSON.stringify({
          event: 'authenticate',
          player_id: session.player_id,
          session_id: session.session_id,
        }),
      );
      setNotice('正在验证实时连接');
    };
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data) as ServerEvent;
      if (message.event === 'snapshot' || message.event === 'state_patch') {
        setRoom(message.state);
      } else if (message.event === 'private_snapshot') {
        setRoom(message.state);
        setYou(message.you);
        setConnectionState((current) => {
          if (current !== 'online') setNotice('实时连接已建立');
          return 'online';
        });
      } else if (message.event === 'command_result') {
        setRespondingPromptId(null);
        setError('');
        setNotice(commandNotice(message.result));
      } else if (message.event === 'error') {
        setRespondingPromptId(null);
        setError(message.message ?? message.error);
      }
    };
    socket.onerror = () => {
      setConnectionState('offline');
      setError('WebSocket 连接失败');
    };
    socket.onclose = () => {
      if (socketRef.current === socket) {
        setConnectionState('offline');
        setNotice('实时连接已断开');
      }
    };
    return () => socket.close();
  }, [session]);

  const submitSession = async (mode: 'create' | 'join') => {
    setError('');
    try {
      const nextSession =
        mode === 'create'
          ? await createRoom(nickname.trim() || '玩家')
          : await joinRoom(joinCode.trim().toUpperCase(), nickname.trim() || '玩家');
      saveSession(nextSession);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '房间操作失败');
    }
  };

  const sendCommand = (commandType: string, payload: Record<string, unknown> = {}): boolean => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN || !session) {
      setError('实时连接尚未就绪');
      return false;
    }
    socket.send(
      JSON.stringify({
        event: 'command',
        action_id: genActionId(),
        command_type: commandType,
        player_id: session.player_id,
        payload,
        game_id: activeGame?.game_id,
        game_epoch: activeGame?.game_epoch,
        expected_state_version: room?.state_version,
      }),
    );
    return true;
  };

  const clearCardSelection = () => {
    setPrimaryCardId(null);
    setSupportCardIds([]);
  };

  const toggleSupport = (cardId: string) => {
    setSupportCardIds((current) =>
      current.includes(cardId) ? current.filter((item) => item !== cardId) : [...current, cardId],
    );
  };

  const playOrActivatePrimary = () => {
    if (!primaryCard) {
      setError('请先选择一张主牌');
      return;
    }
    if (primaryCard.category !== 'sui') {
      sendCommand('PLAY_CARD', {
        card_id: primaryCard.card_id,
        chosen_color: primaryCard.category === 'wild' ? chosenColor : undefined,
        declare_uno: declareUnoWithPlay,
      });
      clearCardSelection();
      return;
    }

    const payload: Record<string, unknown> = { card_id: primaryCard.card_id };
    if (primaryCard.kind === 'ji' || primaryCard.kind === 'shu') payload.chosen_color = chosenColor;
    if (primaryCard.kind === 'shu') {
      if (selectedShuColorCount < selectableTargets.length) {
        setError('黍牌选择的颜色数量不足，不能平均分给其他玩家');
        return;
      }
      if (shuNeedsRemainderTarget) {
        if (!targetPlayerId || !shuRemainderTargets.some((player) => player.player_id === targetPlayerId)) {
          setError('黍牌有余牌且并列最少，请选择余牌接收玩家');
          return;
        }
        payload.remainder_recipient_id = targetPlayerId;
      }
    }
    if (primaryCard.kind === 'yi') {
      const sum = supportCards.reduce((total, card) => total + (card.value ?? 0), 0);
      const validPair =
        supportCards.length === 2 &&
        supportCards.every((card) => card.category === 'number' && typeof card.value === 'number') &&
        sum === 8;
      if (!validPair) {
        setError('易牌需要选择两张数字牌，且点数之和必须为 8');
        return;
      }
      payload.pair_card_ids = supportCardIds;
    }
    if (primaryCard.kind === 'yu') payload.payment_card_ids = supportCardIds;
    if (primaryCard.kind === 'wang' || primaryCard.kind === 'zuole') payload.target_player_id = targetPlayerId;
    sendCommand('ACTIVATE_SPECIAL', payload);
    clearCardSelection();
  };

  const respondToPrompt = (response: string) => {
    if (!pending || !canRespond || respondingPromptId === pending.prompt_id) return;
    const payload: Record<string, unknown> = {
      prompt_id: pending.prompt_id,
      response,
    };
    if (response === 'submit_cards') payload.card_ids = supportCardIds;
    if (response === 'give_card' || response === 'control_play' || response === 'discard_card') payload.card_id = primaryCardId;
    if (response === 'chi' || response === 'peng' || response === 'gang') payload.card_ids = supportCardIds;
    if (response === 'restart') payload.payment_card_ids = supportCardIds;
    if (response === 'use_xi') payload.as_color = chosenColor;
    if (response === 'control_play') payload.chosen_color = chosenColor;
    setRespondingPromptId(pending.prompt_id);
    if (!sendCommand('RESPOND_TO_PROMPT', payload)) setRespondingPromptId(null);
    clearCardSelection();
  };

  const leaveRoom = () => {
    socketRef.current?.close();
    localStorage.removeItem(SESSION_KEY);
    setSession(null);
    setRoom(null);
    setYou(null);
    setConnectionState('offline');
    setNotice('');
    setError('');
  };

  if (!session) {
    return (
      <main className="entry-shell">
        <div className="entry-frame">
          <aside className="entry-intro">
            <p className="eyebrow">岁牌 × 经典 UNO</p>
            <h1>一眼看懂局势，随时加入牌桌</h1>
            <p>保留经典 UNO 节奏，加入望、易、年、重岳等岁牌机制。房间状态、行动顺序和特殊响应会实时同步。</p>
            <div className="entry-card-fan" aria-label="岁牌示例">
              <CardView assetKey="sui_wang" variant="preview" />
              <CardView assetKey="sui_nian" variant="preview" />
              <CardView assetKey="sui_chongyue" variant="preview" />
            </div>
            <div className="entry-facts">
              <span><ShieldCheck size={17} />后端权威结算</span>
              <span><Users size={17} />2–10 人实时联机</span>
            </div>
          </aside>

          <section className="entry-panel">
            <div>
              <p className="section-kicker">进入牌桌</p>
              <h2>创建新房间或加入好友</h2>
              <p>设置昵称后即可开始，房间号为 6 位字符。</p>
            </div>
            <label>
              昵称
              <input value={nickname} maxLength={24} onChange={(event) => setNickname(event.target.value)} />
            </label>
            <button data-testid="create-room" className="primary" type="button" onClick={() => submitSession('create')}>
              创建房间
            </button>
            <div className="entry-divider"><span>或加入现有房间</span></div>
            <div className="join-row">
              <input
                aria-label="房间号"
                placeholder="输入 6 位房间号"
                value={joinCode}
                onChange={(event) => setJoinCode(event.target.value.toUpperCase())}
              />
              <button data-testid="join-room" type="button" onClick={() => submitSession('join')}>
                加入
              </button>
            </div>
            {error ? <p className="error-banner">{error}</p> : null}
          </section>
        </div>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">岁牌 × 经典 UNO</p>
          <h1>多人联机牌桌</h1>
        </div>
        <nav className="topbar__actions" aria-label="房间操作">
          <button
            type="button"
            title="复制房间号"
            onClick={() => navigator.clipboard.writeText(session.room_code)}
          >
            <Copy size={17} />复制
          </button>
          {you?.is_host ? (
            <button type="button" title="重置房间" onClick={() => sendCommand('RESET_ROOM')}>
              <RotateCcw size={17} />Reset
            </button>
          ) : null}
          <button type="button" onClick={leaveRoom}>
            <LogOut size={17} />离开
          </button>
        </nav>
      </header>

      {room?.phase !== 'LOBBY' ? (
        <section className="room-band">
          <div className="room-code">
            <span>房间号</span>
            <strong data-testid="room-code">{session.room_code}</strong>
          </div>
          <div className="status-strip">
            <span><Users size={16} />{room?.players.length ?? 0} 人</span>
            <span><ShieldCheck size={16} />后端权威结算</span>
            <span className={'connection-text is-' + connectionState}>{notice}</span>
          </div>
        </section>
      ) : null}

      {error ? <p data-testid="error-banner" className="error-banner">{error}</p> : null}

      {room?.phase === 'LOBBY' && room ? (
        <LobbyDashboard
          room={room}
          session={session}
          you={you}
          connectionState={connectionState}
          onCopyRoomCode={() => navigator.clipboard.writeText(session.room_code)}
          onToggleReady={() => sendCommand('READY', { ready: !you?.ready })}
          onStartGame={() => sendCommand('START_GAME')}
        />
      ) : (
        <>
      <section className="table-layout">
        <aside className="players-rail" aria-label="玩家列表">
          {room?.players.map((player) => (
            <div
              className={`seat ${activeGame?.current_player_id === player.player_id ? 'is-current' : ''}`}
              key={player.player_id}
            >
              <span className="seat__name">{player.nickname}{player.is_host ? ' · 房主' : ''}</span>
              <span className="seat__meta">
                {player.online ? '在线' : '离线'} · {player.hand_count} 张 · {player.ready ? '已准备' : '未准备'}
              </span>
            </div>
          ))}
        </aside>

        <section className="table-center">
          <div className="turn-panel">
            <span>阶段：{room?.phase}</span>
            <strong>
              当前：{playerName(room, activeGame?.current_player_id)} ·
              颜色 {activeGame?.current_color ?? '无'} ·
              {activeGame?.direction === -1 ? '逆时针' : '顺时针'}
            </strong>
            <span>牌堆 {activeGame?.deck_count ?? 0}</span>
          </div>

          <div className="piles">
            <CardView assetKey="card_back" label={`摸牌堆 ${activeGame?.deck_count ?? 0}`} faceDown variant="table" />
            <CardView
              assetKey={activeGame?.top_discard?.asset_key ?? 'card_back'}
              label="弃牌堆"
              variant="table"
            />
            {activeGame?.field_card ? (
              <CardView assetKey={activeGame.field_card.asset_key} label="坎诺特" variant="table" />
            ) : null}
          </div>

          {activeGame?.shop_goods.length ? (
            <div className="shop-area">
              <div className="section-heading">
                <strong>坎诺特商店</strong>
                <button type="button" onClick={() => sendCommand('REFRESH_SHOP')}>
                  <RefreshCw size={16} />刷新
                </button>
              </div>
              <div className="shop-row">
                {activeGame.shop_goods.map((good) => (
                  <button
                    className="card-button"
                    type="button"
                    key={good.card_id}
                    onClick={() =>
                      sendCommand('BUY_SHOP_GOOD', {
                        good_card_id: good.card_id,
                        payment_card_id: primaryCardId,
                      })
                    }
                  >
                    <CardView assetKey={good.asset_key} label="购买" variant="thumbnail" />
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </section>
      </section>

      {pending ? (
        <section className="pending-panel" data-testid="pending-action">
          <div>
            <strong data-testid="special-prompt-card">{pending.display_title ?? promptTitle(promptCardKind(pending))}</strong>
            <span>来源：{playerName(room, pending.source_player_id)}</span>
            <p data-testid="special-prompt-hint">{pending.display_message ?? promptHint(promptCardKind(pending))}</p>
            <span data-testid="prompt-status">{promptStatusLabel(pending.status)}</span>
            {promptRemainingSeconds !== null ? (
              <span data-testid="prompt-countdown">{promptRemainingSeconds}s</span>
            ) : null}
          </div>
          {canRespond ? (
            <div className="action-row">
              {pending.legal_responses.map((response) => (
                <button
                  data-testid={`pending-response-${response}`}
                  className={response === pending.default_action ? '' : 'primary'}
                  type="button"
                  key={response}
                  disabled={respondingPromptId === pending.prompt_id || promptRemainingSeconds === 0}
                  onClick={() => respondToPrompt(response)}
                >
                  {responseLabel(response)}
                </button>
              ))}
            </div>
          ) : (
            <span>{hasOpenPrompt ? '等待授权响应者' : promptStatusLabel(pending.status)}</span>
          )}
        </section>
      ) : null}

      <section className="control-bar">
        <button data-testid="draw-card" type="button" disabled={!isMyTurn || hasOpenPrompt} onClick={() => sendCommand('DRAW_CARD')}>
          摸牌
        </button>
        <label>
          颜色
          <select value={chosenColor} onChange={(event) => setChosenColor(event.target.value as NonNullable<CardState['color']>)}>
            {COLORS.map((color) => <option key={color} value={color ?? ''}>{color}</option>)}
          </select>
        </label>
        {showTargetSelector ? (
          <label>
            {targetLabel}
            <select value={targetPlayerId} onChange={(event) => setTargetPlayerId(event.target.value)}>
              <option value="">请选择</option>
              {targetOptions.map((player) => <option key={player.player_id} value={player.player_id}>{player.nickname}</option>)}
            </select>
          </label>
        ) : null}
        <label className="check-control">
          <input
            type="checkbox"
            checked={declareUnoWithPlay}
            onChange={(event) => setDeclareUnoWithPlay(event.target.checked)}
          />
          随出牌宣告 UNO
        </label>
        {selectedBatch1Hint ? (
          <p data-testid="batch1-special-hint" className="special-hint">{selectedBatch1Hint}</p>
        ) : null}
        <button
          data-testid="play-selected"
          className="primary"
          type="button"
          disabled={!primaryCard || Boolean(hasOpenPrompt && !canRespond)}
          onClick={playOrActivatePrimary}
        >
          出牌 / 发动
        </button>
        {you?.uno.must_declare ? (
          <button data-testid="declare-uno" className="warning" type="button" onClick={() => sendCommand('DECLARE_UNO')}>
            宣告 UNO
          </button>
        ) : null}
        {you?.uno.can_catch_player_id ? (
          <button
            data-testid="catch-uno"
            className="warning"
            type="button"
            onClick={() => sendCommand('CATCH_UNO', { target_player_id: you.uno.can_catch_player_id })}
          >
            抓取 {playerName(room, you.uno.can_catch_player_id)}
          </button>
        ) : null}
      </section>

      <section className="hand-zone" aria-label="我的手牌">
        {you?.hand.map((card) => (
          <article className="hand-item" key={card.card_id}>
            <button
              type="button"
              className="card-button"
              data-testid="hand-card"
              data-card-kind={card.kind}
              data-card-category={card.category}
              data-card-color={card.color ?? 'none'}
              data-card-value={card.value ?? ''}
              onClick={() => setPrimaryCardId(card.card_id)}
            >
              <CardView
                assetKey={card.asset_key}
                label={primaryCardId === card.card_id ? '主选' : undefined}
                variant="hand"
                selected={primaryCardId === card.card_id}
              />
            </button>
            <label className="support-choice">
              <input
                type="checkbox"
                checked={supportCardIds.includes(card.card_id)}
                onChange={() => toggleSupport(card.card_id)}
              />
              附加选择
            </label>
          </article>
        ))}
        {!you?.hand.length ? <p className="empty-state">当前没有手牌</p> : null}
      </section>

      {activeGame?.status === 'FINISHED' ? (
        <section className="winner-banner">
          胜者：{playerName(room, activeGame.winner_player_id)}
        </section>
      ) : null}
        </>
      )}
    </main>
  );
}
