import type { PauseState } from '../../types';

type PausePanelProps = {
  pause: PauseState;
  isHost: boolean;
  onContinue: () => void;
  onAbort: () => void;
};

const pauseStepLabels: Record<string, string> = {
  TURN_MAIN: '普通回合',
  NIAN_TURN_END_DISCARD: '年牌弃牌步骤',
  NIAN_CLAIM_WINDOW: '年牌吃碰杠响应',
  HAS_SUI_CHALLENGE: '岁牌质疑步骤',
  WILD_DRAW_FOUR_CHALLENGE: '+4 质疑步骤',
  SUI_PLAYER_RESPONSE: '岁牌响应步骤',
};

function pauseStepLabel(stepKind: string): string {
  return pauseStepLabels[stepKind] ?? '当前必选步骤';
}

export function PausePanel({ pause, isHost, onContinue, onAbort }: PausePanelProps) {
  return (
    <section className="pause-panel" role="alert" aria-label="牌局已暂停">
      <div>
        <strong>牌局已暂停</strong>
        <p>必选操作超时，{pauseStepLabel(pause.step_kind)}保持原状，未自动代选或推进。</p>
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
