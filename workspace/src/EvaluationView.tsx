import { useState } from 'react';
import { ClipboardCheck } from 'lucide-react';
import { array, collection, currentResponse, document, evaluationRuns, object, referenceReview, referenceStatus, referenceStatusLabels, sampleSplit, splitCounts, text } from './model';
import type { JsonObject, ReferenceStatus, Snapshot, Split } from './model';
import { PAGE_SIZE, rowSource, sourceTotal, usePaged, useRowPage } from './rows';
import type { RowSource } from './rows';
import { RecordView, sampleLabel } from './RecordView';
import { Empty, Section } from './Parts';
import { ReviewView } from './ReviewView';
import type { ReviewItem } from './useWorkspace';
import { t } from './i18n';

// Only the fixed file beside this definition is a sample source; no record can redirect it.
export function evaluationSamples(files: Snapshot['files'], definitionPath: string): JsonObject[] | null {
  if (!/^evaluation\/[a-zA-Z0-9_-]+\/definition\.json$/.test(definitionPath)) return null;
  const rows = files[definitionPath.replace('/definition.json', '/samples.jsonl')]?.content;
  return Array.isArray(rows) ? rows.map(object) : null;
}

// The sample source of a definition, sent whole or in pages; no record can redirect it.
export function evaluationSource(files: Snapshot['files'], paged: Parameters<typeof rowSource>[1], definitionPath: string): RowSource | null {
  if (!/^evaluation\/[a-zA-Z0-9_-]+\/definition\.json$/.test(definitionPath)) return null;
  return rowSource(files, paged, definitionPath.replace('/definition.json', '/samples.jsonl'));
}
// Split and review counts over the whole file, also when only a page of it is loaded.
export function sourceCounts(source: RowSource): { splits: Record<Split, number>; review: Record<ReferenceStatus, number> } {
  if (source.kind === 'inline') return { splits: splitCounts(source.rows), review: referenceReview(source.rows) };
  const splits = source.file.splits ?? {};
  const status = source.file.reference_status ?? {};
  return { splits: { development: splits.development ?? 0, final: splits.final ?? 0 }, review: { confirmed: status.confirmed ?? 0, corrected: status.corrected ?? 0, draft: status.draft ?? 0 } };
}

export function SamplesView({ source, outputs = false, metricLabels = {} }: { source: RowSource | null; outputs?: boolean; metricLabels?: Record<string, string> }) {
  const [index, setIndex] = useState(0);
  const total = sourceTotal(source);
  const activeIndex = Math.min(index, Math.max(0, total - 1));
  const page = Math.floor(activeIndex / PAGE_SIZE);
  const pages = Math.ceil(total / PAGE_SIZE);
  const loaded = useRowPage(source, page);
  if (!total) return <p className="muted">{outputs ? t('这次评测没有逐例输出。') : t('还没有样例。')}</p>;
  const rows = loaded.value;
  if (!rows) return <p className={loaded.error ? 'error-text' : 'muted'} role="status">{loaded.error || t('正在读取第 {page} 页…', { page: page + 1 })}</p>;
  const row = rows[activeIndex - page * PAGE_SIZE] ?? rows[0];
  const scores = Object.entries(object(row.scores)).filter((entry): entry is [string, number] => typeof entry[1] === 'number' && Number.isFinite(entry[1]));
  return <div className="samples">
    <div className="sample-column">
      <ul className="sample-index" aria-label={outputs ? t('逐例输出') : t('评测样例')}>{rows.map((item, offset) => {
        const i = page * PAGE_SIZE + offset;
        const status = !outputs ? referenceStatus(item) : null;
        return <li key={text(item.sample_id, String(i))}><button className={i === activeIndex ? 'active' : ''} aria-current={i === activeIndex} onClick={() => setIndex(i)}><span>{sampleLabel(item, i)}</span>{status && <span className={`state-dot review-${status}`} title={referenceStatusLabels[status]} />}</button></li>;
      })}</ul>
      {pages > 1 && <p className="pager page-pager"><button disabled={page === 0} onClick={() => setIndex((page - 1) * PAGE_SIZE)}>{t('上一页')}</button><span className="muted">{t('第 {page} / {pages} 页', { page: page + 1, pages })}</span><button disabled={page >= pages - 1} onClick={() => setIndex((page + 1) * PAGE_SIZE)}>{t('下一页')}</button></p>}
    </div>
    <article className="sample-detail">
      <div className="sample-field"><span className="field-label">{t('输入')}</span><div className="reading"><RecordView value={row.input} /></div></div>
      {outputs && <div className="sample-field"><span className="field-label">{t('模型输出')}</span>{row.output == null || row.output === '' ? <p className="muted">{t('这个输入没有输出。')}</p> : <RecordView value={row.output} />}</div>}
      {!outputs && sampleSplit(row) === 'final' && <p className="badge">{t('最终检查样例')}</p>}
      {Object.hasOwn(row, 'reference') && <div className="sample-field"><span className="field-label">{t('参考答案')}{!outputs && referenceStatus(row) && <span className={`badge review-${referenceStatus(row)}`}>{referenceStatusLabels[referenceStatus(row)!]}</span>}</span><RecordView value={row.reference} /></div>}
      {outputs && !!scores.length && <div className="chips" aria-label={t('逐例评分')}>{scores.map(([key, value]) => <span className="chip" key={key}>{Object.hasOwn(metricLabels, key) ? metricLabels[key] : key} <strong>{value.toLocaleString()}</strong></span>)}</div>}
      <p className="pager"><button disabled={activeIndex === 0} onClick={() => setIndex(activeIndex - 1)}>{t('上一例')}</button><span className="muted" role="status">{activeIndex + 1} / {total}</span><button disabled={activeIndex === total - 1} onClick={() => setIndex(activeIndex + 1)}>{t('下一例')}</button></p>
    </article>
  </div>;
}

export function ReviewSummary({ counts }: { counts: Record<ReferenceStatus, number> }) {
  if (!counts.confirmed && !counts.corrected && !counts.draft) return null;
  return <p className="summary-line">{t('参考答案 {counts}', { counts: (['confirmed', 'corrected', 'draft'] as const).filter(key => counts[key]).map(key => `${referenceStatusLabels[key]} ${counts[key]}`).join(t('，')) })}{counts.draft > 0 && <span className="muted">{t('。待审核的答案是草稿，分数只表示与草稿一致的程度。')}</span>}</p>;
}

// Which samples guide the work and which are kept for one final check, and how often that check was used.
export function SplitSummary({ files, version, counts, definition }: { files: Snapshot['files']; version: string; counts: Record<Split, number>; definition: JsonObject }) {
  const runs = evaluationRuns(files).filter(run => run.version === version && run.split === 'final');
  if (!counts.final) return text(definition.no_final_reason) ? <p className="notice">{t('没有另留最终检查：')}{text(definition.no_final_reason)}</p> : null;
  return <p className="summary-line">{t('开发样例 {development} 条，最终检查 {final} 条', { development: counts.development, final: counts.final })}<span className="muted">{runs.length ? t('。最终检查已运行 {runs} 次，涉及 {models} 个模型；它只在选定模型后用一次。', { runs: runs.length, models: new Set(runs.map(run => run.experimentId)).size }) : t('。最终检查还没有运行；它只在选定模型后用一次。')}</span></p>;
}

type Tab = 'overview' | 'samples' | 'review';

export function EvaluationView({ files, currentVersion, selection, onSelect, initialTab, onReview, delivered = false }: {
  files: Snapshot['files']; currentVersion: string; selection: string; onSelect: (path: string) => void; initialTab?: Tab;
  onReview?: (items: ReviewItem[], sha: string) => Promise<unknown>; delivered?: boolean;
}) {
  const paged = usePaged();
  const definitions = collection(files, /^evaluation\/[a-zA-Z0-9_-]+\/definition\.json$/);
  const draft = rowSource(files, paged, 'evaluation/draft/samples.jsonl');
  const reviewable = (!!draft && sourceCounts(draft).review.draft > 0) || !!currentResponse(files, 'evaluation_review', paged);
  const [tab, setTab] = useState<Tab>(initialTab === 'review' && !reviewable ? 'overview' : initialTab ?? (reviewable && !currentVersion ? 'review' : 'overview'));
  const currentPath = currentVersion ? `evaluation/${currentVersion}/definition.json` : 'evaluation/draft/definition.json';
  const selectedPath = definitions.some(([path]) => path === selection) ? selection : files[currentPath] ? currentPath : definitions[0]?.[0] ?? currentPath;
  const definition = document(files, selectedPath);
  const metrics = array(definition.metrics).map(object);
  const source = evaluationSource(files, paged, selectedPath);
  const counts = source ? sourceCounts(source) : null;
  if (!definitions.length && !draft) return <Empty icon={<ClipboardCheck size={20} />} title={t('还没有评测')}>{t('确定什么样的输出算好之后，评分规则和样例会出现在这里。')}</Empty>;
  return <div className="evaluation">
    <div className="tabbar" role="tablist" aria-label={t('评测内容')}>
      {(['overview', 'samples', ...(reviewable ? ['review'] : [])] as Tab[]).map(item => <button key={item} role="tab" aria-selected={tab === item} className={tab === item ? 'active' : ''} onClick={() => setTab(item)}>{{ overview: t('评分规则'), samples: t('样例'), review: t('审阅参考答案') }[item]}</button>)}
      {tab !== 'review' && definitions.length > 0 && <label className="version-select">{t('版本')}<select value={selectedPath} onChange={event => onSelect(event.target.value)}>{definitions.map(([path, item]) => <option key={path} value={path}>{path === 'evaluation/draft/definition.json' ? t('草稿') : text(item.version, path.split('/')[1])}{path === currentPath && !path.includes('/draft/') ? t('（当前）') : ''}</option>)}</select></label>}
    </div>
    {tab === 'review' && draft ? <ReviewView files={files} source={draft} onSubmit={onReview} delivered={delivered} />
      : !definitions.length ? <p className="muted">{t('评测还在起草，样例在“审阅参考答案”里。')}</p>
      : tab === 'overview' ? <>
        {selectedPath.includes('/draft/') && <p className="notice">{t('这是草稿，还会调整。')}</p>}
        {!!counts && <ReviewSummary counts={counts.review} />}
        {!!counts && !selectedPath.includes('/draft/') && <SplitSummary files={files} version={text(definition.version, selectedPath.split('/')[1])} counts={counts.splits} definition={definition} />}
        {text(definition.description) && <p className="lead-text">{text(definition.description)}</p>}
        <Section title={t('指标')}>{metrics.length ? <ul className="metric-defs">{metrics.map((metric, index) => <li key={text(metric.id, String(index))}><strong>{text(metric.label, text(metric.id, t('未命名指标')))}</strong><span className="muted">{text(metric.direction) === 'maximize' ? t('越高越好') : text(metric.direction) === 'minimize' ? t('越低越好') : ''}</span>{text(metric.description) && <p>{text(metric.description)}</p>}</li>)}</ul> : <p className="muted">{t('还没有定义指标。')}</p>}</Section>
        {definition.rubric != null && definition.rubric !== '' && <Section title={t('评分规则')}><div className="prose"><RecordView value={definition.rubric} /></div></Section>}
      </> : <SamplesView key={selectedPath} source={source} />}
  </div>;
}
