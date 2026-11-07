import { useState } from 'react';
import type { ReactNode } from 'react';
import { CheckCircle2, CircleAlert } from 'lucide-react';
import { currentResponse, responseTargets, text } from './model';
import type { ResponseKind, Snapshot } from './model';
import { t } from './i18n';

export function Section({ title, icon, aside, children }: { title: string; icon?: ReactNode; aside?: ReactNode; children: ReactNode }) {
  return <section className="section"><div className="section-head"><h3>{icon}{title}</h3>{aside}</div>{children}</section>;
}

export function Empty({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return <div className="empty"><span className="empty-icon" aria-hidden="true">{icon}</span><p className="empty-title">{title}</p>{children && <p className="empty-text">{children}</p>}</div>;
}

function readableTime(value: unknown): string {
  const time = Date.parse(text(value));
  return Number.isFinite(time) ? new Date(time).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
}

// A decision the Agent asked for in conversation can be answered here; the answer is bound to the exact file shown.
export function ResponseBar({ files, kind, waiting, prompt, approve, decisions, onSubmit }: {
  files: Snapshot['files']; kind: ResponseKind; waiting: string | null; prompt: string; approve: string;
  decisions: { approve: string; revise: string }; onSubmit: (decision: string, note: string, sha: string) => Promise<unknown>;
}) {
  const [revising, setRevising] = useState(false);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const answer = currentResponse(files, kind);
  const target = files[responseTargets[kind]];
  if (answer) {
    const approved = answer.decision === decisions.approve;
    return <div className={`response-bar ${approved ? 'done' : 'noted'}`} role="status"><CheckCircle2 size={16} aria-hidden="true" /><div><strong>{approved ? t('你已确认') : t('你已请求修改')}</strong><span className="muted"> · {readableTime(answer.created_at)}</span>{text(answer.note) && <p>{text(answer.note)}</p>}<p className="muted">{t('回到对话告诉 Agent 一声，它会按你的回复继续。')}</p></div></div>;
  }
  if (!waiting || !target) return null;
  async function send(decision: string) {
    setBusy(true); setError('');
    try { await onSubmit(decision, note.trim(), target!.sha256); }
    catch (cause) { setError(cause instanceof Error ? cause.message : t('提交失败，请重试。')); }
    finally { setBusy(false); }
  }
  return <div className="response-bar waiting">
    <CircleAlert size={16} aria-hidden="true" />
    <div className="response-main">
      <strong>{waiting}</strong>
      <p>{prompt}</p>
      {revising && <textarea value={note} onChange={event => setNote(event.target.value)} rows={3} placeholder={t('写下想改的地方，例如标签再少一些')} aria-label={t('修改意见')} />}
      {error && <p className="error-text" role="alert">{error}</p>}
      <div className="response-actions">
        {revising ? <><button className="primary" disabled={busy || !note.trim()} onClick={() => void send(decisions.revise)}>{t('发送修改意见')}</button><button onClick={() => setRevising(false)} disabled={busy}>{t('取消')}</button></>
          : <><button className="primary" disabled={busy} onClick={() => void send(decisions.approve)}>{approve}</button><button onClick={() => setRevising(true)} disabled={busy}>{t('需要修改')}</button></>}
      </div>
    </div>
  </div>;
}
