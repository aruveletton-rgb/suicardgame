import { RefreshCw, Store } from 'lucide-react';
import { CardView } from '../CardView';
import type { CardState } from '../../types';

type ShopPanelProps = {
  goods: CardState[];
  open: boolean;
  selectedGoodId: string | null;
  paymentCardId: string | null;
  onToggle: () => void;
  onSelectGood: (cardId: string) => void;
  onRefresh: () => void;
  onConfirm: () => void;
};

export function ShopPanel({
  goods,
  open,
  selectedGoodId,
  paymentCardId,
  onToggle,
  onSelectGood,
  onRefresh,
  onConfirm,
}: ShopPanelProps) {
  if (!goods.length) return null;
  return (
    <section className={`shop-area ${open ? 'is-open' : ''}`} aria-label="坎诺特商店">
      <div className="section-heading">
        <strong><Store size={16} />坎诺特商店</strong>
        <div className="shop-actions">
          <button className="shop-toggle" type="button" aria-expanded={open} onClick={onToggle}>
            <Store size={16} />{open ? '收起商品' : '展开商品'}
          </button>
          <button type="button" onClick={onRefresh}><RefreshCw size={16} />刷新</button>
        </div>
      </div>
      <div className="shop-row">
        {goods.map((good) => (
          <button
            className={selectedGoodId === good.card_id ? 'card-button is-selected-good' : 'card-button'}
            type="button"
            key={good.card_id}
            aria-pressed={selectedGoodId === good.card_id}
            onClick={() => onSelectGood(good.card_id)}
          >
            <CardView assetKey={good.asset_key} label={selectedGoodId === good.card_id ? '待购买' : '选择商品'} variant="thumbnail" selected={selectedGoodId === good.card_id} />
          </button>
        ))}
      </div>
      <div className="shop-confirm">
        <span>{selectedGoodId ? '已选商品' : '请选择商品'} · {paymentCardId ? '已选支付牌' : '请在手牌区切换到“支付牌”后选择'}</span>
        <button className="primary" type="button" disabled={!selectedGoodId || !paymentCardId} onClick={onConfirm}>确认交换</button>
      </div>
    </section>
  );
}
