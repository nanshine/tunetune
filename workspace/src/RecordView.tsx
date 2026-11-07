import { object, text } from './model';
import type { JsonObject } from './model';
import { labels, t } from './i18n';

const fieldNames: Record<string, string> = labels({ input: '输入', output: '输出', reference: '参考输出', title: '标题', text: '正文', body: '正文', message: '留言', question: '问题', answer: '回答', category: '类别', score: '得分', description: '说明', tags: '标签' });
// A readable one-line name for an input: its own title, then the start of its text.
export function excerpt(value: unknown, length = 48): string {
  if (typeof value === 'string') return value.replace(/\s+/g, ' ').trim().slice(0, length);
  const record = object(value);
  const first = text(record.title) || text(record.name) || text(record.question) || text(record.text) || text(record.content) || text(record.message);
  return first.replace(/\s+/g, ' ').trim().slice(0, length);
}
export function sampleLabel(row: JsonObject, index: number): string {
  return text(row.title) || text(row.label) || excerpt(row.input) || t('样例 {number}', { number: index + 1 });
}
export function mediaUrl(path: unknown): string | null {
  if (typeof path !== 'string' || !path || /[\\\\\u0000-\u001f?#:%]/.test(path)) return null;
  const parts = path.split('/');
  if (parts.some(part => !part || part.startsWith('.') || /^(?:node_modules|secrets?|credentials)$/i.test(part)) || /\.(?:key|pem|env)$/i.test(path)) return null;
  return `/api/media?path=${encodeURIComponent(path)}`;
}
export function LinkedText({ value }: { value: string }) {
  return <>{value.split(/(https?:\/\/[^\s<>]+)/g).map((part, index) => {
    if (!/^https?:\/\//.test(part)) return part;
    const match = part.match(/^(.*?)([。，；、）)]+)?$/);
    const url = match?.[1] ?? part;
    return <span key={index}><a href={url} target="_blank" rel="noreferrer">{url}</a>{match?.[2]}</span>;
  })}</>;
}
export function RecordView({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value == null || value === '') return <span className="muted">{t('尚无内容')}</span>;
  if (typeof value !== 'object') return <span className="record-text">{typeof value === 'string' ? <LinkedText value={value} /> : typeof value === 'boolean' ? value ? t('是') : t('否') : String(value)}</span>;
  if (depth > 8) return <span className="muted">{t('内容层级过深，请在 Agent 会话中查看。')}</span>;
  // Short word lists, such as tags or labels, read best inline.
  if (Array.isArray(value) && value.length && value.every(item => typeof item === 'string' && item.length <= 24)) return <span className="chips">{value.map((item, index) => <span className="chip" key={index}>{String(item)}</span>)}</span>;
  if (Array.isArray(value)) return value.length ? <div className="record-list">{value.map((item, index) => <div className="record-item" key={index}><RecordView value={item} depth={depth + 1} /></div>)}</div> : <span className="muted">{t('暂无内容')}</span>;
  const record = object(value);
  if (['image', 'audio', 'video', 'file'].includes(text(record.type)) && 'path' in record) {
    const url = mediaUrl(record.path);
    if (!url) return <span className="muted">{t('此附件路径不可预览，请在会话中核对。')}</span>;
    const label = text(record.title) || text(record.path).split('/').at(-1) || t('附件');
    return <figure className="record-media">{record.type === 'image' ? <img loading="lazy" src={url} alt={text(record.alt, label)} /> : record.type === 'audio' ? <audio controls preload="none" src={url} aria-label={label} /> : record.type === 'video' ? <video controls preload="none" src={url} aria-label={label} /> : <a href={url} target="_blank" rel="noreferrer">{label}</a>}<figcaption>{label}</figcaption></figure>;
  }
  return <dl className="record-fields">{Object.entries(record).map(([key, item]) => <div key={key}><dt>{Object.hasOwn(fieldNames, key) ? fieldNames[key] : key}</dt><dd><RecordView value={item} depth={depth + 1} /></dd></div>)}</dl>;
}
