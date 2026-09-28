import type { PauseState } from '../../types';

type PausePanelProps = {
  pause: PauseState;
  isHost: boolean;
  onContinue: () => void;
  onAbort: () => void;
};

export function PausePanel({ pause, isHost, onContinue, onAbort }: PausePanelProps) {
  return (
    <section className="pause-panel" role="alert" aria-label="牌局已暂停">
      <div>
        <strong>牌局已暂停</strong>
        <p>必选操作超时，步骤“{pause.step_kind}”保持原状，未自动代选或推进。</p>
      </div>
      {isHost ? (
        <div className="pause-panel__actions">
          <button className="primary" type="button" onClick={onContinue}>继续等待并重置时限</button>
          <button className="danger" type="button" onClick={onAbort}>结束本局</button>
        </div>
      ) : <span>等待房主选择继续等待或结束本局。</span>}
    </section>
  );
}
