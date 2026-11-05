import { useState } from 'react';
import { ClipboardCheck } from 'lucide-react';
import { array, collection, currentResponse, document, evaluationRuns, object, referenceReview, referenceStatus, referenceStatusLabels, sampleSplit, splitCounts, text } from './model';
import type { JsonObject, Snapshot } from './model';
import { RecordView, sampleLabel } from './RecordView';
import { Empty, Section } from './Parts';
import { ReviewView } from './ReviewView';
import type { ReviewItem } from './useWorkspace';

// Only the fixed file beside this definition is a sample source; no record can redirect it.
export function evaluationSamples(files: Snapshot['files'], definitionPath: string): JsonObject[] | null {
  if (!/^evaluation\/[a-zA-Z0-9_-]+\/definition\.json$/.test(definitionPath)) return null;
  const rows = files[definitionPath.replace('/definition.json', '/samples.jsonl')]?.content;
  return Array.isArray(rows) ? rows.map(object) : null;
}

export function SamplesView({ rows, outputs = false, metricLabels = {} }: { rows: JsonObject[] | null; outputs?: boolean; metricLabels?: Record<string, string> }) {
  const [index, setIndex] = useState(0);
  if (!rows?.length) return <p className="muted">{outputs ? '这次评测没有逐例输出。' : '还没有样例。'}</p>;
  const activeIndex = Math.min(index, rows.length - 1);
  const row = rows[activeIndex];
  const scores = Object.entries(object(row.scores)).filter((entry): entry is [string, number] => typeof entry[1] === 'number' && Number.isFinite(entry[1]));
  return <div className="samples">
    <ul className="sample-index" aria-label={outputs ? '逐例输出' : '评测样例'}>{rows.map((item, i) => {
      const status = !outputs ? referenceStatus(item) : null;
      return <li key={text(item.sample_id, String(i))}><button className={i === activeIndex ? 'active' : ''} aria-current={i === activeIndex} onClick={() => setIndex(i)}><span>{sampleLabel(item, i)}</span>{status && <span className={`state-dot review-${status}`} title={referenceStatusLabels[status]} />}</button></li>;
    })}</ul>
    <article className="sample-detail">
      <div className="sample-field"><span className="field-label">输入</span><div className="reading"><RecordView value={row.input} /></div></div>
      {outputs && <div className="sample-field"><span className="field-label">模型输出</span>{row.output == null || row.output === '' ? <p className="muted">这个输入没有输出。</p> : <RecordView value={row.output} />}</div>}
      {!outputs && sampleSplit(row) === 'final' && <p className="badge">最终检查样例</p>}
      {Object.hasOwn(row, 'reference') && <div className="sample-field"><span className="field-label">参考答案{!outputs && referenceStatus(row) && <span className={`badge review-${referenceStatus(row)}`}>{referenceStatusLabels[referenceStatus(row)!]}</span>}</span><RecordView value={row.reference} /></div>}
      {outputs && !!scores.length && <div className="chips" aria-label="逐例评分">{scores.map(([key, value]) => <span className="chip" key={key}>{Object.hasOwn(metricLabels, key) ? metricLabels[key] : key} <strong>{value.toLocaleString()}</strong></span>)}</div>}
      <p className="pager"><button disabled={activeIndex === 0} onClick={() => setIndex(activeIndex - 1)}>上一例</button><span className="muted" role="status">{activeIndex + 1} / {rows.length}</span><button disabled={activeIndex === rows.length - 1} onClick={() => setIndex(activeIndex + 1)}>下一例</button></p>
    </article>
  </div>;
}

export function ReviewSummary({ rows }: { rows: JsonObject[] }) {
  const counts = referenceReview(rows);
  if (!counts.confirmed && !counts.corrected && !counts.draft) return null;
  return <p className="summary-line">参考答案 {(['confirmed', 'corrected', 'draft'] as const).filter(key => counts[key]).map(key => `${referenceStatusLabels[key]} ${counts[key]}`).join('，')}{counts.draft > 0 && <span className="muted">。待审核的答案是草稿，分数只表示与草稿一致的程度。</span>}</p>;
}

// Which samples guide the work and which are kept for one final check, and how often that check was used.
export function SplitSummary({ files, version, rows, definition }: { files: Snapshot['files']; version: string; rows: JsonObject[]; definition: JsonObject }) {
  const counts = splitCounts(rows);
  const runs = evaluationRuns(files).filter(run => run.version === version && run.split === 'final');
  if (!counts.final) return text(definition.no_final_reason) ? <p className="notice">没有另留最终检查：{text(definition.no_final_reason)}</p> : null;
  return <p className="summary-line">开发样例 {counts.development} 条，最终检查 {counts.final} 条<span className="muted">。最终检查{runs.length ? `已运行 ${runs.length} 次，涉及 ${new Set(runs.map(run => run.experimentId)).size} 个模型` : '还没有运行'}；它只在选定模型后用一次。</span></p>;
}

type Tab = 'overview' | 'samples' | 'review';

export function EvaluationView({ files, currentVersion, selection, onSelect, initialTab, onReview }: {
  files: Snapshot['files']; currentVersion: string; selection: string; onSelect: (path: string) => void; initialTab?: Tab;
  onReview?: (items: ReviewItem[], sha: string) => Promise<unknown>;
}) {
  const definitions = collection(files, /^evaluation\/[a-zA-Z0-9_-]+\/definition\.json$/);
  const draftRows = Array.isArray(files['evaluation/draft/samples.jsonl']?.content) ? array(files['evaluation/draft/samples.jsonl'].content).map(object) : null;
  const reviewable = !!draftRows?.some(row => referenceStatus(row) === 'draft') || !!currentResponse(files, 'evaluation_review');
  const [tab, setTab] = useState<Tab>(initialTab === 'review' && !reviewable ? 'overview' : initialTab ?? (reviewable && !currentVersion ? 'review' : 'overview'));
  const currentPath = currentVersion ? `evaluation/${currentVersion}/definition.json` : 'evaluation/draft/definition.json';
  const selectedPath = definitions.some(([path]) => path === selection) ? selection : files[currentPath] ? currentPath : definitions[0]?.[0] ?? currentPath;
  const definition = document(files, selectedPath);
  const metrics = array(definition.metrics).map(object);
  const rows = evaluationSamples(files, selectedPath);
  if (!definitions.length && !draftRows) return <Empty icon={<ClipboardCheck size={20} />} title="还没有评测">确定什么样的输出算好之后，评分规则和样例会出现在这里。</Empty>;
  return <div className="evaluation">
    <div className="tabbar" role="tablist" aria-label="评测内容">
      {(['overview', 'samples', ...(reviewable ? ['review'] : [])] as Tab[]).map(item => <button key={item} role="tab" aria-selected={tab === item} className={tab === item ? 'active' : ''} onClick={() => setTab(item)}>{{ overview: '评分规则', samples: '样例', review: '审阅参考答案' }[item]}</button>)}
      {tab !== 'review' && definitions.length > 0 && <label className="version-select">版本<select value={selectedPath} onChange={event => onSelect(event.target.value)}>{definitions.map(([path, item]) => <option key={path} value={path}>{path === 'evaluation/draft/definition.json' ? '草稿' : text(item.version, path.split('/')[1])}{path === currentPath && !path.includes('/draft/') ? '（当前）' : ''}</option>)}</select></label>}
    </div>
    {tab === 'review' && draftRows ? <ReviewView files={files} rows={draftRows} onSubmit={onReview} />
      : !definitions.length ? <p className="muted">评测还在起草，样例在“审阅参考答案”里。</p>
      : tab === 'overview' ? <>
        {selectedPath.includes('/draft/') && <p className="notice">这是草稿，还会调整。</p>}
        {!!rows && <ReviewSummary rows={rows} />}
        {!!rows && !selectedPath.includes('/draft/') && <SplitSummary files={files} version={text(definition.version, selectedPath.split('/')[1])} rows={rows} definition={definition} />}
        {text(definition.description) && <p className="lead-text">{text(definition.description)}</p>}
        <Section title="指标">{metrics.length ? <ul className="metric-defs">{metrics.map((metric, index) => <li key={text(metric.id, String(index))}><strong>{text(metric.label, text(metric.id, '未命名指标'))}</strong><span className="muted">{text(metric.direction) === 'maximize' ? '越高越好' : text(metric.direction) === 'minimize' ? '越低越好' : ''}</span>{text(metric.description) && <p>{text(metric.description)}</p>}</li>)}</ul> : <p className="muted">还没有定义指标。</p>}</Section>
        {definition.rubric != null && definition.rubric !== '' && <Section title="评分规则"><div className="prose"><RecordView value={definition.rubric} /></div></Section>}
      </> : <SamplesView key={selectedPath} rows={rows} />}
  </div>;
}
