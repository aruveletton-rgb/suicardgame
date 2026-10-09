import { CardView } from '../CardView';
import type { CardState } from '../../types';
import type { CardPickRole } from '../../hooks/game/useGameSelection';

type HandRackProps = {
  cards: CardState[];
  primaryCardId: string | null;
  supportCardIds: string[];
  paymentCardId: string | null;
  legalCardIds?: Set<string> | null;
  selectableCardIds?: Set<string> | null;
  pickRole: CardPickRole;
  onPickRole: (role: CardPickRole) => void;
  onSelectCard: (cardId: string) => void;
};

const roleLabels: Record<CardPickRole, string> = {
  primary: '主牌',
  support: '多选牌',
  payment: '支付牌',
};

export function HandRack({
  cards,
  primaryCardId,
  supportCardIds,
  paymentCardId,
  legalCardIds,
  selectableCardIds,
  pickRole,
  onPickRole,
  onSelectCard,
}: HandRackProps) {
  return (
    <section className="hand-rack" aria-label="我的手牌">
      <div className="hand-rack__toolbar" role="group" aria-label="手牌选择用途">
        <span>点击手牌设为：</span>
        {(Object.keys(roleLabels) as CardPickRole[]).map((role) => (
          <button
            className={pickRole === role ? 'is-active' : ''}
            type="button"
            key={role}
            aria-pressed={pickRole === role}
            onClick={() => onPickRole(role)}
          >
            {roleLabels[role]}
          </button>
        ))}
      </div>
      <div className="hand-zone">
        {cards.map((card) => {
          const isPrimary = primaryCardId === card.card_id;
          const isSupport = supportCardIds.includes(card.card_id);
          const isPayment = paymentCardId === card.card_id;
          const isLegal = legalCardIds == null || legalCardIds.has(card.card_id);
          const isSelectable = selectableCardIds == null || selectableCardIds.has(card.card_id);
          const selectionLabel = isPrimary ? '主牌' : isPayment ? '支付' : isSupport ? '多选' : undefined;
          return (
            <article className="hand-item" key={card.card_id}>
              <button
                type="button"
                className="card-button"
                data-testid="hand-card"
                data-card-kind={card.kind}
                data-card-category={card.category}
                data-card-color={card.color ?? 'none'}
                data-card-value={card.value ?? ''}
                aria-label={`${card.kind}，${selectionLabel ?? `设为${roleLabels[pickRole]}`}`}
                aria-pressed={Boolean(selectionLabel)}
                disabled={!isSelectable}
                onClick={() => onSelectCard(card.card_id)}
              >
                <CardView assetKey={card.asset_key} label={selectionLabel} variant="hand" selected={Boolean(selectionLabel)} legal={legalCardIds ? isLegal : undefined} />
              </button>
            </article>
          );
        })}
        {!cards.length ? <p className="empty-state">当前没有手牌</p> : null}
      </div>
    </section>
  );
}
