import { useEffect, useRef, useState } from 'react';
import { Box, Columns2, X } from 'lucide-react';
import { array, object, preferredEvaluation, recentEvaluations, statusLabel } from './model';
import type { EvaluationRun, Experiment, Snapshot } from './model';
import { OutcomeBadge, StateIcon } from './Lineage';
import { SamplesView } from './EvaluationView';

const parameterLabels: Record<string, string> = { learning_rate: '学习率', batch_size: '批量大小', epochs: '训练轮数', num_train_epochs: '训练轮数', rank: '适配秩', alpha: 'Alpha', dropout: '丢弃率', max_length: '最大长度', seed: '随机种子', temperature: '生成温度' };

export function ExperimentDetails({ experiment, results, files, currentVersion, delivered, onClose, onCompare }: {
  experiment: Experiment; results: EvaluationRun[]; files: Snapshot['files']; currentVersion: string; delivered: boolean; onClose: () => void; onCompare: () => void;
}) {
  const [selection, setSelection] = useState('');
  const heading = useRef<HTMLHeadingElement>(null);
  const experimentResults = recentEvaluations(results.filter(result => result.experimentId === experiment.id));
  const versions = [...new Set(experimentResults.map(result => result.version))];
  const version = versions.includes(selection) ? selection : versions.includes(currentVersion) ? currentVersion : versions[0] ?? '';
  const active = preferredEvaluation(experimentResults, version);
  const outputFile = active ? files[active.path.replace('/config.json', '/outputs.jsonl')] : undefined;
  const parameters = Object.entries(experiment.parameters).filter(([key, value]) => !/(?:^|_)(?:id|path|sha256|hash|command|execution|inputs|environment)(?:_|$)/.test(key) && (typeof value === 'number' && Number.isFinite(value) || typeof value === 'boolean' || typeof value === 'string' && value.length <= 120)).slice(0, 4);
  useEffect(() => { heading.current?.focus(); }, []);
  return <aside className="drawer right-drawer" aria-labelledby="experiment-detail-title">
    <div className="drawer-header"><div className="experiment-title"><span className="node-icon"><Box size={19} aria-hidden="true" /></span><div><h2 ref={heading} tabIndex={-1} id="experiment-detail-title">{experiment.title}</h2></div></div><button className="icon-button" aria-label="关闭实验详情" onClick={onClose}><X size={19} /></button></div>
    <div className="drawer-content">
      <section className="detail-section"><h3>为什么做</h3><p className="brief-text">{experiment.hypothesis || '尚未记录实验假设。'}</p></section>
      <section className="detail-section"><h3>怎么做</h3><p className="brief-text">{[experiment.modelName, experiment.method, experiment.framework].filter(Boolean).join(' · ') || '尚未记录模型和方法。'}</p>{!!parameters.length && <dl className="parameter-list">{parameters.map(([key, value]) => <div key={key}><dt>{Object.hasOwn(parameterLabels, key) ? parameterLabels[key] : key.replaceAll('_', ' ')}</dt><dd>{typeof value === 'boolean' ? value ? '是' : '否' : String(value)}</dd></div>)}</dl>}</section>
      <section className="detail-section"><h3>结果</h3><div className={`detail-status status ${experiment.state}`}><StateIcon state={experiment.state} />执行 · {statusLabel(experiment.state)}</div>{experiment.state === 'running' && <p className="muted">文件记录不代表进程当前仍在运行。</p>}{active ? <>
        <label>评测版本<select value={version} onChange={event => setSelection(event.target.value)}>{versions.map(item => <option key={item} value={item}>{item || '未指定版本'}{item === currentVersion ? ' · 当前' : ''}</option>)}</select></label>
        <div className={`detail-status status ${active.state}`}><StateIcon state={active.state} />评测 · {statusLabel(active.state)}</div>
        {active.version !== currentVersion && <p className="notice">此结果来自其他评测版本，不与当前版本混排。</p>}
        <div className="detail-metrics">{Object.entries(active.metrics).map(([key, value]) => <div key={key}><span>{Object.hasOwn(active.metricLabels, key) ? active.metricLabels[key] : key}</span><strong>{value.toLocaleString()}</strong></div>)}</div>
        {!Object.keys(active.metrics).length && <p className="muted">此评测尚无指标结果。</p>}
        <SamplesView key={active.path} rows={outputFile ? array(outputFile.content).map(object) : null} outputs metricLabels={active.metricLabels} />
      </> : <p className="muted">尚无评测记录。执行成功不等于效果已经验证。</p>}</section>
      <section className="detail-section"><h3>结论 {delivered && <span className="badge">已交付</span>}</h3><OutcomeBadge analysis={experiment.analysis} /><p className="brief-text">{experiment.analysis.summary || '尚无分析结论；执行成功不等于效果已验证。'}</p>{delivered && <button onClick={onCompare}><Columns2 size={16} />模型对比</button>}</section>
    </div>
  </aside>;
}
