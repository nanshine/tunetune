import { useEffect, useState } from 'react';
import { BookOpen, ChevronDown, CircleCheck, Compass, FileText, Gauge, Layers, ListTree, PackageCheck, Target } from 'lucide-react';
import { array, object, resourceObservation, resourceStates, roleLabels, text } from './model';
import type { JsonObject, Observations, ResourceState, Snapshot } from './model';
import { RecordView } from './RecordView';
import { Empty, ResponseBar, Section } from './Parts';

const feasibilityLabels: Record<string, string> = { feasible: '可行', conditional: '有条件可行', infeasible: '不可行', unknown: '待评估' };
const roleOrder = ['baseline', 'recommended', 'reference', 'challenge'];

function host(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return url; }
}

export function ProposalView({ files, waiting = null, onRespond }: { files: Snapshot['files']; waiting?: string | null; onRespond?: (decision: string, note: string, sha: string) => Promise<unknown> }) {
  const proposal = files['proposal.json'] ? object(files['proposal.json'].content) : {};
  const resources = new Map(array(object(files['resources.json']?.content).items).map(object).map(item => [text(item.id), item]));
  const approaches = array(proposal.approaches).map(object).sort((a, b) => roleOrder.indexOf(text(array(a.roles)[0])) - roleOrder.indexOf(text(array(b.roles)[0])));
  const considered = array(proposal.considered).map(object);
  const examples = array(proposal.examples).map(object);
  const sources = array(proposal.sources).map(object).filter(item => /^https?:\/\//.test(text(item.url)));
  const feasibility = object(proposal.feasibility);
  if (!text(proposal.summary) && !approaches.length && !examples.length) return <Empty icon={<Target size={20} />} title="还没有研究提案">在对话里说说你想让模型做什么，提案会整理在这里。</Empty>;
  return <div className="brief">
    {onRespond && <ResponseBar files={files} kind="proposal" waiting={waiting} prompt="看完下面的方案、资源和预算后，可以直接在这里确认或提出修改。" approve="确认，开始研究" decisions={{ approve: 'approve', revise: 'revise' }} onSubmit={onRespond} />}
    <div className="lead">
      <p>{text(proposal.summary)}</p>
      {!!Object.keys(feasibility).length && <p className="lead-meta"><span className={`badge feasibility-${text(feasibility.verdict, 'unknown')}`}>{feasibilityLabels[text(feasibility.verdict)] ?? '待评估'}</span>{text(feasibility.reason)}</p>}
    </div>
    {(text(proposal.goal) || text(proposal.output)) && <dl className="facts">
      {text(proposal.goal) && <div><dt>目标</dt><dd>{text(proposal.goal)}</dd></div>}
      {text(proposal.output) && <div><dt>输出</dt><dd>{text(proposal.output)}</dd></div>}
    </dl>}
    {!!examples.length && <Section title="你的例子" icon={<FileText size={15} />} aside={<span className="count">{examples.length}</span>}>
      <ol className="examples">{examples.map((example, index) => <li key={text(example.id, String(index))}><div className="example-input"><RecordView value={example.input} /></div>{example.expected_output != null && example.expected_output !== '' && <div className="example-output"><span className="arrow" aria-hidden="true">→</span><RecordView value={example.expected_output} /></div>}</li>)}</ol>
    </Section>}
    {!!approaches.length && <Section title="研究路线" icon={<Compass size={15} />}>
      <div className="routes">{approaches.map((approach, index) => <article className="route" key={text(approach.id, String(index))}>
        <div className="route-head">{array(approach.roles).map(role => <span className={`badge role-${String(role)}`} key={String(role)}>{roleLabels[String(role)] || String(role)}</span>)}<h4>{text(approach.title)}</h4></div>
        <p>{text(approach.rationale)}</p>
        {text(approach.limitations) && <p className="muted">局限：{text(approach.limitations)}</p>}
        {!!array(approach.resource_ids).length && <div className="chips">{array(approach.resource_ids).map(id => resources.get(String(id))).filter(Boolean).map(item => <span className="chip" key={text(item!.id)}>{text(item!.title)}</span>)}</div>}
      </article>)}</div>
    </Section>}
    {!!considered.length && <Section title="考虑过的方法" icon={<Layers size={15} />}>
      <ul className="considered">{considered.map((item, index) => <li key={index}><span className={`badge ${item.decision === 'adopted' ? 'tone-good' : ''}`}>{item.decision === 'adopted' ? '采用' : '不采用'}</span><div><strong>{text(item.family)}</strong><p>{text(item.reason)}</p></div></li>)}</ul>
    </Section>}
    {text(proposal.evaluation) && <Section title="怎么判断好坏" icon={<Gauge size={15} />}><p className="prose">{text(proposal.evaluation)}</p></Section>}
    {(text(proposal.budget) || text(proposal.stopping)) && <Section title="预算与停止" icon={<ListTree size={15} />}><dl className="facts">
      {text(proposal.budget) && <div><dt>预算</dt><dd>{text(proposal.budget)}</dd></div>}
      {text(proposal.stopping) && <div><dt>何时停止</dt><dd>{text(proposal.stopping)}</dd></div>}
    </dl></Section>}
    {text(proposal.delivery) && <Section title="最后交付" icon={<PackageCheck size={15} />}><p className="prose">{text(proposal.delivery)}</p></Section>}
    {!!array(proposal.assumptions).length && <Section title="仍待验证的假设" icon={<CircleCheck size={15} />}><ul className="plain-list">{array(proposal.assumptions).map((item, index) => <li key={index}>{String(item)}</li>)}</ul></Section>}
    {!!sources.length && <Section title="参考来源" icon={<BookOpen size={15} />}><ol className="sources">{sources.map((item, index) => <li key={index}><a href={text(item.url)} target="_blank" rel="noreferrer">{text(item.title, host(text(item.url)))}</a><span className="muted">{host(text(item.url))}</span></li>)}</ol></Section>}
  </div>;
}

const resourceTypes: Record<string, string> = { data: '数据', dataset: '数据', model: '模型', environment: '环境', hardware: '硬件', code: '代码与工具', tool: '代码与工具', api: 'API 服务', annotation: '标注与审核', storage: '存储', credential: '凭证配置', other: '其他' };
export function groupResources(items: JsonObject[]): [string, JsonObject[]][] {
  const groups = new Map<string, JsonObject[]>();
  for (const item of items) {
    const type = text(item.type, 'other') || 'other';
    const label = Object.hasOwn(resourceTypes, type) ? resourceTypes[type] : type;
    groups.set(label, [...(groups.get(label) ?? []), item]);
  }
  return [...groups];
}
export function readableSize(value: unknown): string {
  if (typeof value === 'string') {
    const bytes = /^(\d+)\s*bytes?$/i.exec(value.trim());
    return bytes ? readableSize(Number(bytes[1])) : value;
  }
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return '';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const scale = value > 0 ? Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1) : 0;
  return `${Number((value / 1024 ** scale).toFixed(1)).toLocaleString()} ${units[scale]}`;
}
function readableDate(value: string | undefined): string {
  const time = Date.parse(value ?? '');
  return Number.isFinite(time) ? new Date(time).toLocaleString('zh-CN') : '';
}

function ResourceRow({ resource, state, detail, modified, size }: { resource: JsonObject; state: ResourceState; detail?: string; modified: string; size: string }) {
  const [open, setOpen] = useState(false);
  const facts: [string, string][] = [['用途', text(resource.purpose)], ['来源', text(resource.source)], ['版本', text(resource.version)], ['位置', text(resource.path) || text(resource.location)],
    ['准备', text(resource.preparation)], ['使用条件', text(resource.access)], ['监测', [detail, modified ? `修改于 ${modified}` : ''].filter(Boolean).join('，')]];
  const shown = facts.filter(([, value]) => value);
  return <li className={`resource ${open ? 'open' : ''}`}>
    <button className="resource-row" aria-expanded={open} onClick={() => setOpen(!open)}>
      <span className={`state-dot resource-${state}`} aria-hidden="true" />
      <span className="resource-name">{text(resource.title, '未命名资源')}</span>
      <span className="resource-state">{resourceStates[state]}</span>
      {size && <span className="resource-size">{size}</span>}
      <ChevronDown size={14} className="chevron" aria-hidden="true" />
    </button>
    {!open && text(resource.purpose) && <p className="resource-purpose">{text(resource.purpose)}</p>}
    {open && <dl className="resource-facts">{shown.map(([label, value]) => <div key={label}><dt>{label}</dt><dd className={label === '位置' || label === '版本' ? 'path' : ''}>{label === '来源' && /^https?:\/\//.test(value) ? <a href={value} target="_blank" rel="noreferrer">{value}</a> : value}</dd></div>)}</dl>}
  </li>;
}

export function ResourcesView({ resources, observations }: { resources: JsonObject; observations?: Observations }) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    // Expire stale facts even if the file channel is disconnected or its revision is unchanged.
    const timer = setInterval(() => setNow(Date.now()), 2000);
    return () => clearInterval(timer);
  }, []);
  const items = array(resources.items).map(object);
  if (!items.length) return <Empty icon={<Layers size={20} />} title="还没有登记资源">Agent 查看你的数据、电脑和需要下载的东西后，会列在这里。</Empty>;
  const states = items.map(item => resourceObservation(item, observations, now));
  const ready = states.filter(item => item.state === 'ready').length;
  return <div className="resources">
    <p className="summary-line"><strong>{ready}</strong> / {items.length} 已就绪</p>
    {groupResources(items).map(([type, group]) => <Section key={type} title={type} aside={<span className="count">{group.length}</span>}>
      <ul className="resource-list">{group.map((resource, index) => {
        const { state, observation } = resourceObservation(resource, observations, now);
        return <ResourceRow key={text(resource.id, String(index))} resource={resource} state={state} detail={observation?.detail} modified={readableDate(observation?.modified_at)} size={readableSize(observation?.size ?? resource.size)} />;
      })}</ul>
    </Section>)}
  </div>;
}
