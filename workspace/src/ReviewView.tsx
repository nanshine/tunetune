import { useState } from 'react';
import { Check, HelpCircle, PencilLine } from 'lucide-react';
import { currentResponse, object, text } from './model';
import type { JsonObject, Snapshot } from './model';
import { excerpt, RecordView } from './RecordView';
import type { ReviewItem } from './useWorkspace';
import { PAGE_SIZE, sourceSha, sourceTotal, usePaged, useRowPage } from './rows';
import type { RowSource } from './rows';
import { t } from './i18n';

// A verdict keeps the reference it was given on, so pages read earlier need not stay loaded.
type Verdict = { verdict: ReviewItem['verdict']; edit?: string; note?: string; original?: unknown };

// Lists read as comma-separated words, so a beginner can correct tags without writing JSON.
function display(value: unknown): string {
  if (Array.isArray(value) && value.every(item => typeof item === 'string')) return value.join(t('，'));
  if (typeof value === 'string') return value;
  return JSON.stringify(value);
}
export function parseCorrection(original: unknown, edited: string): unknown {
  if (Array.isArray(original) && original.every(item => typeof item === 'string')) return edited.split(/[,，、;；\n]/).map(item => item.trim()).filter(Boolean);
  if (typeof original === 'string' || original === undefined) return edited.trim();
  try { return JSON.parse(edited); } catch { return edited.trim(); }
}

export function ReviewView({ files, source, onSubmit, delivered = false }: { files: Snapshot['files']; source: RowSource; onSubmit?: (items: ReviewItem[], sha: string) => Promise<unknown>; delivered?: boolean }) {
  const [verdicts, setVerdicts] = useState<Record<string, Verdict>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [page, setPage] = useState(0);
  const paged = usePaged();
  const answered = currentResponse(files, 'evaluation_review', paged);
  const reviewed = Object.keys(verdicts).length;
  const sha = sourceSha(source);
  const total = sourceTotal(source);
  const pages = Math.ceil(total / PAGE_SIZE);
  const loaded = useRowPage(source, Math.min(page, Math.max(0, pages - 1)));
  const rows: JsonObject[] = loaded.value ?? [];
  function set(id: string, value: Verdict | null) {
    setVerdicts(previous => {
      const next = { ...previous };
      if (value) next[id] = value; else delete next[id];
      return next;
    });
  }
  async function submit() {
    if (!onSubmit) return;
    setBusy(true); setError('');
    const items: ReviewItem[] = Object.entries(verdicts).map(([id, verdict]): ReviewItem => {
      if (verdict.verdict === 'correct') return { sample_id: id, verdict: 'correct', reference: parseCorrection(verdict.original, verdict.edit ?? ''), ...(verdict.note ? { note: verdict.note } : {}) };
      return { sample_id: id, verdict: verdict.verdict, ...(verdict.note ? { note: verdict.note } : {}) };
    });
    try { await onSubmit(items, sha); setVerdicts({}); }
    catch (cause) { setError(cause instanceof Error ? cause.message : t('提交失败，请重试。')); }
    finally { setBusy(false); }
  }
  if (answered) return <div className="response-bar done" role="status"><Check size={16} aria-hidden="true" /><div><strong>{t('审阅已提交')}</strong><p>{delivered ? t('共 {count} 条意见，已转给对话中的 Agent，它会据此更新参考答案。', { count: Array.isArray(answered.items) ? answered.items.length : 0 }) : t('共 {count} 条意见。回到对话告诉 Agent，它会据此更新参考答案。', { count: Array.isArray(answered.items) ? answered.items.length : 0 })}</p></div></div>;
  return <div className="review">
    <div className="review-head">
      <p>{t('这些参考答案由 Agent 起草，代表“好的输出”应该是什么样。逐条看一看：对的点确认，不对的直接改。')}</p>
      <div className="progress" aria-label={t('已看 {reviewed} / {total}', { reviewed, total })}><span style={{ width: `${total ? reviewed / total * 100 : 0}%` }} /></div>
      <p className="muted">{t('已看 {reviewed} / {total}', { reviewed, total })}</p>
    </div>
    {!loaded.value && <p className={loaded.error ? 'error-text' : 'muted'} role="status">{loaded.error || t('正在读取第 {page} 页…', { page: page + 1 })}</p>}
    <ol className="review-list" start={page * PAGE_SIZE + 1}>{rows.map((row, index) => {
      const id = text(row.sample_id, String(page * PAGE_SIZE + index));
      const verdict = verdicts[id];
      const input = object(row.input);
      return <li key={id} className={verdict ? `reviewed verdict-${verdict.verdict}` : ''}>
        <div className="review-sample">
          <p className="review-title">{text(input.title) || excerpt(row.input) || id}</p>
          {text(input.title) && <p className="review-excerpt">{excerpt(input.text ?? input.body ?? input.content, 120)}</p>}
          {!text(input.title) && typeof row.input !== 'string' && <details><summary>{t('查看完整输入')}</summary><RecordView value={row.input} /></details>}
        </div>
        <div className="review-answer">
          {verdict?.verdict === 'correct'
            ? <input autoFocus aria-label={t('修改 {id} 的参考答案', { id })} value={verdict.edit ?? ''} onChange={event => set(id, { ...verdict, edit: event.target.value })} />
            : <span className="review-reference">{display(row.reference)}</span>}
          {verdict?.verdict === 'question' && <input aria-label={t('对 {id} 的疑问', { id })} placeholder={t('哪里拿不准？')} value={verdict.note ?? ''} onChange={event => set(id, { ...verdict, note: event.target.value })} />}
        </div>
        <div className="review-actions" role="group" aria-label={t('{id} 的判断', { id })}>
          <button className={verdict?.verdict === 'confirm' ? 'active good' : ''} aria-pressed={verdict?.verdict === 'confirm'} onClick={() => set(id, verdict?.verdict === 'confirm' ? null : { verdict: 'confirm', original: row.reference })}><Check size={14} />{t('对')}</button>
          <button className={verdict?.verdict === 'correct' ? 'active' : ''} aria-pressed={verdict?.verdict === 'correct'} onClick={() => set(id, verdict?.verdict === 'correct' ? null : { verdict: 'correct', edit: display(row.reference), original: row.reference })}><PencilLine size={14} />{t('改')}</button>
          <button className={verdict?.verdict === 'question' ? 'active warn' : ''} aria-pressed={verdict?.verdict === 'question'} onClick={() => set(id, verdict?.verdict === 'question' ? null : { verdict: 'question', original: row.reference })}><HelpCircle size={14} />{t('拿不准')}</button>
        </div>
      </li>;
    })}</ol>
    {pages > 1 && <p className="pager page-pager"><button disabled={page === 0} onClick={() => setPage(page - 1)}>{t('上一页')}</button><span className="muted">{t('第 {page} / {pages} 页', { page: page + 1, pages })}</span><button disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>{t('下一页')}</button></p>}
    <div className="review-footer">
      {error && <p className="error-text" role="alert">{error}</p>}
      <span className="muted">{reviewed < total ? t('还有 {count} 条没看；没看的会保持草稿。', { count: total - reviewed }) : t('全部看完了。')}</span>
      <button className="primary" disabled={busy || !reviewed || !onSubmit} onClick={() => void submit()}>{t('提交审阅')}</button>
    </div>
  </div>;
}
