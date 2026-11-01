import { useEffect, useState } from 'react';
import { parseSnapshot } from './model';
import type { Snapshot } from './model';

export function useWorkspace() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const response = await fetch('/api/state', { signal: controller.signal, cache: 'no-store' });
        if (!response.ok) throw new Error(`读取失败（HTTP ${response.status}）`);
        const next = parseSnapshot(await response.json());
        if (!controller.signal.aborted) {
          setSnapshot(previous => previous?.revision === next.revision && previous?.error === next.error ? previous : next);
          setConnectionError(null);
        }
      } catch (error) {
        if (!controller.signal.aborted) setConnectionError(error instanceof Error ? error.message : '无法连接本地研究空间服务');
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
      if (response.status === 409) throw new Error('项目记录已变更或正在写入，请取消后重新编辑。');
      throw new Error(`名称保存失败（HTTP ${response.status}），请重试。`);
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
  return { snapshot, connectionError, renameProject };
}
