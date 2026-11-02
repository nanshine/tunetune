import { describe, expect, it } from 'vitest';
import { assessments, experiments, layout, parseSnapshot, statusLabel } from './model';
import type { ResearchFile, Snapshot } from './model';
const file = (content: unknown): ResearchFile => ({ content, sha256: 'a'.repeat(64) });
const files = {
  'project.json': file({ schema_version: 1 }),
  'experiments/exp-1/config.json': file({ title: '初次训练' }),
  'experiments/exp-1/status.json': file({ state: 'succeeded' }),
  'assessments/a/config.json': file({ experiment_id: 'exp-1', evaluation_version: 'v1' }),
  'assessments/a/result.json': file({ state: 'failed', metrics: {} }),
  'assessments/b/config.json': file({ experiment_id: 'exp-1', evaluation_version: 'v2' }),
  'assessments/b/result.json': file({ state: 'succeeded', metrics: { accuracy: 0.9, invalid: '0.5' } }),
};
describe('research file contract', () => {
  it('validates the external snapshot envelope', () => {
    expect(parseSnapshot({ files, revision: '1', synced_at: '', error: null }).files).toEqual(files);
    expect(() => parseSnapshot({ files: [], revision: '1', synced_at: '', error: null })).toThrow();
    expect(() => parseSnapshot({ files: { 'project.json': file({ schema_version: 2 }) }, revision: '1', synced_at: '', error: null })).toThrow();
  });
  it('rejects malformed structured records', () => {
    for (const bad of [{ 'goal.json': file({ examples: 'bad' }) }, { 'test.json': file([]) }, { 'outputs.jsonl': file([null]) }]) {
      expect(() => parseSnapshot({ files: { ...files, ...bad }, revision: '1', synced_at: '', error: null })).toThrow();
    }
  });
  it('keeps successful training separate from a failed assessment and different versions', () => {
    expect(experiments(files)[0].state).toBe('succeeded');
    const results = assessments(files);
    expect(results.map(item => item.version)).toEqual(['v1', 'v2']);
    expect(results.map(item => item.state)).toEqual(['failed', 'succeeded']);
    expect(results[1].metrics).toEqual({ accuracy: 0.9 });
  });
  it('syncs config-only and recorded pending/running assessments without result metrics', () => {
    let current = parseSnapshot({ files, revision: 'initial', synced_at: '', error: null });
    for (const state of [undefined, 'pending', 'running']) {
      const revision = state ?? 'config-only';
      const nextFiles: Snapshot['files'] = {
        ...files,
        'assessments/c/config.json': file({ experiment_id: 'exp-1', evaluation_version: 'v2', metrics: { accuracy: 1 } }),
        'goal.json': file({ examples: [{ id: revision }] }),
        'experiments/exp-1/status.json': file({ state: 'failed' }),
      };
      if (state) nextFiles['assessments/c/status.json'] = file({ state, metrics: { accuracy: 0.5 } });
      const next = parseSnapshot({ files: nextFiles, revision, synced_at: '', error: null });
      expect(next.revision).not.toBe(current.revision);
      expect(next.files['goal.json'].content).toEqual({ examples: [{ id: revision }] });
      expect(experiments(next.files)[0].state).toBe('failed');
      const assessment = assessments(next.files).find(item => item.id === 'c');
      expect(assessment).toMatchObject({ experimentId: 'exp-1', version: 'v2', state: state ?? 'pending' });
      expect(assessment?.metrics).toEqual({});
      expect(assessments(next.files).filter(item => item.id !== 'c')).toEqual(assessments(files));
      current = next;
    }
    expect(statusLabel('running')).toBe('记录为运行中');
  });
  it.each(['failed', 'succeeded', 'cancelled'])('prefers a %s result over stale running status', state => {
    const metrics = state === 'succeeded' ? { accuracy: 0.9 } : {};
    const recorded = file({ state: 'running', metrics: { accuracy: 1 } });
    const complete = parseSnapshot({
      files: { ...files, 'assessments/b/status.json': recorded, 'assessments/b/result.json': file({ state, metrics }) },
      revision: 'complete', synced_at: '', error: null,
    });
    expect(complete.files['assessments/b/status.json']).toEqual(recorded);
    expect(assessments(complete.files).find(item => item.id === 'b')).toMatchObject({ state, metrics });
  });
  it('rejects malformed assessment records rather than replacing the last usable snapshot', () => {
    const malformed: unknown[] = [null, [], 'bad', {}, { state: null }, { state: true }, { state: 1 }, { state: [] }, { state: {} }, { state: 'unknown' }];
    for (const completed of [false, true]) {
      const goodFiles: Snapshot['files'] = {
        ...files,
        'assessments/c/config.json': file({ experiment_id: 'exp-1' }),
        'assessments/c/status.json': file({ state: 'running' }),
      };
      if (completed) goodFiles['assessments/c/result.json'] = file({ state: 'succeeded', metrics: { accuracy: 0.9 } });
      const good = parseSnapshot({ files: goodFiles, revision: 'good', synced_at: 'last-sync', error: null });
      let current = good;
      for (const [filename, invalidStates] of [
        ['status.json', ['succeeded', 'failed', 'cancelled']],
        ['result.json', ['pending', 'running']],
      ] as const) {
        const path = `assessments/c/${filename}`;
        for (const content of [...malformed, ...invalidStates.map(state => ({ state }))]) {
          expect(() => {
            current = parseSnapshot({
              files: { ...goodFiles, [path]: file(content), 'goal.json': file({ examples: [{ id: 'changed' }] }) },
              revision: 'bad', synced_at: 'new-sync', error: null,
            });
          }).toThrow(path);
          expect(current).toBe(good);
        }
      }
      current = parseSnapshot({ files: goodFiles, revision: 'recovered', synced_at: 'new-sync', error: null });
      expect(current.revision).toBe('recovered');
      expect(assessments(current.files).find(item => item.id === 'c')?.state).toBe(completed ? 'succeeded' : 'running');
    }
  });
  it('uses each evaluation definition for metric labels and display ordering', () => {
    const configured = {
      ...files,
      'workspace.json': file({ metric_columns: ['cost', 'accuracy'] }),
      'evaluation/versions/v2/definition.json': file({ metrics: [{ id: 'accuracy', label: '准确率' }] }),
      'assessments/b/result.json': file({ state: 'succeeded', metrics: { accuracy: 0.9, cost: 2 } }),
    };
    expect(Object.keys(assessments(configured)[1].metrics)).toEqual(['cost', 'accuracy']);
    expect(assessments(configured)[1].metricLabels.accuracy).toBe('准确率');
  });
  it('lays out lineage consistently and tolerates unresolved or cyclic ancestry', () => {
    const items = experiments(files);
    const child = { ...items[0], id: 'exp-2', parent: 'exp-1' };
    expect(layout([...items, child]).get('exp-2')!.x).toBeGreaterThan(layout(items).get('exp-1')!.x);
    expect(layout([{ ...items[0], state: 'failed' }])).toEqual(layout(items));
    expect(layout([{ ...items[0], parent: 'exp-2' }, child]).size).toBe(2);
  });
});
