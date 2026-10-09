import { useState } from 'react';
import { ExternalLink, X } from 'lucide-react';
import { generalRules, specialRules, type SpecialRule } from '../../data/rules';
import { CardView } from '../CardView';

export type RulesGalleryProps = {
  open: boolean;
  onClose: () => void;
};

export function RulesGallery({ open, onClose }: RulesGalleryProps) {
  const [originalRule, setOriginalRule] = useState<SpecialRule | null>(null);
  if (!open) return null;

  return (
    <aside className="product-rules" aria-label="岁牌规则图鉴" data-testid="rules-gallery">
      <header className="product-rules__head">
        <div><p className="product-kicker">规则图鉴</p><h2>岁牌与通用规则</h2></div>
        <button type="button" aria-label="关闭规则图鉴" onClick={onClose}><X size={20} /></button>
      </header>

      <div className="product-rules__scroll">
        <section className="product-rules__general" aria-label="通用规则">
          {generalRules.map((rule) => (
            <details key={rule.id} open={rule.id === 'has-sui'}>
              <summary><strong>{rule.title}</strong><span>{rule.summary}</span></summary>
              <ul>{rule.details.map((detail) => <li key={detail}>{detail}</li>)}</ul>
            </details>
          ))}
        </section>

        <section className="product-rules__cards" aria-label="逐张岁牌规则">
          {specialRules.map((rule) => (
            <article key={rule.assetKey} id={`rule-${rule.assetKey}`}>
              <div className="product-rules__card-column">
                <CardView assetKey={rule.assetKey} variant="rule" />
                <button type="button" onClick={() => setOriginalRule(rule)}><ExternalLink size={14} />查看原图</button>
              </div>
              <div className="product-rules__content">
                <header><div><strong>{rule.name}</strong><span>{rule.categoryLabel}</span></div><small>{rule.timing}</small></header>
                <p>{rule.summary}</p>
                <ol>{rule.steps.map((step) => <li key={step}>{step}</li>)}</ol>
                {rule.notes.length ? <ul className="product-rules__notes">{rule.notes.map((note) => <li key={note}>{note}</li>)}</ul> : null}
              </div>
            </article>
          ))}
        </section>
      </div>

      {originalRule ? (
        <div className="product-original" role="dialog" aria-modal="true" aria-label={`${originalRule.name}完整原图`}>
          <div>
            <header><strong>{originalRule.name} · 完整原图</strong><button type="button" aria-label="关闭原图" onClick={() => setOriginalRule(null)}><X size={20} /></button></header>
            <img src={originalRule.originalImage} alt={`${originalRule.name}卡面与原始规则说明`} />
          </div>
        </div>
      ) : null}
    </aside>
  );
}
