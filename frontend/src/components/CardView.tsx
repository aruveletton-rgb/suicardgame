import manifest from '../data/cardManifest.json';
import { specialRuleByAssetKey } from '../data/rules';

export type CardViewProps = {
  assetKey: string;
  label?: string;
  variant?: 'thumbnail' | 'hand' | 'table' | 'preview' | 'rule';
  faceDown?: boolean;
  selected?: boolean;
  legal?: boolean;
  disabled?: boolean;
};

const classByVariant = {
  thumbnail: 'card card--thumbnail product-card product-card--thumbnail',
  hand: 'card card--hand product-card product-card--hand',
  table: 'card card--table product-card product-card--table',
  preview: 'card card--preview product-card product-card--preview',
  rule: 'card card--rule product-card product-card--rule',
};

const COLOR_LABELS: Record<string, string> = {
  red: '红色',
  yellow: '黄色',
  green: '绿色',
  blue: '蓝色',
  wild: '无色',
};

type UnoFace = {
  color: string;
  kind: string;
  symbol: string;
  accessibleName: string;
};

function unoFace(assetKey: string): UnoFace | null {
  if (!assetKey.startsWith('uno_')) return null;
  if (assetKey === 'uno_wild') {
    return { color: 'wild', kind: 'wild', symbol: 'W', accessibleName: '万能牌' };
  }
  if (assetKey === 'uno_wild_draw_four') {
    return { color: 'wild', kind: 'wild-draw-four', symbol: '+4', accessibleName: '万能加四牌' };
  }

  const [, color, ...parts] = assetKey.split('_');
  const kind = parts.join('_');
  const symbolByKind: Record<string, string> = {
    skip: '⊘',
    reverse: '↻',
    draw_two: '+2',
  };
  const nameByKind: Record<string, string> = {
    skip: '禁止',
    reverse: '反转',
    draw_two: '加二',
  };
  const symbol = symbolByKind[kind] ?? kind;
  const cardName = nameByKind[kind] ?? `${kind} 点`;
  return {
    color,
    kind: /^\d$/.test(kind) ? 'number' : kind.replace(/_/g, '-'),
    symbol,
    accessibleName: `${COLOR_LABELS[color] ?? color}${cardName}牌`,
  };
}

function CardBack() {
  return (
    <div className="product-card-back" role="img" aria-label="牌背">
      <span className="product-card-back__frame" aria-hidden="true">
        <i />
        <strong>岁</strong>
        <small>SUI / UNO</small>
      </span>
    </div>
  );
}

export function CardView({
  assetKey,
  label,
  variant = 'table',
  faceDown = false,
  selected = false,
  legal,
  disabled = false,
}: CardViewProps) {
  const specialRule = specialRuleByAssetKey[assetKey];
  const uno = !faceDown ? unoFace(assetKey) : null;
  const fallbackSrc = (manifest as Record<string, string>)[assetKey] ?? (manifest as Record<string, string>).card_back;
  const stateClass = [
    selected ? 'is-selected' : '',
    legal === true ? 'is-legal' : '',
    legal === false ? 'is-illegal' : '',
    disabled ? 'is-disabled' : '',
  ].filter(Boolean).join(' ');

  return (
    <figure
      className={`${classByVariant[variant]} ${stateClass}`}
      data-asset-key={assetKey}
      data-card-category={faceDown ? 'back' : specialRule?.category ?? (uno ? 'uno' : 'unknown')}
      title={label ?? specialRule?.name ?? uno?.accessibleName ?? assetKey}
    >
      {faceDown || assetKey === 'card_back' ? (
        <CardBack />
      ) : uno ? (
        <div
          className={`uno-card-face product-uno product-uno--${uno.color} product-uno--${uno.kind}`}
          role="img"
          aria-label={uno.accessibleName}
        >
          <span className="uno-card-corner product-uno__corner" aria-hidden="true">{uno.symbol}</span>
          <span className="product-uno__oval" aria-hidden="true"><strong>{uno.symbol}</strong></span>
          <span className="uno-card-corner uno-card-corner--bottom product-uno__corner product-uno__corner--bottom" aria-hidden="true">{uno.symbol}</span>
          <span className="product-uno__color-name" aria-hidden="true">{COLOR_LABELS[uno.color]}</span>
        </div>
      ) : specialRule ? (
        <div className={`sui-card-face product-sui product-sui--${specialRule.category}`} role="img" aria-label={`${specialRule.name}，${specialRule.categoryLabel}`}>
          <img src={specialRule.cardArt} alt="" draggable={false} />
          <span className="sui-card-face__name product-sui__name">{specialRule.shortName}</span>
          <span className="sui-card-face__mark product-sui__mark">{specialRule.category === 'field' ? '场' : '岁'}</span>
          <span className="product-sui__type">{specialRule.categoryLabel}</span>
        </div>
      ) : (
        <img src={fallbackSrc} alt={label ?? assetKey} draggable={false} />
      )}
      {label ? <figcaption>{label}</figcaption> : null}
    </figure>
  );
}
