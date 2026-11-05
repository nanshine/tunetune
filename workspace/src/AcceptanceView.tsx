import { useState } from 'react';
import { LoaderCircle, Play, Sparkles, Star } from 'lucide-react';
import { acceptanceInputs, acceptanceModels, comparisonSamples, deliveryIds, document, experimentNumber, object, outcomeLabels, runState, runStateLabels, text } from './model';
import type { AcceptanceJob, Experiment, JsonObject, ModelPool, Snapshot } from './model';
import { RecordView, sampleLabel } from './RecordView';
import { Empty } from './Parts';

const fieldLabels: Record<string, string> = { title: '标题', text: '正文', body: '正文', content: '内容', question: '问题', message: '留言' };
// Only flat text inputs get a form; anything richer falls back to plain text.
export function inputTemplate(rows: JsonObject[]): string[] | null {
  const first = rows.find(row => row.input != null)?.input;
  if (!first || typeof first !== 'object' || Array.isArray(first)) return null;
  const keys = Object.entries(first as JsonObject).filter(([, value]) => typeof value === 'string').map(([key]) => key);
  return keys.length && keys.length === Object.keys(first as JsonObject).length && keys.length <= 6 ? keys : null;
}

function hasOutput(outputs: Record<string, unknown>, id: string): boolean {
  const value = outputs[id];
  return Object.hasOwn(outputs, id) && value != null && !(typeof value === 'string' && !value.trim()) && !(Array.isArray(value) && !value.length);
}

// New input follows the shape of existing inputs, so a model expecting {title, text} gets the same fields.
function TryPanel({ models, template, onTry }: { models: Experiment[]; template: string[] | null; onTry: (experiment: string, input: unknown) => Promise<{ output?: unknown; error?: string; log_tail?: string }> }) {
  const local = models.filter(item => item.targetKind === 'local' && item.invoke.length);
  const [model, setModel] = useState(local[0]?.id ?? '');
  const [input, setInput] = useState('');
  const [fields, setFields] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ output?: unknown; error?: string } | null>(null);
  if (!local.length) return null;
  async function run() {
    setBusy(true); setResult(null);
    try { setResult(await onTry(model, template ? Object.fromEntries(template.map(key => [key, fields[key] ?? ''])) : input)); }
    catch (cause) { setResult({ error: cause instanceof Error ? cause.message : '运行失败' }); }
    finally { setBusy(false); }
  }
  return <section className="try-panel" aria-label="试一段新内容">
    <div className="try-head"><Sparkles size={15} aria-hidden="true" /><h3>试一段新内容</h3>
      <select aria-label="选择模型" value={model} onChange={event => setModel(event.target.value)}>{local.map(item => <option key={item.id} value={item.id}>{experimentNumber(item.id)} · {item.title}</option>)}</select></div>
    {template ? template.map(key => <label key={key} className="try-field"><span>{fieldLabels[key] ?? key}</span><textarea value={fields[key] ?? ''} onChange={event => setFields({ ...fields, [key]: event.target.value })} rows={key === 'title' ? 1 : 4} /></label>)
      : <textarea value={input} onChange={event => setInput(event.target.value)} rows={4} placeholder="粘贴一段你想让模型处理的内容" aria-label="试运行输入" />}
    <div className="try-actions"><button className="primary" disabled={busy || !model || (template ? !Object.values(fields).some(value => value.trim()) : !input.trim())} onClick={() => void run()}>{busy ? <LoaderCircle size={14} className="spin" /> : <Play size={14} />}运行</button><span className="muted">只在本机运行，不会写入研究记录。</span></div>
    {result && <div className={`try-result ${result.error ? 'failed' : ''}`} role="status">{result.error ? <p>{result.error}</p> : <RecordView value={result.output} />}</div>}
  </section>;
}

// Loading keeps a model resident so trials answer at once; the person decides what stays loaded within the budget.
function LoadButton({ item, pool, onLoad, onUnload, onError }: { item: Experiment; pool: ModelPool | null | undefined; onLoad: (experiment: string) => Promise<unknown>; onUnload: (experiment: string) => Promise<unknown>; onError: (message: string) => void }) {
  const [busy, setBusy] = useState(false);
  if (!item.serve || item.targetKind !== 'local') return null;
  const loaded = pool?.items[item.id];
  const resident = loaded?.state === 'loaded' || loaded?.state === 'loading';
  async function act() {
    setBusy(true); onError('');
    try { await (resident ? onUnload(item.id) : onLoad(item.id)); }
    catch (cause) { onError(cause instanceof Error ? cause.message : '操作失败'); }
    finally { setBusy(false); }
  }
  return <button className="load-toggle" disabled={busy} onClick={() => void act()}>{resident ? (loaded.state === 'loading' ? '取消加载' : '卸载') : '加载'}</button>;
}

export function AcceptanceView({ files, job, pool, onRun, onTry, onLoad, onUnload }: {
  files: Snapshot['files']; job: AcceptanceJob | null | undefined; pool?: ModelPool | null;
  onRun: (experiments: string[]) => Promise<unknown>; onTry: (experiment: string, input: unknown) => Promise<{ output?: unknown; error?: string }>;
  onLoad?: (experiment: string) => Promise<unknown>; onUnload?: (experiment: string) => Promise<unknown>;
}) {
  const { primary, more } = acceptanceModels(files);
  const ordered = [...primary, ...more];
  const delivered = new Set(deliveryIds(files));
  const [chosen, setChosen] = useState<string[]>(() => (primary.length ? primary : more).slice(0, 3).map(item => item.id));
  const [showMore, setShowMore] = useState(() => !primary.length);
  const [index, setIndex] = useState(0);
  const [error, setError] = useState('');
  const version = text(document(files, 'project.json').current_evaluation);
  const selected = ordered.filter(item => chosen.includes(item.id));
  const rows = acceptanceInputs(files) ? comparisonSamples(files, '', '', version) : comparisonSamples(files, selected[0]?.id ?? '', selected[1]?.id ?? '', version);
  const active = rows[Math.min(index, Math.max(0, rows.length - 1))];
  const outputs = object(active?.outputs);
  const running = job?.state === 'running';
  const runnable = selected.filter(item => item.targetKind === 'local' && item.invoke.length).map(item => item.id);
  const pick = (item: Experiment) => <button key={item.id} aria-pressed={chosen.includes(item.id)} className={chosen.includes(item.id) ? 'active' : ''} onClick={() => setChosen(chosen.includes(item.id) ? chosen.filter(id => id !== item.id) : [...chosen, item.id].slice(-4))}>
    {delivered.has(item.id) && <Star size={12} aria-label="交付模型" />}<span className="node-number">{experimentNumber(item.id)}</span>{item.title}{item.analysis.outcome !== 'unknown' && !delivered.has(item.id) && <span className="muted">{outcomeLabels[item.analysis.outcome]}</span>}
  </button>;
  async function run() {
    setError('');
    try { await onRun(runnable); } catch (cause) { setError(cause instanceof Error ? cause.message : '无法开始运行'); }
  }
  if (!ordered.length) return <Empty icon={<Play size={20} />} title="还没有可验收的模型">实验跑出可用的模型后，可以在这里用你自己的内容看它们的输出。</Empty>;
  return <div className="acceptance">
    <div className="acceptance-bar">
      <div className="model-picks" role="group" aria-label="选择要对照的模型">{primary.map(pick)}
        {more.length > 0 && <button className="more-toggle" aria-expanded={showMore} onClick={() => setShowMore(!showMore)}>{showMore ? '收起' : `其他实验 ${more.length} 个`}</button>}
        {showMore && more.map(pick)}</div>
      {pool && ordered.some(item => item.serve) && <span className="memory-line muted">常驻内存 {pool.used_gb.toFixed(1)} / {pool.budget_gb.toFixed(1)} GB</span>}
      {acceptanceInputs(files) && <button className="primary" disabled={running || !runnable.length} onClick={() => void run()}>{running ? <LoaderCircle size={14} className="spin" /> : <Play size={14} />}{running ? '正在运行' : '用所选模型重新运行'}</button>}
    </div>
    {(job || error) && <p className={`job-line ${job?.state ?? 'failed'}`} role="status">{error || (job!.state === 'running' ? `正在让 ${job!.experiments.map(experimentNumber).join('、')} 处理全部输入…` : job!.state === 'succeeded' ? '运行完成，输出已更新。' : `有模型没跑完${job!.failed?.length ? `（${job!.failed.map(experimentNumber).join('、')}）` : ''}，保留了之前的输出。`)}</p>}
    <div className="acceptance-body">
      <nav className="input-list" aria-label="验收输入">{rows.length ? <ol>{rows.map((row, i) => <li key={text(row.sample_id, String(i))}><button className={row === active ? 'active' : ''} aria-current={row === active} onClick={() => setIndex(i)}>{sampleLabel(row, i)}</button></li>)}</ol>
        : <p className="muted">还没有验收输入。告诉 Agent 你想看哪些内容的结果，它们会出现在这里。</p>}</nav>
      <div className="acceptance-main">
        {active && <>
          <details className="input-preview" open={JSON.stringify(active.input).length < 600}><summary>输入：{sampleLabel(active, index)}</summary><div className="reading"><RecordView value={active.input} /></div></details>
          <div className="outputs" style={{ gridTemplateColumns: `repeat(${Math.max(selected.length, 1)}, minmax(0, 1fr))` }}>{selected.map(item => <section key={item.id} className="output-card">
            <h4><span className="node-number">{experimentNumber(item.id)}</span>{item.title}{onLoad && onUnload && <LoadButton item={item} pool={pool} onLoad={onLoad} onUnload={onUnload} onError={setError} />}</h4>
            <p className={`run-state ${runState(item, job, pool)}`} title={pool?.items[item.id]?.error}>{runStateLabels[runState(item, job, pool)]}{pool?.items[item.id] && pool.items[item.id].state !== 'failed' && ` · 约 ${pool.items[item.id].memory_gb.toFixed(1)} GB`}</p>
            {hasOutput(outputs, item.id) ? <RecordView value={outputs[item.id]} /> : <p className="muted">还没有这个输入的输出{acceptanceInputs(files) && ['runnable', 'loaded'].includes(runState(item, job, pool)) ? '，点上方按钮运行。' : '。'}</p>}
          </section>)}</div>
        </>}
        <TryPanel models={selected.length ? selected : ordered} template={inputTemplate(rows)} onTry={onTry} />
      </div>
    </div>
  </div>;
}
