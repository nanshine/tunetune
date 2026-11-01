import { useId, useState } from 'react';
import type { FormEvent } from 'react';
import type { FeedbackTarget, Snapshot } from './model';

export type Draft = { id: string; text: string; choice: string; hash: string | null };
export function FeedbackForm({ target, files, draft, busy, onBusyChange, onChange, onSaved, allowChoiceOnly = false, submitLabel = '保存反馈', compact = false }: {
  target: FeedbackTarget; files: Snapshot['files']; draft?: Draft; busy: boolean;
  onBusyChange: (busy: boolean) => void; onChange: (draft: Draft) => void; onSaved: (id: string) => void;
  allowChoiceOnly?: boolean; submitLabel?: string; compact?: boolean;
}) {
  const [message, setMessage] = useState('');
  const [failed, setFailed] = useState(false);
  const choiceName = useId();
  const currentHash = target.target ? files[target.target]?.sha256 ?? null : null;
  const stale = draft !== undefined && draft.hash !== currentHash;
  const choiceRequired = !!(target.options?.length || target.choices?.length);
  const validChoice = !choiceRequired || !!(draft?.choice && (target.choices?.some(choice => choice.value === draft.choice) || target.options?.includes(draft.choice)));
  const feedbackText = draft?.text.trim() || (allowChoiceOnly && validChoice ? `${target.title}：${draft?.choice}` : '');
  function update(patch: Partial<Draft>) {
    setMessage('');
    onChange({ text: '', choice: '', hash: currentHash, ...draft, ...patch, id: crypto.randomUUID() });
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!feedbackText || stale || busy || !validChoice) return;
    onBusyChange(true); setMessage(''); setFailed(false);
    try {
      const response = await fetch('/api/feedback', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: draft!.id, kind: target.kind, text: feedbackText, target: target.target, target_sha256: draft!.hash,
          ...(target.request_id ? { request_id: target.request_id } : {}),
          ...(draft!.choice ? { choice: draft!.choice } : {}),
          ...(target.sample_id ? { sample_id: target.sample_id } : {}),
        }),
      });
      if (!response.ok) throw new Error(response.status === 409 ? '依据已变化或回答已保存，请核对后再提交。' : `保存失败（HTTP ${response.status}），草稿已保留，可重试。`);
      onSaved(draft!.id); setMessage('已保存，待 Agent 处理。请在会话中让 Agent 读取反馈。');
    } catch (error) { setFailed(true); setMessage(error instanceof Error ? error.message : '保存失败，草稿已保留。'); }
    finally { onBusyChange(false); }
  }
  return <form className={`feedback-form ${compact ? 'compact' : ''}`} onSubmit={submit}>
    <h3>{target.title}</h3>
    {!compact && <p className="muted">只保存原始意见，不直接修改研究文件或启动训练。</p>}
    {!compact && target.target && <p className="file-path">{target.target}</p>}
    {!!target.options?.length && <label>选择回答<select value={draft?.choice ?? ''} onChange={event => update({ choice: event.target.value })} required disabled={busy}><option value="">请选择</option>{target.options.map(option => <option key={option}>{option}</option>)}</select></label>}
    {!!target.choices?.length && <fieldset className="choice-fieldset" disabled={busy}><legend className="sr-only">{target.title}</legend><div className="choice-options">{target.choices.map(choice => <label className={`choice-option ${draft?.choice === choice.value ? 'selected' : ''}`} key={choice.value}><input type="radio" name={choiceName} value={choice.value} checked={draft?.choice === choice.value} onChange={event => update({ choice: event.target.value })} required /><span>{choice.label}</span></label>)}</div></fieldset>}
    <label htmlFor={`${choiceName}-text`}>{target.kind === 'response' ? '回答与说明' : allowChoiceOnly ? '反馈（可选）' : '反馈内容'}</label>
    <textarea id={`${choiceName}-text`} value={draft?.text ?? ''} onChange={event => update({ text: event.target.value })} placeholder={allowChoiceOnly ? '补充本例观察或验收意见…' : '写下你的观察、修改建议或需要确认的问题…'} maxLength={16000} required={!allowChoiceOnly} rows={compact ? 3 : 6} disabled={busy} />
    {stale && <div className="notice" role="alert">依据文件已经更新，草稿没有被覆盖。请阅读新内容后确认。<button type="button" onClick={() => update({ hash: currentHash, id: crypto.randomUUID() })}>已核对，使用新版本</button></div>}
    <button className="primary" disabled={busy || stale || !feedbackText || !validChoice}>{busy ? '正在保存…' : submitLabel}</button>
    <p role={failed ? 'alert' : 'status'} className={failed ? 'error-text' : 'success-text'}>{message}</p>
  </form>;
}
