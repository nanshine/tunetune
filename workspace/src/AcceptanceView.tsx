import { useEffect, useState } from 'react';
import { Check, Eraser, FileText, LoaderCircle, PencilLine, Play, Plus, Sparkles, Star, ThumbsDown, ThumbsUp, Upload } from 'lucide-react';
import { acceptanceInputs, acceptanceModels, combineComparison, comparisonPlan, currentResponse, array, deliveryIds, document, experimentNumber, object, outcomeLabels, runState, runStateLabels, text } from './model';
import { PAGE_SIZE, rowSource, sourceTotal, targetSha, usePaged, useRowPage, useRowsById } from './rows';
import type { AcceptanceJob, Experiment, JsonObject, ModelPool, Snapshot } from './model';
import { RecordView, mediaUrl, prefetchImages, sampleLabel } from './RecordView';
import { Empty } from './Parts';
import type { AcceptanceItem } from './useWorkspace';
import { labels, list, t } from './i18n';
import { ATTACHMENT_FORMATS, ATTACHMENT_LIMIT_MB, attachmentExtension, changeLabels, dropLabels, formatLabels, missingLabels, pickLabels } from './attachments';
import type { AttachmentKind } from './attachments';

const fieldLabels: Record<string, string> = labels({ title: '标题', text: '正文', body: '正文', content: '内容', question: '问题', message: '留言', image: '图片', audio: '音频', video: '视频', file: '文件' });
type TryResult = { output?: unknown; error?: string; log_tail?: string };
export type UploadAttachment = (file: File, kind: AttachmentKind) => Promise<JsonObject>;

function isAttachment(value: unknown): value is JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value) && ['image', 'audio', 'video', 'file'].includes(text(object(value).type)) && typeof object(value).path === 'string';
}
// A new input in the shape of the acceptance inputs: text emptied, choices and numbers kept, pictures still to choose.
export function blankInput(value: unknown): unknown {
  if (typeof value === 'string') return '';
  if (isAttachment(value)) return { type: value.type, path: '' };
  if (Array.isArray(value)) return value.every(item => typeof item === 'string') ? [] : value;
  if (value !== null && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, blankInput(item)]));
  return value;
}
// What still keeps a trial from running: a picture to choose or no text at all.
export function trialGap(value: unknown): string | null {
  const pending: string[] = [];
  let filled = false;
  const visit = (item: unknown) => {
    if (typeof item === 'string') { if (item.trim()) filled = true; return; }
    if (isAttachment(item)) { if (text(item.path)) filled = true; else pending.push(text(item.type)); return; }
    if (Array.isArray(item)) { item.forEach(visit); return; }
    if (item !== null && typeof item === 'object') { Object.values(item).forEach(visit); return; }
    if (item !== null && item !== undefined) filled = true;
  };
  visit(value);
  const kind = (['image', 'audio', 'video', 'file'] as const).find(item => pending.includes(item));
  if (kind) return missingLabels[kind];
  return filled ? null : t('先填写内容');
}

type Preview = { url: string; name: string };
// An attachment field: the chosen file is copied into the project's scratch area so the model reads it like any input.
function AttachmentPick({ value, preview, onUpload, onPicked }: { value: JsonObject; preview: Preview | undefined; onUpload?: UploadAttachment; onPicked: (value: JsonObject, preview: Preview) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const kind = text(value.type) as AttachmentKind;
  const path = text(value.path);
  const shown = preview?.url ?? mediaUrl(path);
  const name = preview?.name ?? path.split('/').at(-1) ?? '';
  async function pick(file: File | undefined) {
    if (!file || !onUpload) return;
    if (!attachmentExtension(file, kind)) { setError(formatLabels[kind]); return; }
    if (file.size > ATTACHMENT_LIMIT_MB[kind] * 1024 * 1024) { setError(t('这个文件不能超过 {mb} MB。', { mb: ATTACHMENT_LIMIT_MB[kind] })); return; }
    setBusy(true); setError('');
    try { onPicked(await onUpload(file, kind), { url: URL.createObjectURL(file), name: file.name }); }
    catch (cause) { setError(cause instanceof Error ? cause.message : t('上传失败')); }
    finally { setBusy(false); }
  }
  const accept = kind === 'file' ? undefined : ATTACHMENT_FORMATS[kind].map(ext => `.${ext}`).join(',');
  return <div className={`picture-pick ${path ? '' : 'empty'}`} onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); void pick(event.dataTransfer.files[0]); }}>
    {!path ? <span className="muted"><Upload size={18} aria-hidden="true" />{dropLabels[kind]}</span>
      : kind === 'image' && shown ? <img src={shown} alt={name} />
      : kind === 'audio' && shown ? <audio key={shown} controls src={shown} aria-label={name} />
      : kind === 'video' && shown ? <video key={shown} controls src={shown} aria-label={name} />
      : <span className="attachment-name"><FileText size={16} aria-hidden="true" />{name}</span>}
    {onUpload ? <label className="button-like">{busy ? <LoaderCircle size={14} className="spin" /> : <Upload size={14} />}{path ? changeLabels[kind] : pickLabels[kind]}
      <input type="file" accept={accept} className="sr-only" disabled={busy} onChange={event => { void pick(event.target.files?.[0]); event.target.value = ''; }} /></label>
      : <span className="muted">{t('这里不能上传文件')}</span>}
    {path && kind !== 'image' && kind !== 'file' && <span className="muted attachment-caption">{name}</span>}
    {error && <p className="error-text" role="alert">{error}</p>}
  </div>;
}

// Nested lists and records are edited as JSON; the last valid value is the one that runs.
function JsonField({ value, onChange, label }: { value: unknown; onChange: (value: unknown) => void; label: string }) {
  const [draft, setDraft] = useState(() => JSON.stringify(value, null, 2));
  const [invalid, setInvalid] = useState(false);
  return <><textarea className="mono-input" aria-label={label} value={draft} rows={Math.min(8, draft.split('\n').length + 1)} onChange={event => {
    setDraft(event.target.value);
    try { onChange(JSON.parse(event.target.value)); setInvalid(false); } catch { setInvalid(true); }
  }} />{invalid && <span className="error-text">{t('JSON 格式不对，运行时用上一次有效的内容。')}</span>}</>;
}

function FieldEditor({ name, value, onChange, previews, onPreview, onUpload }: { name: string; value: unknown; onChange: (value: unknown) => void; previews: Record<string, Preview>; onPreview: (path: string, preview: Preview) => void; onUpload?: UploadAttachment }) {
  const label = Object.hasOwn(fieldLabels, name) ? fieldLabels[name] : name;
  if (typeof value === 'string') return <textarea aria-label={label} value={value} onChange={event => onChange(event.target.value)} rows={value.length > 60 || value.includes('\n') || /text|body|content|message|question|prompt/i.test(name) ? 4 : 1} />;
  if (typeof value === 'number') return <input type="number" aria-label={label} value={Number.isFinite(value) ? value : 0} onChange={event => onChange(event.target.value === '' ? 0 : Number(event.target.value))} />;
  if (typeof value === 'boolean') return <label className="check-field"><input type="checkbox" checked={value} onChange={event => onChange(event.target.checked)} />{value ? t('是') : t('否')}</label>;
  if (isAttachment(value)) return <AttachmentPick value={value} preview={previews[text(value.path)]} onUpload={onUpload} onPicked={(next, preview) => { onPreview(text(next.path), preview); onChange(next); }} />;
  return <JsonField value={value} onChange={onChange} label={label} />;
}

// The trial input, edited field by field in the shape the models already receive.
function InputEditor({ value, onChange, onUpload }: { value: unknown; onChange: (value: unknown) => void; onUpload?: UploadAttachment }) {
  const [previews, setPreviews] = useState<Record<string, Preview>>({});
  const onPreview = (path: string, preview: Preview) => setPreviews(previous => ({ ...previous, [path]: preview }));
  if (value !== null && typeof value === 'object' && !Array.isArray(value) && !isAttachment(value)) {
    return <div className="try-fields">{Object.entries(value).map(([key, item]) => <div key={key} className="try-field"><span>{Object.hasOwn(fieldLabels, key) ? fieldLabels[key] : key}</span>
      <FieldEditor name={key} value={item} previews={previews} onPreview={onPreview} onUpload={onUpload} onChange={next => onChange({ ...(value as JsonObject), [key]: next })} /></div>)}</div>;
  }
  if (typeof value === 'string') return <textarea value={value} onChange={event => onChange(event.target.value)} rows={5} placeholder={t('粘贴一段你想让模型处理的内容')} aria-label={t('试运行输入')} />;
  return <FieldEditor name="input" value={value} previews={previews} onPreview={onPreview} onUpload={onUpload} onChange={onChange} />;
}

// A new or edited input run on the chosen models, side by side like the acceptance outputs, without being recorded.
export function TryPanel({ models, initial, from, blank, onTry, onUpload }: {
  models: Experiment[]; initial: unknown; from: string | null; blank: unknown;
  onTry: (experiment: string, input: unknown) => Promise<TryResult>; onUpload?: UploadAttachment;
}) {
  const local = models.filter(item => item.targetKind === 'local' && item.invoke.length);
  const [value, setValue] = useState<unknown>(initial);
  const [results, setResults] = useState<Record<string, TryResult | 'running'>>({});
  const [busy, setBusy] = useState(false);
  const gap = trialGap(value);
  async function run() {
    setBusy(true); setResults({});
    for (const item of local) {
      setResults(previous => ({ ...previous, [item.id]: 'running' }));
      let result: TryResult;
      try { result = await onTry(item.id, value); }
      catch (cause) { result = { error: cause instanceof Error ? cause.message : t('运行失败') }; }
      setResults(previous => ({ ...previous, [item.id]: result }));
    }
    setBusy(false);
  }
  return <section className="try-panel" aria-label={t('试新输入')}>
    <div className="try-head"><Sparkles size={15} aria-hidden="true" /><h3>{t('试新输入')}</h3>
      <button className="ghost-button" disabled={busy} onClick={() => { setValue(blank); setResults({}); }}><Eraser size={14} />{t('清空')}</button></div>
    <p className="muted">{from ? t('从「{name}」复制而来，可以改任何字段或换掉附件。', { name: from }) : t('按验收输入的格式填写，也可以先选一个验收输入再点“改一改再试”。')}</p>
    <InputEditor value={value} onChange={setValue} onUpload={onUpload} />
    <div className="try-actions">
      <button className="primary" disabled={busy || !!gap || !local.length} onClick={() => void run()}>{busy ? <LoaderCircle size={14} className="spin" /> : <Play size={14} />}{local.length > 1 ? t('用所选的 {count} 个模型运行', { count: local.length }) : t('运行')}</button>
      <span className="muted">{!local.length ? t('所选模型都不能在本机运行，先在上方选择一个本地模型。') : gap ?? t('只在本机运行，不会写入研究记录。')}</span>
    </div>
    {Object.keys(results).length > 0 && <div className="outputs" style={{ gridTemplateColumns: `repeat(${Math.min(local.length, 3)}, minmax(0, 1fr))` }}>{local.filter(item => results[item.id]).map(item => {
      const result = results[item.id];
      return <section key={item.id} className={`output-card ${result !== 'running' && result.error ? 'failed' : ''}`} role="status">
        <h4><span className="node-number">{experimentNumber(item.id)}</span>{item.title}</h4>
        {result === 'running' ? <p className="muted"><LoaderCircle size={14} className="spin" /> {t('正在运行…')}</p>
          : result.error ? <p className="error-text">{result.error}</p>
          : result.output === undefined ? <><p className="error-text">{t('模型没有给出这个输入的输出。')}</p>{result.log_tail && <pre className="log-tail">{result.log_tail}</pre>}</>
          : <RecordView value={result.output} />}
      </section>;
    })}</div>}
    {Object.keys(results).length > 0 && !busy && <p className="muted">{t('想把这个输入加进验收输入或评测，在对话里告诉 Agent。')}</p>}
  </section>;
}

function hasOutput(outputs: Record<string, unknown>, id: string): boolean {
  const value = outputs[id];
  return Object.hasOwn(outputs, id) && value != null && !(typeof value === 'string' && !value.trim()) && !(Array.isArray(value) && !value.length);
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

export function AcceptanceView({ files, job, pool, onRun, onTry, onUpload, onLoad, onUnload, onFeedback, delivered: answersDelivered = false }: {
  files: Snapshot['files']; job: AcceptanceJob | null | undefined; pool?: ModelPool | null;
  onRun: (experiments: string[]) => Promise<unknown>; onTry: (experiment: string, input: unknown) => Promise<TryResult>; onUpload?: UploadAttachment;
  onLoad?: (experiment: string) => Promise<unknown>; onUnload?: (experiment: string) => Promise<unknown>;
  onFeedback?: (items: AcceptanceItem[], sha: string) => Promise<unknown>; delivered?: boolean;
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
  const [page, setPage] = useState(0);
  // A trial input replaces the selected acceptance input in the main area until an input is chosen again.
  const [trial, setTrial] = useState<{ value: unknown; from: string | null; key: number } | null>(null);
  const paged = usePaged();
  const shownSha = targetSha(files, paged, 'comparison/outputs.jsonl');
  const shown = shownSha ? { sha256: shownSha } : undefined;
  const answered = currentResponse(files, 'acceptance', paged);
  const version = text(document(files, 'project.json').current_evaluation);
  const selected = ordered.filter(item => chosen.includes(item.id));
  const inputs = acceptanceInputs(files, paged);
  // One page of the driving file at a time, matched by sample ID to the file it is compared with.
  const plan = inputs ? comparisonPlan(files, '', '', version, paged) : comparisonPlan(files, selected[0]?.id ?? '', selected[1]?.id ?? '', version, paged);
  const driver = plan ? rowSource(files, paged, plan.rows) : null;
  const total = sourceTotal(driver);
  const pages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.min(page, Math.max(0, pages - 1));
  const pageRows = useRowPage(driver, currentPage);
  const partner = useRowsById(plan?.partner ? rowSource(files, paged, plan.partner) : null, (pageRows.value ?? []).map(row => text(row.sample_id)));
  const loading = !!driver && (!pageRows.value || !partner.value);
  const rows = !loading && pageRows.value && partner.value ? combineComparison(plan, pageRows.value, partner.value) : [];
  const active = rows[Math.min(index, Math.max(0, rows.length - 1))] as JsonObject | undefined;
  const outputs = object(active?.outputs);
  const activeIndex = Math.min(index, Math.max(0, rows.length - 1));
  useEffect(() => { prefetchImages([rows[activeIndex + 1], rows[activeIndex - 1]].filter(Boolean).map(row => row.input)); }, [rows, activeIndex]);
  const blank = rows.length ? blankInput(rows[0].input) : '';
  const tryModels = selected.length ? selected : ordered;
  const canTry = tryModels.some(item => item.targetKind === 'local' && item.invoke.length);
  const startTrial = (value: unknown, from: string | null) => setTrial(previous => ({ value, from, key: (previous?.key ?? 0) + 1 }));
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
      {inputs && <button className="primary" disabled={running || !runnable.length} onClick={() => void run()}>{running ? <LoaderCircle size={14} className="spin" /> : <Play size={14} />}{running ? t('正在运行') : t('用所选模型重新运行')}</button>}
    </div>
    {(job || error) && <p className={`job-line ${job?.state ?? 'failed'}`} role="status">{error || (job!.state === 'running' ? t('正在让 {models} 处理全部输入…', { models: list(job!.experiments.map(experimentNumber)) }) : job!.state === 'succeeded' ? t('运行完成，输出已更新。') : job!.failed?.length ? t('有模型没跑完（{models}），保留了之前的输出。', { models: list(job!.failed.map(experimentNumber)) }) : t('有模型没跑完，保留了之前的输出。'))}</p>}
    <div className="acceptance-body">
      <nav className="input-list" aria-label={t('验收输入')}>
        {canTry && <button className={`new-input ${trial ? 'active' : ''}`} aria-current={!!trial} onClick={() => trial || startTrial(blank, null)}><Plus size={14} aria-hidden="true" />{t('试新输入')}</button>}
        {rows.length ? <ol start={currentPage * PAGE_SIZE + 1}>{rows.map((row, i) => <li key={text(row.sample_id, String(i))}><button className={!trial && row === active ? 'active' : ''} aria-current={!trial && row === active} onClick={() => { setIndex(i); setTrial(null); }}>{sampleLabel(row, currentPage * PAGE_SIZE + i)}</button></li>)}</ol>
        : loading ? <p className={pageRows.error || partner.error ? 'error-text' : 'muted'} role="status">{pageRows.error || partner.error || t('正在读取第 {page} 页…', { page: currentPage + 1 })}</p>
        : <p className="muted">{t('还没有验收输入。告诉 Agent 你想看哪些内容的结果，它们会出现在这里。')}</p>}
        {pages > 1 && <p className="pager page-pager"><button disabled={currentPage === 0} onClick={() => { setPage(currentPage - 1); setIndex(0); }}>{t('上一页')}</button><span className="muted">{t('第 {page} / {pages} 页', { page: currentPage + 1, pages })}</span><button disabled={currentPage >= pages - 1} onClick={() => { setPage(currentPage + 1); setIndex(0); }}>{t('下一页')}</button></p>}</nav>
      <div className="acceptance-main">
        {trial ? <TryPanel key={trial.key} models={tryModels} initial={trial.value} from={trial.from} blank={blank} onTry={onTry} onUpload={onUpload} />
        : active ? <>
          <div className="input-preview">
            <div className="input-preview-head"><strong>{t('输入：')}{sampleLabel(active, currentPage * PAGE_SIZE + activeIndex)}</strong>
              {canTry && <button className="ghost-button" onClick={() => startTrial(structuredClone(active.input), sampleLabel(active, currentPage * PAGE_SIZE + activeIndex))}><PencilLine size={14} />{t('改一改再试')}</button>}</div>
            <div className="reading"><RecordView value={active.input} /></div>
          </div>
          <div className="outputs" style={{ gridTemplateColumns: `repeat(${Math.max(selected.length, 1)}, minmax(0, 1fr))` }}>{selected.map(item => <section key={item.id} className="output-card">
            <h4><span className="node-number">{experimentNumber(item.id)}</span>{item.title}{onLoad && onUnload && <LoadButton item={item} pool={pool} onLoad={onLoad} onUnload={onUnload} onError={setError} />}</h4>
            <p className={`run-state ${runState(item, job, pool)}`} title={pool?.items[item.id]?.error}>{runStateLabels[runState(item, job, pool)]}{pool?.items[item.id] && pool.items[item.id].state !== 'failed' && t(' · 约 {gb} GB', { gb: pool.items[item.id].memory_gb.toFixed(1) })}</p>
            {hasOutput(outputs, item.id) ? <RecordView value={outputs[item.id]} /> : <p className="muted">{inputs && ['runnable', 'loaded'].includes(runState(item, job, pool)) ? t('还没有这个输入的输出，点上方按钮运行。') : t('还没有这个输入的输出。')}</p>}
            {shown && onFeedback && hasOutput(outputs, item.id) && <Verdict judgment={judgments[judgmentKey(text(active.sample_id), item.id)]} onChange={value => judge(text(active.sample_id), item.id, value)} />}
          </section>)}</div>
          {shown && onFeedback && (judged > 0 || answered) && <div className="feedback-bar" role="status">
            {judged > 0 ? <><span>{t('已评价 {count} 个输出。觉得不好的会补进下一版评测，你会在审阅里再看到它们。', { count: judged })}</span>
              <button className="primary" disabled={sending} onClick={() => void sendFeedback()}>{t('提交验收意见')}</button></>
              : <span><Check size={14} aria-hidden="true" />{answersDelivered ? t('这批输出的意见已提交（{count} 条），已转给对话中的 Agent。', { count: array(answered!.items).length }) : t('这批输出的意见已提交（{count} 条）。回到对话告诉 Agent。', { count: array(answered!.items).length })}</span>}
          </div>}
        </> : canTry && !loading ? <TryPanel key="empty" models={tryModels} initial={blank} from={null} blank={blank} onTry={onTry} onUpload={onUpload} /> : null}
      </div>
    </div>
  </div>;
}
