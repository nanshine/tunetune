import { useState } from 'react';
import { Check, LoaderCircle, Play, Sparkles, Star, ThumbsDown, ThumbsUp } from 'lucide-react';
import { acceptanceInputs, acceptanceModels, comparisonSamples, currentResponse, array, deliveryIds, document, experimentNumber, object, outcomeLabels, runState, runStateLabels, text } from './model';
import type { AcceptanceJob, Experiment, JsonObject, ModelPool, Snapshot } from './model';
import { RecordView, sampleLabel } from './RecordView';
import { Empty } from './Parts';
import type { AcceptanceItem } from './useWorkspace';
import { labels, list, t } from './i18n';

const fieldLabels: Record<string, string> = labels({ title: '标题', text: '正文', body: '正文', content: '内容', question: '问题', message: '留言' });
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
    catch (cause) { setResult({ error: cause instanceof Error ? cause.message : t('运行失败') }); }
    finally { setBusy(false); }
  }
  return <section className="try-panel" aria-label={t('试一段新内容')}>
    <div className="try-head"><Sparkles size={15} aria-hidden="true" /><h3>{t('试一段新内容')}</h3>
      <select aria-label={t('选择模型')} value={model} onChange={event => setModel(event.target.value)}>{local.map(item => <option key={item.id} value={item.id}>{experimentNumber(item.id)} · {item.title}</option>)}</select></div>
    {template ? template.map(key => <label key={key} className="try-field"><span>{fieldLabels[key] ?? key}</span><textarea value={fields[key] ?? ''} onChange={event => setFields({ ...fields, [key]: event.target.value })} rows={key === 'title' ? 1 : 4} /></label>)
      : <textarea value={input} onChange={event => setInput(event.target.value)} rows={4} placeholder={t('粘贴一段你想让模型处理的内容')} aria-label={t('试运行输入')} />}
    <div className="try-actions"><button className="primary" disabled={busy || !model || (template ? !Object.values(fields).some(value => value.trim()) : !input.trim())} onClick={() => void run()}>{busy ? <LoaderCircle size={14} className="spin" /> : <Play size={14} />}{t('运行')}</button><span className="muted">{t('只在本机运行，不会写入研究记录。')}</span></div>
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
    catch (cause) { onError(cause instanceof Error ? cause.message : t('操作失败')); }
    finally { setBusy(false); }
  }
  return <button className="load-toggle" disabled={busy} onClick={() => void act()}>{resident ? (loaded.state === 'loading' ? t('取消加载') : t('卸载')) : t('加载')}</button>;
}

type Judgment = { verdict: AcceptanceItem['verdict']; note?: string };
const judgmentKey = (sample: string, experiment: string) => `${sample}\u0000${experiment}`;

// The person's verdict on an output they read; outputs judged bad become cases for the next evaluation.
function Verdict({ judgment, onChange }: { judgment: Judgment | undefined; onChange: (value: Judgment | null) => void }) {
  return <div className="output-verdict">
    <div role="group" aria-label={t('这个输出好不好')}>
      <button className={judgment?.verdict === 'good' ? 'active good' : ''} aria-pressed={judgment?.verdict === 'good'} onClick={() => onChange(judgment?.verdict === 'good' ? null : { verdict: 'good' })}><ThumbsUp size={13} />{t('好')}</button>
      <button className={judgment?.verdict === 'bad' ? 'active warn' : ''} aria-pressed={judgment?.verdict === 'bad'} onClick={() => onChange(judgment?.verdict === 'bad' ? null : { verdict: 'bad', note: judgment?.note })}><ThumbsDown size={13} />{t('不好')}</button>
    </div>
    {judgment?.verdict === 'bad' && <input aria-label={t('哪里不好')} placeholder={t('哪里不对？应该是什么样？')} value={judgment.note ?? ''} onChange={event => onChange({ verdict: 'bad', note: event.target.value })} />}
  </div>;
}

export function AcceptanceView({ files, job, pool, onRun, onTry, onLoad, onUnload, onFeedback }: {
  files: Snapshot['files']; job: AcceptanceJob | null | undefined; pool?: ModelPool | null;
  onRun: (experiments: string[]) => Promise<unknown>; onTry: (experiment: string, input: unknown) => Promise<{ output?: unknown; error?: string }>;
  onLoad?: (experiment: string) => Promise<unknown>; onUnload?: (experiment: string) => Promise<unknown>;
  onFeedback?: (items: AcceptanceItem[], sha: string) => Promise<unknown>;
}) {
  const { primary, more } = acceptanceModels(files);
  const ordered = [...primary, ...more];
  const delivered = new Set(deliveryIds(files));
  const [chosen, setChosen] = useState<string[]>(() => (primary.length ? primary : more).slice(0, 3).map(item => item.id));
  const [showMore, setShowMore] = useState(() => !primary.length);
  const [index, setIndex] = useState(0);
  const [error, setError] = useState('');
  const [judgments, setJudgments] = useState<Record<string, Judgment>>({});
  const [sending, setSending] = useState(false);
  const shown = files['comparison/outputs.jsonl'];
  const answered = currentResponse(files, 'acceptance');
  const version = text(document(files, 'project.json').current_evaluation);
  const selected = ordered.filter(item => chosen.includes(item.id));
  const rows = acceptanceInputs(files) ? comparisonSamples(files, '', '', version) : comparisonSamples(files, selected[0]?.id ?? '', selected[1]?.id ?? '', version);
  const active = rows[Math.min(index, Math.max(0, rows.length - 1))];
  const outputs = object(active?.outputs);
  const running = job?.state === 'running';
  const runnable = selected.filter(item => item.targetKind === 'local' && item.invoke.length).map(item => item.id);
  const pick = (item: Experiment) => <button key={item.id} aria-pressed={chosen.includes(item.id)} className={chosen.includes(item.id) ? 'active' : ''} onClick={() => setChosen(chosen.includes(item.id) ? chosen.filter(id => id !== item.id) : [...chosen, item.id].slice(-4))}>
    {delivered.has(item.id) && <Star size={12} aria-label={t('交付模型')} />}<span className="node-number">{experimentNumber(item.id)}</span>{item.title}{item.analysis.outcome !== 'unknown' && !delivered.has(item.id) && <span className="muted">{outcomeLabels[item.analysis.outcome]}</span>}
  </button>;
  async function run() {
    setError('');
    try { await onRun(runnable); } catch (cause) { setError(cause instanceof Error ? cause.message : t('无法开始运行')); }
  }
  function judge(sample: string, experiment: string, value: Judgment | null) {
    setJudgments(previous => {
      const next = { ...previous };
      if (value) next[judgmentKey(sample, experiment)] = value; else delete next[judgmentKey(sample, experiment)];
      return next;
    });
  }
  async function sendFeedback() {
    if (!onFeedback || !shown) return;
    setSending(true); setError('');
    const items = Object.entries(judgments).map(([key, value]): AcceptanceItem => {
      const [sample_id, experiment_id] = key.split('\u0000');
      const note = value.note?.trim();
      return { sample_id, experiment_id, verdict: value.verdict, ...(note ? { note } : {}) };
    });
    try { await onFeedback(items, shown.sha256); setJudgments({}); }
    catch (cause) { setError(cause instanceof Error ? cause.message : t('提交失败，请重试。')); }
    finally { setSending(false); }
  }
  const judged = Object.keys(judgments).length;
  if (!ordered.length) return <Empty icon={<Play size={20} />} title={t('还没有可验收的模型')}>{t('实验跑出可用的模型后，可以在这里用你自己的内容看它们的输出。')}</Empty>;
  return <div className="acceptance">
    <div className="acceptance-bar">
      <div className="model-picks" role="group" aria-label={t('选择要对照的模型')}>{primary.map(pick)}
        {more.length > 0 && <button className="more-toggle" aria-expanded={showMore} onClick={() => setShowMore(!showMore)}>{showMore ? t('收起') : t('其他实验 {count} 个', { count: more.length })}</button>}
        {showMore && more.map(pick)}</div>
      {pool && ordered.some(item => item.serve) && <span className="memory-line muted">{t('常驻内存 {used} / {budget} GB', { used: pool.used_gb.toFixed(1), budget: pool.budget_gb.toFixed(1) })}</span>}
      {acceptanceInputs(files) && <button className="primary" disabled={running || !runnable.length} onClick={() => void run()}>{running ? <LoaderCircle size={14} className="spin" /> : <Play size={14} />}{running ? t('正在运行') : t('用所选模型重新运行')}</button>}
    </div>
    {(job || error) && <p className={`job-line ${job?.state ?? 'failed'}`} role="status">{error || (job!.state === 'running' ? t('正在让 {models} 处理全部输入…', { models: list(job!.experiments.map(experimentNumber)) }) : job!.state === 'succeeded' ? t('运行完成，输出已更新。') : job!.failed?.length ? t('有模型没跑完（{models}），保留了之前的输出。', { models: list(job!.failed.map(experimentNumber)) }) : t('有模型没跑完，保留了之前的输出。'))}</p>}
    <div className="acceptance-body">
      <nav className="input-list" aria-label={t('验收输入')}>{rows.length ? <ol>{rows.map((row, i) => <li key={text(row.sample_id, String(i))}><button className={row === active ? 'active' : ''} aria-current={row === active} onClick={() => setIndex(i)}>{sampleLabel(row, i)}</button></li>)}</ol>
        : <p className="muted">{t('还没有验收输入。告诉 Agent 你想看哪些内容的结果，它们会出现在这里。')}</p>}</nav>
      <div className="acceptance-main">
        {active && <>
          <details className="input-preview" open={JSON.stringify(active.input).length < 600}><summary>{t('输入：')}{sampleLabel(active, index)}</summary><div className="reading"><RecordView value={active.input} /></div></details>
          <div className="outputs" style={{ gridTemplateColumns: `repeat(${Math.max(selected.length, 1)}, minmax(0, 1fr))` }}>{selected.map(item => <section key={item.id} className="output-card">
            <h4><span className="node-number">{experimentNumber(item.id)}</span>{item.title}{onLoad && onUnload && <LoadButton item={item} pool={pool} onLoad={onLoad} onUnload={onUnload} onError={setError} />}</h4>
            <p className={`run-state ${runState(item, job, pool)}`} title={pool?.items[item.id]?.error}>{runStateLabels[runState(item, job, pool)]}{pool?.items[item.id] && pool.items[item.id].state !== 'failed' && t(' · 约 {gb} GB', { gb: pool.items[item.id].memory_gb.toFixed(1) })}</p>
            {hasOutput(outputs, item.id) ? <RecordView value={outputs[item.id]} /> : <p className="muted">{acceptanceInputs(files) && ['runnable', 'loaded'].includes(runState(item, job, pool)) ? t('还没有这个输入的输出，点上方按钮运行。') : t('还没有这个输入的输出。')}</p>}
            {shown && onFeedback && hasOutput(outputs, item.id) && <Verdict judgment={judgments[judgmentKey(text(active.sample_id), item.id)]} onChange={value => judge(text(active.sample_id), item.id, value)} />}
          </section>)}</div>
          {shown && onFeedback && (judged > 0 || answered) && <div className="feedback-bar" role="status">
            {judged > 0 ? <><span>{t('已评价 {count} 个输出。觉得不好的会补进下一版评测，你会在审阅里再看到它们。', { count: judged })}</span>
              <button className="primary" disabled={sending} onClick={() => void sendFeedback()}>{t('提交验收意见')}</button></>
              : <span><Check size={14} aria-hidden="true" />{t('这批输出的意见已提交（{count} 条）。回到对话告诉 Agent。', { count: array(answered!.items).length })}</span>}
          </div>}
        </>}
        <TryPanel models={selected.length ? selected : ordered} template={inputTemplate(rows)} onTry={onTry} />
      </div>
    </div>
  </div>;
}
