import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useWorkspace } from './useWorkspace';
import type { Snapshot } from './model';

// A small hook harness tests the file channel without introducing a DOM dependency.
const hooks = vi.hoisted(() => ({ values: [] as unknown[], cursor: 0, mounted: false, cleanup: undefined as (() => void) | undefined }));
vi.mock('react', () => ({
  useState: (initial: unknown) => {
    const index = hooks.cursor++;
    if (!(index in hooks.values)) hooks.values[index] = initial;
    return [hooks.values[index], (next: unknown) => { hooks.values[index] = typeof next === 'function' ? next(hooks.values[index]) : next; }];
  },
  useEffect: (effect: () => (() => void)) => {
    if (!hooks.mounted) { hooks.mounted = true; hooks.cleanup = effect(); }
  },
}));
function render() { hooks.cursor = 0; return useWorkspace(); }
const snapshot: Snapshot = {
  files: { 'project.json': { content: { schema_version: 4, name: '研究', deliveries: [] }, sha256: 'a'.repeat(64) } },
  revision: 'stable', synced_at: '2026-11-01T12:00:00Z', error: null,
  observations: { checked_at: '2026-11-01T12:00:00Z', items: [{ id: 'data', state: 'ready' }] },
};
const response = (content: unknown) => ({ ok: true, json: async () => content });

beforeEach(() => {
  hooks.values = []; hooks.cursor = 0; hooks.mounted = false; hooks.cleanup = undefined;
  vi.useFakeTimers();
});
afterEach(() => { hooks.cleanup?.(); vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('file channel polling', () => {
  it('updates monitor observations even when research file revision does not change', async () => {
    const changed: Snapshot = { ...snapshot, observations: { checked_at: '2026-11-01T12:00:06Z', items: [{ id: 'data', state: 'changed', size: '2 KB' }] } };
    const fetch = vi.fn().mockResolvedValueOnce(response(snapshot)).mockResolvedValue(response(changed));
    vi.stubGlobal('fetch', fetch);
    render();
    await vi.advanceTimersByTimeAsync(0);
    expect(render().snapshot?.observations?.items[0].state).toBe('ready');
    await vi.advanceTimersByTimeAsync(2000);
    const updated = render().snapshot;
    expect(updated?.observations?.items[0]).toEqual({ id: 'data', state: 'changed', size: '2 KB' });
    expect(updated?.revision).toBe('stable');
    await vi.advanceTimersByTimeAsync(2000);
    expect(render().snapshot).toBe(updated);
  });
  it('preserves the last usable snapshot during errors and resumes polling', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(response(snapshot)).mockRejectedValueOnce(new Error('离线')).mockResolvedValue(response(snapshot));
    vi.stubGlobal('fetch', fetch);
    render();
    await vi.advanceTimersByTimeAsync(0);
    const previous = render().snapshot;
    await vi.advanceTimersByTimeAsync(2000);
    expect(render().snapshot).toBe(previous);
    expect(render().connectionError).toBe('离线');
    await vi.advanceTimersByTimeAsync(2000);
    expect(render().connectionError).toBeNull();
    hooks.cleanup?.();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(fetch).toHaveBeenCalledTimes(3);
  });
  it('retains expected-byte conflict detection for the only write action', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(response(snapshot)).mockResolvedValue({ ok: false, status: 409 });
    vi.stubGlobal('fetch', fetch);
    render();
    await vi.advanceTimersByTimeAsync(0);
    await expect(render().renameProject('新名称', 'a'.repeat(64))).rejects.toThrow('项目记录已变更');
    expect(fetch).toHaveBeenLastCalledWith('/api/project/name', expect.objectContaining({ method: 'POST', body: JSON.stringify({ name: '新名称', expected_sha256: 'a'.repeat(64) }) }));
    expect(render().snapshot?.files['project.json'].content).toEqual({ schema_version: 4, name: '研究', deliveries: [] });
  });
});
