import { useEffect, useState } from 'react';
import { CheckCircle2, CircleHelp, Clock3, RefreshCw, XCircle } from 'lucide-react';
import { array, object, resourceObservation, resourceStates, text } from './model';
import type { JsonObject, Observations } from './model';
import { RecordView } from './RecordView';

const feasibilityLabels: Record<string, string> = { feasible: '可行', conditional: '有条件可行', infeasible: '不可行', unknown: '待评估' };

export function ProposalView({ proposal }: { proposal: JsonObject }) {
  const feasibility = object(proposal.feasibility);
  const verdict = text(feasibility.verdict, 'unknown');
  return <div className="project-brief">
    <p className="proposal-summary">{text(proposal.summary) || '和 Agent 聊聊你想完成的事，研究提案会逐步整理在这里。'}</p>
    {array(proposal.sections).map(object).map((section, index) => <section className="panel-section" key={index}><h3>{text(section.title)}</h3><p className="brief-text">{text(section.body)}</p></section>)}
    {!!Object.keys(feasibility).length && <section className="panel-section"><h3>可行性 <span className="record-badge">{Object.hasOwn(feasibilityLabels, verdict) ? feasibilityLabels[verdict] : '待评估'}</span></h3>{text(feasibility.reason) && <p className="brief-text">{text(feasibility.reason)}</p>}</section>}
    {!!array(proposal.examples).length && <details className="proposal-examples"><summary>输入 / 输出示例 <span className="count">{array(proposal.examples).length}</span></summary>{array(proposal.examples).map(object).map((example, index) => <article className="brief-example" key={text(example.id, String(index))}>
      <h4>例子 {index + 1}</h4>
      <div><span className="section-label">提供的内容</span><div className="brief-text">{example.input == null || example.input === '' ? '待一起补充' : <RecordView value={example.input} />}</div></div>
      <div><span className="section-label">希望得到</span><div className="brief-text">{example.expected_output == null || example.expected_output === '' ? '待一起补充' : <RecordView value={example.expected_output} />}</div></div>
    </article>)}</details>}
  </div>;
}

const resourceTypes: Record<string, string> = { data: '数据', dataset: '数据', model: '模型', environment: '环境', hardware: '硬件', tool: '工具', other: '其他' };
const resourceIcons = { ready: CheckCircle2, missing: XCircle, changed: RefreshCw, busy: Clock3, unknown: CircleHelp };

export function groupResources(items: JsonObject[]): [string, JsonObject[]][] {
  const groups = new Map<string, JsonObject[]>();
  for (const item of items) {
    const type = text(item.type, 'other') || 'other';
    const label = Object.hasOwn(resourceTypes, type) ? resourceTypes[type] : type;
    groups.set(label, [...(groups.get(label) ?? []), item]);
  }
  return [...groups];
}
function readableSize(value: unknown): string {
  if (typeof value === 'string') return value;
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return '';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const scale = value > 0 ? Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1) : 0;
  return `${Number((value / 1024 ** scale).toFixed(1)).toLocaleString()} ${units[scale]}`;
}
function readableDate(value: string | undefined): string {
  const time = Date.parse(value ?? '');
  return Number.isFinite(time) ? new Date(time).toLocaleString('zh-CN') : '';
}

export function ResourcesView({ resources, observations }: { resources: JsonObject; observations?: Observations }) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    // Expire stale facts even if the file channel is disconnected or its revision is unchanged.
    const timer = setInterval(() => setNow(Date.now()), 2000);
    return () => clearInterval(timer);
  }, []);
  const groups = groupResources(array(resources.items).map(object));
  return <div className="resource-list">{!groups.length && <p className="muted">Agent 会查看现有材料和环境，并将资源整理在这里。</p>}
    {groups.map(([type, items]) => <section className="resource-group" key={type}><h3>{type} <span className="count">{items.length}</span></h3>{items.map((resource, index) => {
      const { state, observation } = resourceObservation(resource, observations, now);
      const Icon = resourceIcons[state];
      const title = text(resource.title, '未命名资源');
      const version = text(resource.version);
      const detail = observation?.detail;
      const observedPython = object(resource.monitor).kind === 'python' && detail && state === 'ready';
      const name = observedPython && detail.startsWith(title) ? detail : [title, !observedPython && version && !title.includes(version) ? version : ''].filter(Boolean).join(' ');
      const measuredSize = readableSize(observation?.size ?? resource.size);
      const quantity = /条|行|样本|参数|samples|records|parameters/i.test(text(resource.size)) ? text(resource.size) : '';
      const size = [...new Set([quantity, measuredSize].filter(Boolean))].join(' · ');
      const location = text(resource.path) || text(resource.location);
      const modified = readableDate(observation?.modified_at);
      const description = [resourceStates[state], detail, modified ? `文件修改于 ${modified}` : ''].filter(Boolean).join(' · ');
      const showDetail = object(resource.monitor).kind !== 'file' && state !== 'unknown' && state !== 'missing';
      return <article className="brief-resource" key={text(resource.id, String(index))}>
        <div className="resource-heading"><h4>{name}</h4><span className={`resource-state ${state}`} role="img" title={description} aria-label={resourceStates[state]}><Icon size={18} aria-hidden="true" /></span></div>
        {(location || size) && <p className="resource-facts">{[location, size].filter(Boolean).join(' · ')}</p>}
        {showDetail && detail && detail !== name && <p className="resource-facts">{detail}</p>}
      </article>;
    })}</section>)}
  </div>;
}
