import { describe, expect, it } from 'vitest';
import { assessments, experiments, layout, parseSnapshot } from './model';
import type { ResearchFile } from './model';
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
