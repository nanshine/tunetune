import { useEffect, useState } from 'react';
import { parseSnapshot } from './model';
import type { Snapshot } from './model';
import { labels, t } from './i18n';
import { ATTACHMENT_LIMIT_MB, attachmentExtension, formatLabels } from './attachments';
import type { AttachmentKind } from './attachments';

export function useWorkspace() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    // The records the panel holds; while their revision is unchanged the service sends only the live parts.
    let held: Snapshot | null = null;
    async function refresh() {
      try {
        const since = held && !held.error ? `?since=${held.revision}` : '';
        const response = await fetch(`api/state${since}`, { signal: controller.signal, cache: 'no-store' });
        if (!response.ok) throw new Error(t('读取失败（HTTP {status}）', { status: response.status }));
        const next = mergeSnapshot(held, await response.json());
        if (!controller.signal.aborted) {
          held = next;
          setSnapshot(previous => sameSnapshot(previous, next) ? previous : next);
          setConnectionError(null);
        }
      } catch (error) {
        if (!controller.signal.aborted) setConnectionError(error instanceof Error ? error.message : t('无法连接本地研究空间服务'));
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(refresh, 2000);
      }
    }
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, []);
  async function renameProject(name: string, expectedSha256: string) {
    const response = await fetch('api/project/name', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, expected_sha256: expectedSha256 }),
    });
    if (!response.ok) {
      if (response.status === 409) throw new Error(t('项目记录已变更或正在写入，请取消后重新编辑。'));
      throw new Error(t('名称保存失败（HTTP {status}），请重试。', { status: response.status }));
    }
    const saved: { name: string; sha256: string } = await response.json();
    setSnapshot(previous => previous ? {
      ...previous,
      files: { ...previous.files, 'project.json': {
        content: { ...(previous.files['project.json'].content as Record<string, unknown>), name: saved.name },
        sha256: saved.sha256,
      } },
    } : previous);
  }
  return { snapshot, connectionError, renameProject, submitResponse, runAcceptance, tryModel };
}

// An unchanged reply carries no records; it reuses the ones held for that exact revision.
export function mergeSnapshot(held: Snapshot | null, raw: unknown): Snapshot {
  const value = raw !== null && typeof raw === 'object' && !Array.isArray(raw) ? raw as Record<string, unknown> : {};
  if (value.unchanged !== true) return parseSnapshot(value);
  if (!held || held.revision !== value.revision) throw new Error(t('文件通道返回了无效格式'));
  const { unchanged: _unchanged, ...live } = value;
  return parseSnapshot({ ...live, files: held.files, paged: held.paged, omitted: held.omitted });
}
// Model loading, runs and the Agent's focus change without the records, so they are compared as well.
export function sameSnapshot(previous: Snapshot | null, next: Snapshot): boolean {
  if (!previous || previous.revision !== next.revision || previous.error !== next.error || previous.files !== next.files) return false;
  const live = (item: Snapshot) => JSON.stringify([item.observations, item.view, item.acceptance, item.models, item.conversation]);
  return live(previous) === live(next);
}

const failures: Record<number, string> = labels({ 400: '内容不完整，请检查后重试。', 409: '内容刚被更新或有任务正在运行，请稍后再试。', 503: '这个研究目录还没有安装研究工具。', 504: '模型没有在限定时间内给出结果。' });
async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const value = await response.json().catch(() => ({}));
  // A notice is written for the person; other server errors are technical and get a plain explanation.
  if (!response.ok) throw new Error(typeof value.notice === 'string' ? value.notice : failures[response.status] ?? t('请求失败（HTTP {status}）', { status: response.status }));
  return value as T;
}
export type ReviewItem = { sample_id: string; verdict: 'confirm' | 'correct' | 'question'; reference?: unknown; note?: string };
export type AcceptanceItem = { sample_id: string; experiment_id: string; verdict: 'good' | 'bad'; note?: string };
export function submitResponse(body: { kind: 'proposal' | 'plan' | 'evaluation_review' | 'acceptance'; decision: string; target_sha256: string; note?: string; items?: ReviewItem[] | AcceptanceItem[] }) {
  return post<{ id: string }>('api/responses', body);
}
export function runAcceptance(experimentIds: string[]) {
  return post<{ id: string; state: string }>('api/acceptance/run', { experiments: experimentIds });
}
export function loadModel(experiment: string) {
  return post<{ state: string }>('api/models/load', { experiment });
}
export function unloadModel(experiment: string) {
  return post<unknown>('api/models/unload', { experiment });
}
// An attachment for a trial input; the service keeps it as panel scratch and answers with its reference.
export async function uploadTrialAttachment(file: File, kind: AttachmentKind): Promise<Record<string, unknown>> {
  const ext = attachmentExtension(file, kind);
  if (!ext) throw new Error(formatLabels[kind]);
  const response = await fetch(`api/try/media?${new URLSearchParams({ kind, ext })}`, { method: 'POST', headers: { 'Content-Type': file.type || 'application/octet-stream' }, body: file });
  const value = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(response.status === 413 ? t('这个文件不能超过 {mb} MB。', { mb: ATTACHMENT_LIMIT_MB[kind] }) : response.status === 415 ? (/content does not match/.test(String(value.error)) ? t('文件内容和它的格式不符。') : formatLabels[kind]) : t('上传失败'));
  if (value.type !== kind || typeof value.path !== 'string') throw new Error(t('文件通道返回了无效格式'));
  return value;
}
export function tryModel(experiment: string, input: unknown) {
  return post<{ output?: unknown; error?: string; log_tail?: string; elapsed_seconds?: number }>('api/try', { experiment, input });
}
