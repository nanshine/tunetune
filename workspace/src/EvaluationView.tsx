import { useState } from 'react';
import { array, collection, document, object, referenceReview, referenceStatus, referenceStatusLabels, text } from './model';
import type { JsonObject, Snapshot } from './model';
import { RecordView, sampleLabel } from './RecordView';

// Only the fixed file beside this definition is a sample source; no record can redirect it.
export function evaluationSamples(files: Snapshot['files'], definitionPath: string): JsonObject[] | null {
  if (!/^evaluation\/[a-zA-Z0-9_-]+\/definition\.json$/.test(definitionPath)) return null;
  const rows = files[definitionPath.replace('/definition.json', '/samples.jsonl')]?.content;
  return Array.isArray(rows) ? rows.map(object) : null;
}

export function SamplesView({ rows, outputs = false, metricLabels = {} }: { rows: JsonObject[] | null; outputs?: boolean; metricLabels?: Record<string, string> }) {
  const [index, setIndex] = useState(0);
  const activeIndex = Math.min(index, Math.max(0, (rows?.length ?? 0) - 1));
  const row = rows?.[activeIndex] ?? {};
  const scores = Object.entries(object(row.scores)).filter((entry): entry is [string, number] => typeof entry[1] === 'number' && Number.isFinite(entry[1]));
  return <div className="sample-browser">
    {rows?.length ? <>
      <div className="sample-browser-toolbar"><label>{outputs ? '查看逐例输出' : '查看评测样例'}<select value={activeIndex} onChange={event => setIndex(Number(event.target.value))}>{rows.map((item, i) => <option key={text(item.sample_id, String(i))} value={i}>{sampleLabel(item, i)}</option>)}</select></label><span className="muted" role="status">{activeIndex + 1} / {rows.length}</span></div>
      <article className="evaluation-sample">
        <h4>输入</h4><div className="reading-block"><RecordView value={row.input} /></div>
        {outputs && <><h4>模型输出</h4><div className="reading-block">{row.output == null || row.output === '' ? <p className="muted">暂无该输入的输出。</p> : <RecordView value={row.output} />}</div></>}
        {Object.hasOwn(row, 'reference') && <><h4>参考输出{!outputs && <span className={`record-badge review-${referenceStatus(row)}`}>{referenceStatusLabels[referenceStatus(row)!]}</span>}</h4><RecordView value={row.reference} /></>}
        {Object.hasOwn(row, 'label') && <><h4>标签</h4><RecordView value={row.label} /></>}
        {Object.hasOwn(row, 'labels') && <><h4>标签</h4><RecordView value={row.labels} /></>}
        {outputs && !!scores.length && <div className="metric-list" aria-label="逐例评分">{scores.map(([key, value]) => <span key={key}>{Object.hasOwn(metricLabels, key) ? metricLabels[key] : key}<strong>{value.toLocaleString()}</strong></span>)}</div>}
      </article>
      <div className="sample-pagination"><button disabled={activeIndex === 0} onClick={() => setIndex(activeIndex - 1)}>上一例</button><button disabled={activeIndex === rows.length - 1} onClick={() => setIndex(activeIndex + 1)}>下一例</button></div>
    </> : <p className="muted">{outputs ? rows ? '逐例输出文件为空。' : '尚无逐例输出。' : rows ? '样例文件为空。' : '尚无可浏览样例，请在 Agent 会话中准备评测样例。'}</p>}
  </div>;
}

export function ReviewSummary({ rows }: { rows: JsonObject[] }) {
  const counts = referenceReview(rows);
  if (!counts.confirmed && !counts.corrected && !counts.draft) return null;
  return <div className="review-summary">
    <p>参考答案：{(['confirmed', 'corrected', 'draft'] as const).filter(key => counts[key]).map(key => `${referenceStatusLabels[key]} ${counts[key]}`).join(' · ')}</p>
    {counts.draft > 0 && <p className="muted">待审核的参考答案由 Agent、模型或未核实的来源起草；需要你判断的答案请在 Agent 会话中确认或修正，未审核前分数只表示与草稿的一致程度。</p>}
  </div>;
}

export function EvaluationView({ files, currentVersion, selection, onSelect }: { files: Snapshot['files']; currentVersion: string; selection: string; onSelect: (path: string) => void }) {
  const definitions = collection(files, /^evaluation\/[a-zA-Z0-9_-]+\/definition\.json$/);
  const currentPath = currentVersion ? `evaluation/${currentVersion}/definition.json` : 'evaluation/draft/definition.json';
  const selectedPath = definitions.some(([path]) => path === selection) ? selection : files[currentPath] ? currentPath : definitions[0]?.[0] ?? currentPath;
  const definition = document(files, selectedPath);
  const isDraft = selectedPath === 'evaluation/draft/definition.json';
  const metrics = array(definition.metrics).map(object);
  return <div className="evaluation-view">
    {!!definitions.length && <div className="evaluation-toolbar"><label>查看评测版本<select value={selectedPath} onChange={event => onSelect(event.target.value)}>{definitions.map(([path, item]) => <option key={path} value={path}>{path === 'evaluation/draft/definition.json' ? '草稿' : text(item.version, path.split('/')[1])}{path === currentPath && path !== 'evaluation/draft/definition.json' ? ' · 当前' : ''}</option>)}</select></label></div>}
    {!definitions.length ? <div className="empty-section"><h3>尚无评测定义</h3><p className="muted">与 Agent 确认评分规则和代表性样例后，定义会显示在这里。</p></div> : <>
      {isDraft && <p className="muted">草稿尚未发布，内容仍可调整，不代表正式评测结果。</p>}
      {!files[currentPath] && currentVersion && <p className="notice">当前版本定义尚未同步，正在浏览已有版本。</p>}
      <section className="panel-section"><h3>评测说明</h3><div className="reading-block"><RecordView value={definition.description} /></div></section>
      <section className="panel-section"><h3>评分规则与核心指标</h3><RecordView value={definition.rubric} />{metrics.map((metric, index) => <div className="metric-definition" key={text(metric.id, String(index))}><div><strong>{text(metric.label, text(metric.id, '未命名指标'))}</strong></div><span>{text(metric.direction) === 'maximize' ? '越高越好' : text(metric.direction) === 'minimize' ? '越低越好' : ''}</span></div>)}{!metrics.length && <p className="muted">尚未定义指标。</p>}</section>
      <section className="panel-section"><h3>评测样例</h3><ReviewSummary rows={evaluationSamples(files, selectedPath) ?? []} /><SamplesView key={selectedPath} rows={evaluationSamples(files, selectedPath)} /></section>
    </>}
  </div>;
}
