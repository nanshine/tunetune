import { object, text } from './model';
import type { JsonObject } from './model';

// This renderer is for user-facing content (inputs, outputs and rubrics), never whole records.
const labels: Record<string, string> = { input: '输入', output: '输出', reference: '参考输出', text: '内容', message: '留言', question: '问题', answer: '回答', category: '类别', score: '得分', description: '说明' };
export function sampleLabel(row: JsonObject, index: number): string {
  return text(row.title) || text(row.label) || `样例 ${index + 1}`;
}
export function RecordView({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value == null || value === '') return <span className="muted">尚无内容</span>;
  if (typeof value !== 'object') return <span className="record-text">{typeof value === 'boolean' ? value ? '是' : '否' : String(value)}</span>;
  if (depth > 8) return <span className="muted">内容层级过深，请在 Agent 会话中查看。</span>;
  if (Array.isArray(value)) return value.length ? <div className="record-list">{value.map((item, index) => <div className="record-item" key={index}><RecordView value={item} depth={depth + 1} /></div>)}</div> : <span className="muted">暂无内容</span>;
  return <dl className="record-fields">{Object.entries(object(value)).map(([key, item]) => <div key={key}><dt>{Object.hasOwn(labels, key) ? labels[key] : key}</dt><dd><RecordView value={item} depth={depth + 1} /></dd></div>)}</dl>;
}
