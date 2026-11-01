import { array, object, text } from './model';

const labels: Record<string, string> = {
  context: '使用情境', expected_result: '期望结果', examples: '具体例子', revision: '目标修订', sources: '来源', input: '输入', output: '输出', reference: '参考输出',
  name: '名称', title: '名称', type: '类型', path: '位置', version: '版本', state: '执行状态', status: '状态', updated_at: '更新时间', checked_at: '最近检查',
  description: '说明', metrics: '指标', datasets: '数据集', rubric: '评分规则', command: '执行命令', direction: '优化方向', label: '显示名称',
  hypothesis: '假设', resources: '所需资源', parent_experiment_id: '起点实验', evaluation_version: '评测版本', goal_revision: '目标修订',
  artifact_id: '产物', experiment_id: '来源实验', assessment_ids: '关联评测', notes: '说明', constraints: '限制', source: '来源', error: '错误',
  disposition: '处理决定', reason: '理由', changes: '相关改动', text: '原始意见', prompt: '问题', options: '选项', created_at: '保存时间', completed_at: '完成时间',
  id: '标识', items: '条目', limitations: '使用限制', purpose: '用途', sha256: '内容哈希', gpu_model: 'GPU 型号', gpu_utilization: 'GPU 利用率', memory: '显存', disk_free: '磁盘剩余', collected_at: '采集时间',
};
export function RecordView({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value == null || value === '') return <span className="muted">尚未填写</span>;
  if (typeof value !== 'object') return <span className="record-text">{String(value)}</span>;
  if (depth > 5) return <pre>{JSON.stringify(value, null, 2)}</pre>;
  if (Array.isArray(value)) return value.length ? <div className="record-list">{array(value).map((item, index) => <div className="record-item" key={text(object(item).id, String(index))}><RecordView value={item} depth={depth + 1} /></div>)}</div> : <span className="muted">暂无记录</span>;
  return <dl className="record-fields">{Object.entries(object(value)).map(([key, item]) => <div key={key}><dt>{Object.hasOwn(labels, key) ? labels[key] : key}</dt><dd><RecordView value={item} depth={depth + 1} /></dd></div>)}</dl>;
}
