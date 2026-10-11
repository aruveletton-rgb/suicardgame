import { memo } from 'react';
import { CardView } from '../CardView';
import type { ChongyueEffect, PlayerState } from '../../types';

const COLORS = ['red', 'yellow', 'green', 'blue'] as const;
const COLOR_NAMES = { red: '红', yellow: '黄', green: '绿', blue: '蓝' };

export const ChongyuePanel = memo(function ChongyuePanel({ effect, players }: { effect: ChongyueEffect; players: PlayerState[] }) {
  const playerName = (id: string | undefined) => players.find((player) => player.player_id === id)?.nickname ?? '玩家';
  const order = [...new Set([...(effect.reveal_order ?? []), ...Object.keys(effect.displayed_cards ?? {})])];
  const sourceId = effect.source_player_id;
  if (sourceId && !order.includes(sourceId)) order.push(sourceId);
  const challengeSucceeded = effect.challenge_result === 'challenge_succeeded';
  const challengeFailed = effect.challenge_result === 'challenge_failed';
  const sourceImmune = effect.challenge_result === 'source_immune';

  return (
    <section className="chongyue-panel" data-testid="chongyue-panel" aria-label="重岳展示区">
      <div className="chongyue-panel__heading">
        <strong>重岳 · 四色展示</strong>
        {effect.phase !== 'completed' && effect.acting_player_id ? <span>当前：{playerName(effect.acting_player_id)}</span> : <span>展示结束</span>}
        {challengeSucceeded || challengeFailed ? (
          <span className={`chongyue-result ${challengeSucceeded ? 'is-success' : ''}`} data-testid="chongyue-result" role="status">
            {playerName(effect.challenger_player_id)}质疑{challengeSucceeded ? '成功' : '失败'}
          </span>
        ) : null}
        {sourceImmune ? <span data-testid="chongyue-result" role="status">使用者已规避本次质疑</span> : null}
      </div>
      {order.map((id) => {
        const cards = effect.displayed_cards?.[id] ?? [];
        const displayedColors = new Set(effect.displayed_colors?.[id] ?? []);
        const missing = COLORS.filter((color) => !displayedColors.has(color));
        const active = effect.acting_player_id === id && effect.phase !== 'completed';
        return (
          <article className={`chongyue-player ${active ? 'is-active' : ''}`} key={id} data-testid="chongyue-player" data-player-id={id}>
            <div className="chongyue-player__summary">
              <strong>{playerName(id)}{id === sourceId ? <small className="chongyue-player__source">使用者</small> : null}</strong>
              <div className="chongyue-colors" aria-label={`已展示 ${displayedColors.size}/4 色`}>
                {COLORS.map((color) => <span key={color} className={`chongyue-color chongyue-color--${color} ${displayedColors.has(color) ? 'is-shown' : ''}`}>{COLOR_NAMES[color]}</span>)}
              </div>
              <progress data-testid="chongyue-progress" value={displayedColors.size} max={4} aria-label={`${playerName(id)}四色进度`} />
              <small>{displayedColors.size}/4 色 · 已摸 {effect.drawn_until_four?.[id] ?? 0} 张</small>
              {active && missing.length && !effect.immune_player_ids?.includes(id) ? <small>缺 {missing.map((color) => COLOR_NAMES[color]).join('、')}</small> : null}
              {effect.immune_player_ids?.includes(id) ? <small>已规避展示</small> : null}
            </div>
            <div className="chongyue-player__cards" aria-label={`${playerName(id)}已展示的牌`}>
              {cards.map((card) => <CardView key={card.card_id} assetKey={card.asset_key} variant="thumbnail" />)}
              {!cards.length ? <span className="chongyue-player__empty">尚未展示</span> : null}
            </div>
          </article>
        );
      })}
    </section>
  );
});
