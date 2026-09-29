import { Copy, LogOut, RotateCcw, ShieldCheck, Users, BookOpen } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { createRoom, joinRoom, reconnectRoom, roomWebSocketUrl } from './api';
import { CardView } from './components/CardView';
import { LobbyDashboard } from './components/LobbyDashboard';
import { EntryPanel, GameResult, RulesGallery, createPublicInviteUrl } from './components/product';
import { HandRack } from './components/table/HandRack';
import { PausePanel } from './components/table/PausePanel';
import { PlayerOrbit } from './components/table/PlayerOrbit';
import { ShopPanel } from './components/table/ShopPanel';
import { useGameFeedback } from './hooks/game/useGameFeedback';
import { useGameSelection } from './hooks/game/useGameSelection';
import type { AvatarId, CardState, PendingAction, PrivatePlayerState, RoomState, ServerEvent, SessionState } from './types';
import './styles/product.css';

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
    evade: '使用高辈分牌规避',
    draw_four: '摸四张',
    give_card: '赠送主选牌',
    control_play: '代打主选牌',
    control_pass: '不出牌',
    discard_card: '弃掉主选牌',
    chi: '吃',
    peng: '碰',
    gang: '杠',
    accept: '确认',
  };
  return labels[response] ?? response;
}

function phaseLabel(phase: string | undefined): string {
  return ({ LOBBY: '大厅', STARTING: '准备中', IN_GAME: '进行中', ROUND_RESULT: '本局结算', RESETTING: '重置中', CLOSED: '已关闭' } as Record<string, string>)[phase ?? ''] ?? '进行中';
}

function colorLabel(color: CardState['color']): string {
  return ({ red: '红色', yellow: '黄色', green: '绿色', blue: '蓝色' } as Record<string, string>)[color ?? ''] ?? '无';
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
    nian: '年牌：摸牌、弃牌与吃碰杠',
    nian_claim: '年牌：吃 / 碰 / 杠响应',
    nian_turn_end_discard: '年牌：回合结束弃牌',
    chongyue: '重岳牌：展示四色与质疑',
    wang: '望牌：连续控制',
    sui_xiang: '岁相牌：同色响应',
    cannot: '坎诺特：商店操作',
    fuzhou: '符咒牌：赠牌响应',
    wild_draw_four_challenge: '+4 质疑',
    WILD_DRAW_FOUR_CHALLENGE: '+4 质疑',
  };
  return titles[kind] ?? `特殊牌：${kind}`;
}

function promptDisplayTitle(pending: PendingAction): string {
  if (pending.display_title === 'Response required') return '需要响应';
  return pending.display_title ?? promptTitle(promptCardKind(pending));
}

function promptDisplayMessage(pending: PendingAction): string {
  if (pending.display_message === 'Choose an available response before the window closes.') return '请在倒计时结束前选择可用操作。';
  return pending.display_message ?? promptHint(promptCardKind(pending));
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
  const [nickname, setNickname] = useState('');
  const [avatarId, setAvatarId] = useState<AvatarId>('default');
  const [joinCode, setJoinCode] = useState('');
  const [entryBusy, setEntryBusy] = useState(false);
  const [session, setSession] = useState<SessionState | null>(null);
  const [room, setRoom] = useState<RoomState | null>(null);
  const [you, setYou] = useState<PrivatePlayerState | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [connectionState, setConnectionState] = useState<'connecting' | 'online' | 'offline'>('offline');
  const {
    primaryCardId,
    supportCardIds,
    paymentCardId,
    chosenColor,
    targetPlayerId,
    pickRole,
    setPaymentCardId,
    setChosenColor,
    setTargetPlayerId,
    setPickRole,
    selectCard,
    clearCards,
  } = useGameSelection();
  const [declareUnoWithPlay, setDeclareUnoWithPlay] = useState(false);
  const [respondingPromptId, setRespondingPromptId] = useState<string | null>(null);
  const [shopOpen, setShopOpen] = useState(false);
  const [selectedShopGoodId, setSelectedShopGoodId] = useState<string | null>(null);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [promptNow, setPromptNow] = useState(() => Date.now());
  const socketRef = useRef<WebSocket | null>(null);
  const restoredRef = useRef(false);

  const activeGame = room?.active_game ?? null;
  const feedback = useGameFeedback(room, activeGame);
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
  const turnRemainingSeconds = activeGame?.turn_deadline_at && !activeGame.pause_state
    ? Math.max(0, Math.ceil((activeGame.turn_deadline_at * 1000 - promptNow) / 1000))
    : null;
  const allTargetOptions = useMemo(() => room?.players ?? [], [room]);
  const selectableTargets = useMemo(
    () => allTargetOptions.filter((player) => player.player_id !== you?.player_id),
    [allTargetOptions, you],
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
  const targetOptions = primaryCard?.kind === 'zuole'
    ? allTargetOptions
    : shuNeedsRemainderTarget
      ? shuRemainderTargets
      : selectableTargets;
  const showTargetSelector = primaryCard?.kind === 'wang' || primaryCard?.kind === 'zuole' || shuNeedsRemainderTarget;
  const showColorSelector = primaryCard?.category === 'wild' || primaryCard?.kind === 'ji' || primaryCard?.kind === 'shu';
  const targetLabel = primaryCard?.kind === 'shu' ? '余牌给' : '目标';

  useEffect(() => {
    if (!targetPlayerId) return;
    if (!showTargetSelector || !targetOptions.some((player) => player.player_id === targetPlayerId)) {
      setTargetPlayerId('');
    }
  }, [showTargetSelector, targetOptions, targetPlayerId]);

  useEffect(() => {
    setRespondingPromptId(null);
    if ((!pending || pending.status !== 'open') && !activeGame?.turn_deadline_at) return;
    setPromptNow(Date.now());
    const timer = window.setInterval(() => setPromptNow(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, [activeGame?.turn_deadline_at, pending?.prompt_id, pending?.status]);

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
          avatar_id: response.avatar_id ?? previous.avatar_id ?? 'default',
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
      setNotice((current) => current || '正在验证实时连接');
    };
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data) as ServerEvent;
      if (message.event === 'snapshot' || message.event === 'state_patch') {
        setRoom(message.state);
      } else if (message.event === 'private_snapshot') {
        setRoom(message.state);
        setYou(message.you);
        setConnectionState((current) => {
          if (current !== 'online') setNotice((noticeText) => noticeText || '实时连接已建立');
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
    setEntryBusy(true);
    try {
      const nextSession =
        mode === 'create'
          ? await createRoom(nickname.trim() || '玩家', avatarId)
          : await joinRoom(joinCode.trim().toUpperCase(), nickname.trim() || '玩家', avatarId);
      saveSession(nextSession);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '房间操作失败');
    } finally {
      setEntryBusy(false);
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
      clearCards();
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
    clearCards();
  };

  const respondToPrompt = (response: string) => {
    if (!pending || !canRespond || respondingPromptId === pending.prompt_id) return;
    const singleCardResponses = ['give_card', 'control_play', 'discard_card', 'evade'];
    const multipleCardResponses = ['submit_cards', 'chi', 'peng', 'gang', 'restart'];
    if (singleCardResponses.includes(response) && !primaryCardId) {
      setError('该响应需要先在手牌区选择一张主牌');
      setPickRole('primary');
      return;
    }
    if (multipleCardResponses.includes(response) && supportCardIds.length === 0) {
      setError('该响应需要先切换到“多选牌”并选择所需手牌');
      setPickRole('support');
      return;
    }
    const payload: Record<string, unknown> = {
      prompt_id: pending.prompt_id,
      response,
    };
    if (response === 'submit_cards') payload.card_ids = supportCardIds;
    if (response === 'give_card' || response === 'control_play' || response === 'discard_card' || response === 'evade') payload.card_id = primaryCardId;
    if (response === 'chi' || response === 'peng' || response === 'gang') payload.card_ids = supportCardIds;
    if (response === 'restart') payload.payment_card_ids = supportCardIds;
    if (response === 'use_xi') payload.as_color = chosenColor;
    if (response === 'control_play') payload.chosen_color = chosenColor;
    setRespondingPromptId(pending.prompt_id);
    if (!sendCommand('RESPOND_TO_PROMPT', payload)) setRespondingPromptId(null);
    clearCards();
  };

  const confirmShopExchange = () => {
    if (!selectedShopGoodId || !paymentCardId) {
      setError('请选择商品，并在手牌区选择一张支付牌');
      setShopOpen(true);
      setPickRole('payment');
      return;
    }
    if (sendCommand('BUY_SHOP_GOOD', {
      good_card_id: selectedShopGoodId,
      payment_card_id: paymentCardId,
    })) {
      setSelectedShopGoodId(null);
      setPaymentCardId(null);
      setPickRole('primary');
    }
  };

  const leaveRoom = () => {
    if (room?.phase === 'IN_GAME' && !window.confirm('离开会清除本机保存的重连会话。确定离开牌桌吗？')) return;
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
      <EntryPanel
        nickname={nickname}
        avatarId={avatarId}
        roomCode={joinCode}
        busy={entryBusy}
        error={error}
        onNicknameChange={setNickname}
        onAvatarChange={setAvatarId}
        onRoomCodeChange={setJoinCode}
        onCreate={() => submitSession('create')}
        onJoin={() => submitSession('join')}
      />
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">岁牌 × 经典 UNO</p>
          <h1>战术牌桌 <span className="topbar__room">#{session.room_code}</span></h1>
        </div>
        <nav className="topbar__actions" aria-label="房间操作">
          <button
            type="button"
            title="复制房间号"
            onClick={() => navigator.clipboard.writeText(session.room_code)}
          >
            <Copy size={17} />复制
          </button>
          <button type="button" title="打开规则图鉴" onClick={() => setRulesOpen((open) => !open)}>
            <BookOpen size={17} />图鉴
          </button>
          {you?.is_host ? (
            <button type="button" title="结束本局并回到大厅" onClick={() => {
              if (window.confirm('重置会结束当前牌局并回到大厅。确定继续吗？')) sendCommand('RESET_ROOM');
            }}>
              <RotateCcw size={17} />重置
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
            <span><ShieldCheck size={16} />规则同步</span>
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
          inviteUrl={createPublicInviteUrl(session.room_code)}
          onCopyInviteLink={(inviteUrl) => navigator.clipboard.writeText(inviteUrl)}
          onOpenRules={() => setRulesOpen(true)}
          onToggleReady={() => sendCommand('READY', { ready: !you?.ready })}
          onStartGame={() => sendCommand('START_GAME')}
        />
      ) : (
        <>
      <section className="game-workspace" data-layout="responsive-table">
        <section className="table-layout">
          <PlayerOrbit
            players={room?.players ?? []}
            currentPlayerId={activeGame?.current_player_id}
            youPlayerId={you?.player_id}
          />
          <section className="table-center">
            <div className="turn-panel">
              <span>阶段：{phaseLabel(room?.phase)}</span>
              <strong>
                当前：{playerName(room, activeGame?.current_player_id)} ·
                颜色 {colorLabel(activeGame?.current_color ?? null)} ·
                {activeGame?.direction === -1 ? '逆时针' : '顺时针'}
              </strong>
              <span>{turnRemainingSeconds !== null ? `回合 ${turnRemainingSeconds}s` : `牌堆 ${activeGame?.deck_count ?? 0}`}</span>
            </div>

            <div className="piles" aria-label="牌桌中央">
              <CardView assetKey="card_back" label={`摸牌堆 ${activeGame?.deck_count ?? 0}`} faceDown variant="table" />
              <CardView assetKey={activeGame?.top_discard?.asset_key ?? 'card_back'} label="弃牌堆" variant="table" />
              {activeGame?.field_card ? <CardView assetKey={activeGame.field_card.asset_key} label="坎诺特" variant="table" /> : null}
            </div>

            <ShopPanel
              goods={activeGame?.shop_goods ?? []}
              open={shopOpen}
              selectedGoodId={selectedShopGoodId}
              paymentCardId={paymentCardId}
              onToggle={() => setShopOpen((open) => !open)}
              onSelectGood={(cardId) => {
                setSelectedShopGoodId((current) => current === cardId ? null : cardId);
                setShopOpen(true);
                setPickRole('payment');
              }}
              onRefresh={() => sendCommand('REFRESH_SHOP')}
              onConfirm={confirmShopExchange}
            />
          </section>
        </section>

        {feedback ? <div className="event-feedback" key={feedback.id} role="status">{feedback.message}</div> : null}

        {activeGame?.pause_state ? (
          <PausePanel
            pause={activeGame.pause_state}
            isHost={Boolean(you?.is_host)}
            onContinue={() => sendCommand('CONTINUE_WAITING')}
            onAbort={() => {
              if (window.confirm('结束本局不会按手牌数判胜者。确定继续吗？')) sendCommand('ABORT_GAME');
            }}
          />
        ) : null}

        {pending ? (
          <section className="pending-panel" data-testid="pending-action">
            <div>
              <strong data-testid="special-prompt-card">{promptDisplayTitle(pending)}</strong>
              <span>来源：{playerName(room, pending.source_player_id)} · {pending.required ? '必选操作' : '可选响应'}</span>
              <p data-testid="special-prompt-hint">{promptDisplayMessage(pending)}</p>
              <span data-testid="prompt-status">{promptStatusLabel(pending.status)}</span>
              {promptRemainingSeconds !== null ? <span data-testid="prompt-countdown">{promptRemainingSeconds}s</span> : null}
              {promptRemainingSeconds === 0 && hasOpenPrompt ? <em>已到显示时限，等待服务端结算或暂停状态。</em> : null}
            </div>
            {canRespond ? (
              <div className="action-row">
                {pending.legal_responses.map((response) => (
                  <button
                    data-testid={`pending-response-${response}`}
                    className={response === pending.default_action ? '' : 'primary'}
                    type="button"
                    key={response}
                    disabled={respondingPromptId === pending.prompt_id}
                    onClick={() => respondToPrompt(response)}
                  >
                    {responseLabel(response)}
                  </button>
                ))}
              </div>
            ) : <span>{hasOpenPrompt ? '等待授权响应者' : promptStatusLabel(pending.status)}</span>}
          </section>
        ) : null}

        <section className="control-bar" role="group" aria-label="上下文操作区">
          <div className="selection-summary">
            <strong>当前选择</strong>
            <span>主牌 {primaryCard ? primaryCard.kind : '未选'}</span>
            <span>多选 {supportCardIds.length} 张</span>
            <span>支付牌 {paymentCardId ? '已选' : '未选'}</span>
          </div>
          {showColorSelector ? (
            <fieldset className="context-choice color-choice">
              <legend>选择颜色</legend>
              {COLORS.map((color) => color ? (
                <button
                  className={`color-choice__${color} ${chosenColor === color ? 'is-active' : ''}`}
                  type="button"
                  key={color}
                  aria-pressed={chosenColor === color}
                  onClick={() => setChosenColor(color)}
                >{colorLabel(color)}</button>
              ) : null)}
            </fieldset>
          ) : null}
          {showTargetSelector ? (
            <fieldset className="context-choice target-choice">
              <legend>{targetLabel}</legend>
              {targetOptions.map((player) => (
                <button
                  className={targetPlayerId === player.player_id ? 'is-active' : ''}
                  type="button"
                  key={player.player_id}
                  aria-pressed={targetPlayerId === player.player_id}
                  onClick={() => setTargetPlayerId(player.player_id)}
                >{player.nickname}{player.player_id === you?.player_id ? '（自己）' : ''}</button>
              ))}
            </fieldset>
          ) : null}
          <button data-testid="draw-card" type="button" disabled={!isMyTurn || hasOpenPrompt || Boolean(activeGame?.pause_state)} onClick={() => sendCommand('DRAW_CARD')}>摸牌</button>
          <button
            className={declareUnoWithPlay ? 'is-active' : ''}
            type="button"
            aria-pressed={declareUnoWithPlay}
            onClick={() => setDeclareUnoWithPlay((declared) => !declared)}
          >随出牌宣告 UNO</button>
          <button
            data-testid="play-selected"
            className="primary"
            type="button"
            disabled={!primaryCard || Boolean(hasOpenPrompt && !canRespond) || Boolean(activeGame?.pause_state)}
            onClick={playOrActivatePrimary}
          >确认出牌 / 发动</button>
          {you?.uno.must_declare ? <button data-testid="declare-uno" className="warning" type="button" onClick={() => sendCommand('DECLARE_UNO')}>宣告 UNO</button> : null}
          {you?.uno.can_catch_player_id ? (
            <button data-testid="catch-uno" className="warning" type="button" onClick={() => sendCommand('CATCH_UNO', { target_player_id: you.uno.can_catch_player_id })}>
              抓取 {playerName(room, you.uno.can_catch_player_id)}
            </button>
          ) : null}
          {selectedBatch1Hint ? <p data-testid="batch1-special-hint" className="special-hint">{selectedBatch1Hint}</p> : null}
        </section>

        <HandRack
          cards={you?.hand ?? []}
          primaryCardId={primaryCardId}
          supportCardIds={supportCardIds}
          paymentCardId={paymentCardId}
          pickRole={pickRole}
          onPickRole={setPickRole}
          onSelectCard={selectCard}
        />

        {room?.phase === 'ROUND_RESULT' && activeGame ? (
          <GameResult
            players={room.players}
            winnerPlayerId={activeGame.winner_player_id}
            outcome={activeGame.status === 'ABORTED_BY_ROOM_RESET' ? 'aborted' : 'completed'}
            canManage={Boolean(you?.is_host)}
            onRematch={() => you?.is_host ? sendCommand('REMATCH') : setError('只有房主可以发起再来一局')}
            onReturnLobby={() => you?.is_host ? sendCommand('REMATCH') : setError('等待房主返回大厅')}
          />
        ) : null}
      </section>
        </>
      )}
      <RulesGallery open={rulesOpen} onClose={() => setRulesOpen(false)} />
    </main>
  );
}
