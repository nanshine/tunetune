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
  return { snapshot, connectionError };
}
