import { useState } from 'react';
import { Lightbulb, ListChecks } from 'lucide-react';
import { experimentNumber, experiments, plan, planStateLabels } from './model';
import type { Snapshot } from './model';
import { Empty, ResponseBar, Section } from './Parts';

export function PlanView({ files, waiting = null, onRespond, onFocusExperiment }: {
  files: Snapshot['files']; waiting?: string | null; onRespond?: (decision: string, note: string, sha: string) => Promise<unknown>; onFocusExperiment: (id: string) => void;
}) {
  const { rounds, ideas } = plan(files);
  const [selection, setSelection] = useState<number | null>(null);
  const existing = new Set(experiments(files).map(item => item.id));
  if (!rounds.length) return <Empty icon={<ListChecks size={20} />} title="还没有实验方案">基线测完后，Agent 会在这里写下第一轮要做的实验。</Empty>;
  const active = rounds.find(round => round.round === selection) ?? rounds.at(-1)!;
  return <div className="plan">
    {onRespond && <ResponseBar files={files} kind="plan" waiting={waiting} prompt="这是接下来要做的一轮实验。可以按这个方案继续，也可以提出调整。" approve="按这个方案继续" decisions={{ approve: 'continue', revise: 'revise' }} onSubmit={onRespond} />}
    {rounds.length > 1 && <div className="segmented" role="tablist" aria-label="实验轮次">{rounds.map(round => <button key={round.round} role="tab" aria-selected={round.round === active.round} className={round.round === active.round ? 'active' : ''} onClick={() => setSelection(round.round)}>第 {round.round} 轮</button>)}</div>}
    <div className="lead">
      <p>{active.goal}</p>
      {active.budget && <p className="lead-meta">预算：{active.budget}</p>}
    </div>
    <ol className="plan-items">{active.items.map(item => <li key={item.id} className={`plan-item state-${item.state}`}>
      <button className="plan-item-head" disabled={!existing.has(item.id) && item.state !== 'planned' && item.state !== 'running'} onClick={() => onFocusExperiment(item.id)} aria-label={`在画布上查看 ${item.title}`}>
        <span className="node-number">{experimentNumber(item.id)}</span><span className="plan-item-title">{item.title}</span><span className={`badge plan-${item.state}`}>{planStateLabels[item.state]}</span>
      </button>
      {item.question && <p>{item.question}</p>}
      {item.expected && <p className="plan-expected"><span>会改变下一步的结果</span>{item.expected}</p>}
      <div className="chips">{item.intervention && <span className="chip">{item.intervention}</span>}{item.comparator && <span className="chip">对比 {experimentNumber(item.comparator)}</span>}{item.cost && <span className="chip">成本 {item.cost}</span>}</div>
      {item.note && <p className="muted">{item.note}</p>}
    </li>)}</ol>
    {active.conclusion && <Section title="这一轮的结论"><p className="prose">{active.conclusion}</p></Section>}
    {!!ideas.length && <Section title="暂缓的想法" icon={<Lightbulb size={15} />}><ul className="considered">{ideas.map((idea, index) => <li key={index}><div><strong>{idea.title}</strong><p>{idea.reason}</p></div></li>)}</ul></Section>}
  </div>;
}
