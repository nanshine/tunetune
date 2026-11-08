import { useState } from 'react';
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
  return text(row.title) || text(row.label) || excerpt(row.input) || text(row.sample_id) || t('样例 {number}', { number: index + 1 });
}
export function mediaUrl(path: unknown): string | null {
  if (typeof path !== 'string' || !path || /[\\\\\u0000-\u001f?#:%]/.test(path)) return null;
  const parts = path.split('/');
  if (parts.some(part => !part || part.startsWith('.') || /^(?:node_modules|secrets?|credentials)$/i.test(part)) || /\.(?:key|pem|env)$/i.test(path)) return null;
  return `api/media?path=${encodeURIComponent(path)}`;
}
// Image references inside a value, so a view can fetch the neighbouring samples' pictures ahead of time.
export function mediaUrls(value: unknown, found: string[] = [], depth = 0): string[] {
  if (depth > 8 || value === null || typeof value !== 'object') return found;
  if (Array.isArray(value)) { value.forEach(item => mediaUrls(item, found, depth + 1)); return found; }
  const record = object(value);
  if (record.type === 'image' && 'path' in record) { const url = mediaUrl(record.path); if (url) found.push(url); return found; }
  Object.values(record).forEach(item => mediaUrls(item, found, depth + 1));
  return found;
}
export function prefetchImages(values: unknown[]) {
  for (const url of values.flatMap(value => mediaUrls(value)).slice(0, 8)) { const image = new Image(); image.decoding = 'async'; image.src = url; }
}

// A new picture replaces the old one at once; a placeholder holds its place while it loads.
function MediaImage({ url, alt }: { url: string; alt: string }) {
  const [state, setState] = useState<'loading' | 'ready' | 'failed'>('loading');
  return <span className={`media-frame ${state}`}>
    <img src={url} alt={alt} onLoad={() => setState('ready')} onError={() => setState('failed')} />
    {state === 'failed' && <span className="muted">{t('图片无法读取')}</span>}
  </span>;
}

export function LinkedText({ value }: { value: string }) {
  return <>{value.split(/(https?:\/\/[^\s<>]+)/g).map((part, index) => {
    if (!/^https?:\/\//.test(part)) return part;
    const match = part.match(/^(.*?)([。，；、）)]+)?$/);
    const url = match?.[1] ?? part;
    return <span key={index}><a href={url} target="_blank" rel="noreferrer">{url}</a>{match?.[2]}</span>;
  })}</>;
}
// Measured fractions read at four significant digits; whole numbers such as IDs stay exactly as written.
export function readableNumber(value: number): string {
  if (Number.isInteger(value) || !Number.isFinite(value)) return String(value);
  return String(Math.abs(value) >= 1 ? Math.round(value * 1e4) / 1e4 : Number(value.toPrecision(4)));
}
export function RecordView({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value == null || value === '') return <span className="muted">{t('尚无内容')}</span>;
  if (typeof value !== 'object') return <span className="record-text">{typeof value === 'string' ? <LinkedText value={value} /> : typeof value === 'boolean' ? value ? t('是') : t('否') : typeof value === 'number' ? <span title={String(value)}>{readableNumber(value)}</span> : String(value)}</span>;
  if (depth > 8) return <span className="muted">{t('内容层级过深，请在 Agent 会话中查看。')}</span>;
  // Short word lists, such as tags or labels, read best inline.
  if (Array.isArray(value) && value.length && value.every(item => typeof item === 'string' && item.length <= 24)) return <span className="chips">{value.map((item, index) => <span className="chip" key={index}>{String(item)}</span>)}</span>;
  // Ranked candidates and similar lists of flat records read best as a table, one row each.
  const rows = Array.isArray(value) && value.length > 1 && value.every(item => item !== null && typeof item === 'object' && !Array.isArray(item) && Object.values(item).every(cell => cell === null || typeof cell !== 'object')) ? value.map(object) : null;
  const columns = rows ? [...new Set(rows.flatMap(row => Object.keys(row)))] : [];
  if (rows && columns.length <= 8) return <div className="record-table"><table><thead><tr>{columns.map(key => <th key={key} scope="col">{Object.hasOwn(fieldNames, key) ? fieldNames[key] : key}</th>)}</tr></thead>
    <tbody>{rows.map((row, index) => <tr key={index}>{columns.map(key => <td key={key}>{row[key] == null ? '' : <RecordView value={row[key]} depth={depth + 1} />}</td>)}</tr>)}</tbody></table></div>;
  if (Array.isArray(value)) return value.length ? <div className="record-list">{value.map((item, index) => <div className="record-item" key={index}><RecordView value={item} depth={depth + 1} /></div>)}</div> : <span className="muted">{t('暂无内容')}</span>;
  const record = object(value);
  if (['image', 'audio', 'video', 'file'].includes(text(record.type)) && 'path' in record) {
    const url = mediaUrl(record.path);
    if (!url) return <span className="muted">{t('此附件路径不可预览，请在会话中核对。')}</span>;
    const label = text(record.title) || text(record.path).split('/').at(-1) || t('附件');
    return <figure className="record-media">{record.type === 'image' ? <MediaImage key={url} url={url} alt={text(record.alt, label)} /> : record.type === 'audio' ? <audio key={url} controls preload="none" src={url} aria-label={label} /> : record.type === 'video' ? <video key={url} controls preload="none" src={url} aria-label={label} /> : <a href={url} target="_blank" rel="noreferrer">{label}</a>}<figcaption>{label}</figcaption></figure>;
  }
  return <dl className="record-fields">{Object.entries(record).map(([key, item]) => <div key={key}><dt>{Object.hasOwn(fieldNames, key) ? fieldNames[key] : key}</dt><dd><RecordView value={item} depth={depth + 1} /></dd></div>)}</dl>;
}
