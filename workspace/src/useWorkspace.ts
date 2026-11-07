import { useEffect, useState } from 'react';
import { parseSnapshot } from './model';
import type { Snapshot } from './model';
import { labels, t } from './i18n';

export function useWorkspace() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const response = await fetch('/api/state', { signal: controller.signal, cache: 'no-store' });
        if (!response.ok) throw new Error(t('读取失败（HTTP {status}）', { status: response.status }));
        const next = parseSnapshot(await response.json());
        if (!controller.signal.aborted) {
          // Monitor updates are independent of the research-file revision.
          setSnapshot(previous => previous?.revision === next.revision && previous?.error === next.error && JSON.stringify(previous?.observations) === JSON.stringify(next.observations) ? previous : next);
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
    const response = await fetch('/api/project/name', {
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
  return post<{ id: string }>('/api/responses', body);
}
export function runAcceptance(experimentIds: string[]) {
  return post<{ id: string; state: string }>('/api/acceptance/run', { experiments: experimentIds });
}
export function loadModel(experiment: string) {
  return post<{ state: string }>('/api/models/load', { experiment });
}
export function unloadModel(experiment: string) {
  return post<unknown>('/api/models/unload', { experiment });
}
export function tryModel(experiment: string, input: unknown) {
  return post<{ output?: unknown; error?: string; log_tail?: string; elapsed_seconds?: number }>('/api/try', { experiment, input });
}
