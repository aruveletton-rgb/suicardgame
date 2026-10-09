import type { CardState } from '../types';

export function canPlayNormalCard(card: CardState, top: CardState | null, color: CardState['color']): boolean {
  if (card.category === 'field') return false;
  if (card.category === 'sui' || card.category === 'wild') return true;
  if (!top) return true;
  if (color && card.color === color) return true;
  if (card.category === 'number' && top.category === 'number' && card.value === top.value) return true;
  return card.category === 'action' && top.category === 'action' && card.kind === top.kind;
}

export function cardUseHint(card: CardState): string {
  if (card.kind === 'xi') return '夕牌在响应窗口中通过“使用夕牌”发动';
  if (card.kind === 'zuole') return '左乐只能在岁牌效果生效期间使用';
  if (card.kind === 'wang') return '望牌在其他玩家无法出牌时使用';
  if (card.category === 'field') return '场地牌不能作为手牌打出';
  return '这张牌当前不能打出';
}
