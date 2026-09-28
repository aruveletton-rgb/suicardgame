import manifest from '../data/cardManifest.json';

type CardViewProps = {
  assetKey: string;
  label?: string;
  variant?: 'thumbnail' | 'hand' | 'table' | 'preview' | 'rule';
  faceDown?: boolean;
  selected?: boolean;
  legal?: boolean;
  disabled?: boolean;
};

const classByVariant = {
  thumbnail: 'card card--thumbnail',
  hand: 'card card--hand',
  table: 'card card--table',
  preview: 'card card--preview',
  rule: 'card card--rule',
};

const SPECIAL_NAMES: Record<string, string> = {
  sui_wang: '望',
  sui_ji: '绩',
  sui_yu: '余',
  sui_yi: '易',
  sui_zuole: '左乐',
  sui_xi: '夕',
  sui_nian: '年',
  sui_sui_xiang: '岁相',
  sui_shu: '黍',
  sui_chongyue: '重岳',
  sui_ling: '令',
  sui_fuzhou: '符咒',
  field_cannot: '坎诺特',
};

function unoLabel(assetKey: string): { color: string; symbol: string } | null {
  if (!assetKey.startsWith('uno_')) return null;
  if (assetKey === 'uno_wild') return { color: 'wild', symbol: '★' };
  if (assetKey === 'uno_wild_draw_four') return { color: 'wild', symbol: '+4' };
  const [, color, ...parts] = assetKey.split('_');
  const kind = parts.join('_');
  const symbols: Record<string, string> = {
    skip: '⊘',
    reverse: '↺',
    draw_two: '+2',
    wild: '★',
    wild_draw_four: '+4',
  };
  return { color, symbol: symbols[kind] ?? kind };
}

export function CardView({ assetKey, label, variant = 'table', faceDown = false, selected = false, legal, disabled = false }: CardViewProps) {
  const src = (manifest as Record<string, string>)[faceDown ? 'card_back' : assetKey] ?? (manifest as Record<string, string>).card_back;
  const uno = !faceDown ? unoLabel(assetKey) : null;
  const specialName = SPECIAL_NAMES[assetKey];
  const stateClass = [selected ? 'is-selected' : '', legal === true ? 'is-legal' : '', legal === false ? 'is-illegal' : '', disabled ? 'is-disabled' : '']
    .filter(Boolean)
    .join(' ');
  return (
    <figure className={`${classByVariant[variant]} ${stateClass}`} title={label ?? assetKey}>
      {uno ? (
        <div className={`uno-card-face uno-card-face--${uno.color}`} role="img" aria-label={`${uno.color} ${uno.symbol}`}>
          <span className="uno-card-corner">{uno.symbol}</span>
          <strong>{uno.symbol}</strong>
          <span className="uno-card-corner uno-card-corner--bottom">{uno.symbol}</span>
        </div>
      ) : specialName && !faceDown ? (
        <div className="sui-card-face" role="img" aria-label={specialName}>
          <img src={src} alt="" />
          <span className="sui-card-face__name">{specialName}</span>
          <span className="sui-card-face__mark">岁</span>
        </div>
      ) : (
        <img src={src} alt={label ?? assetKey} />
      )}
      {label ? <figcaption>{label}</figcaption> : null}
    </figure>
  );
}

