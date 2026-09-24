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

export function CardView({ assetKey, label, variant = 'table', faceDown = false, selected = false, legal, disabled = false }: CardViewProps) {
  const src = (manifest as Record<string, string>)[faceDown ? 'card_back' : assetKey] ?? (manifest as Record<string, string>).card_back;
  const stateClass = [selected ? 'is-selected' : '', legal === true ? 'is-legal' : '', legal === false ? 'is-illegal' : '', disabled ? 'is-disabled' : '']
    .filter(Boolean)
    .join(' ');
  return (
    <figure className={`${classByVariant[variant]} ${stateClass}`} title={label ?? assetKey}>
      <img src={src} alt={label ?? assetKey} />
      {label ? <figcaption>{label}</figcaption> : null}
    </figure>
  );
}

