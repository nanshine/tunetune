import { array, object, text } from './model';
import type { JsonObject } from './model';

export function GoalView({ goal }: { goal: JsonObject }) {
  return <div className="project-brief">
    <p className="goal-summary">{text(goal.summary) || '和 Agent 聊聊你想完成的事，目标会逐步整理在这里。'}</p>
    {array(goal.sections).map(object).map((section, index) => <section className="panel-section" key={index}><h3>{text(section.title)}</h3><p className="brief-text">{text(section.body)}</p></section>)}
    {!!array(goal.examples).length && <section className="panel-section"><h3>具体例子</h3>{array(goal.examples).map(object).map((example, index) => <article className="brief-example" key={text(example.id, String(index))}>
      <h4>{text(example.title) || `例子 ${index + 1}`}</h4>
      <div><span className="section-label">提供的内容</span><p className="brief-text">{text(example.input) || '待一起补充'}</p></div>
      <div><span className="section-label">希望得到</span><p className="brief-text">{text(example.expected_output) || '待一起确认'}</p></div>
      {!!text(example.source) && <details><summary>来源</summary><p className="brief-text">{text(example.source)}</p></details>}
    </article>)}</section>}
    {!!text(goal.proposal) && <section className="panel-section proposal"><h3>初步提案</h3><p className="brief-text">{text(goal.proposal)}</p></section>}
    {typeof goal.revision === 'number' && <p className="muted">修订 {goal.revision}</p>}
  </div>;
}

const resourceTypes: Record<string, string> = { data: '数据', dataset: '数据', model: '模型', environment: '环境', hardware: '硬件', tool: '工具', other: '其他' };
export const resourceStates: Record<string, string> = { unknown: '待了解', available: '可获取', preparing: '准备中', ready: '已就绪', unavailable: '暂不可用' };
const detailLabels: Record<string, string> = { source: '来源', path: '项目位置', location: '位置', version: '版本', checked_at: '检查时间', notes: '说明' };

export function ResourcesView({ resources }: { resources: JsonObject }) {
  const items = array(resources.items).map(object);
  return <div className="resource-list">{!items.length && <p className="muted">Agent 会查看现有材料和环境，并将找到的可用资源整理在这里。</p>}
    {items.map((resource, index) => {
      const state = text(resource.status);
      return <article className="brief-resource" key={text(resource.id, String(index))}>
        <div className="resource-heading"><h3>{text(resource.title)}</h3><span className={`resource-state ${Object.hasOwn(resourceStates, state) ? state : 'unknown'}`}><i aria-hidden="true" />{resourceStates[state] ?? '待了解'}</span></div>
        <span className="section-label">{resourceTypes[text(resource.type)] ?? text(resource.type)}</span>
        <p className="brief-text">{text(resource.purpose)}</p>
        {Object.keys(detailLabels).some(key => !!text(resource[key])) && <details><summary>查看详情</summary><dl className="resource-details">{Object.entries(detailLabels).filter(([key]) => !!text(resource[key])).map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{text(resource[key])}</dd></div>)}</dl></details>}
      </article>;
    })}
  </div>;
}
