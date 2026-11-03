import { describe, expect, it } from 'vitest';
import { deliveredModels, deliveryIds, evaluationRuns, experiments, layout, OBSERVATION_MAX_AGE_MS, outcomeLabels, parseSnapshot, preferredEvaluation, resourceObservation, statusLabel } from './model';
import type { Observations, ResearchFile, Snapshot } from './model';
const file = (content: unknown): ResearchFile => ({ content, sha256: 'a'.repeat(64) });
const files: Snapshot['files'] = {
  'project.json': file({ schema_version: 3, deliveries: ['exp-1'] }),
  'experiments/exp-1/config.json': file({ id: 'exp-1', title: '初次训练', parameters: {} }),
  'experiments/exp-1/status.json': file({ state: 'succeeded', target: { kind: 'local', path: 'experiments/exp-1/model/model.bin', sha256: 'a'.repeat(64) } }),
  'experiments/exp-1/evals/a/config.json': file({ evaluation_version: 'v1' }),
  'experiments/exp-1/evals/a/status.json': file({ state: 'failed', metrics: {} }),
  'experiments/exp-1/evals/b/config.json': file({ evaluation_version: 'v2' }),
  'experiments/exp-1/evals/b/status.json': file({ state: 'succeeded', metrics: { accuracy: 0.9, invalid: '0.5' } }),
};
const snapshot = (source = files, observations?: Observations) => ({ files: source, revision: '1', synced_at: '', error: null, ...(observations ? { observations } : {}) });

describe('格式 3 research files', () => {
  it('validates the snapshot envelope and requires 格式 3', () => {
    expect(parseSnapshot(snapshot()).files).toEqual(files);
    expect(parseSnapshot(snapshot({})).files).toEqual({});
    expect(() => parseSnapshot({ ...snapshot(), files: [] })).toThrow();
    expect(() => parseSnapshot(snapshot({ 'project.json': file({ schema_version: 1, deliveries: [] }) }))).toThrow('格式 3');
    expect(() => parseSnapshot(snapshot({ 'project.json': { content: {}, sha256: '' } }))).toThrow();
  });
  it('rejects malformed structured records without replacing the last usable snapshot', () => {
    const good = parseSnapshot(snapshot());
    let current = good;
    for (const bad of [{ 'proposal.json': file({ sections: [], examples: 'bad' }) }, { 'proposal.json': file({ sections: 'bad', examples: [] }) }, { 'resources.json': file({ items: null }) }, { 'test.json': file([]) }, { 'outputs.jsonl': file([null]) }, { 'project.json': file({ schema_version: 3, deliveries: null }) }] as Snapshot['files'][]) {
      expect(() => { current = parseSnapshot(snapshot({ ...files, ...bad })); }).toThrow();
      expect(current).toBe(good);
    }
  });
  it('keeps successful execution separate from evaluations and versions', () => {
    expect(experiments(files)[0].state).toBe('succeeded');
    const results = evaluationRuns(files);
    expect(results.map(item => item.version)).toEqual(['v1', 'v2']);
    expect(results.map(item => item.state)).toEqual(['failed', 'succeeded']);
    expect(results[1].metrics).toEqual({ accuracy: 0.9 });
    expect(results[0].experimentId).toBe('exp-1');
  });
  it.each(['pending', 'running', 'completed', 'succeeded', 'failed', 'cancelled'])('reads the %s execution fact from experiment-local status', state => {
    const source = { ...files, 'experiments/exp-1/evals/c/config.json': file({ evaluation_version: 'v2' }), 'experiments/exp-1/evals/c/status.json': file({ state, metrics: { accuracy: 0.5 } }) };
    const result = evaluationRuns(parseSnapshot(snapshot(source)).files).find(item => item.id === 'c');
    expect(result).toMatchObject({ experimentId: 'exp-1', version: 'v2', state, metrics: { accuracy: 0.5 } });
    expect(statusLabel('completed')).toBe('待核验');
    expect(statusLabel('running')).toBe('记录为运行中');
  });
  it('accepts config-only runs, but rejects malformed status facts', () => {
    const source = { ...files, 'experiments/exp-1/evals/c/config.json': file({ evaluation_version: 'v2' }) };
    expect(evaluationRuns(source).find(item => item.id === 'c')).toMatchObject({ state: 'pending', metrics: {} });
    for (const content of [null, [], {}, { state: 'unknown' }, { state: 'toString' }, { state: true }]) {
      for (const path of ['experiments/exp-1/status.json', 'experiments/exp-1/evals/c/status.json']) {
        expect(() => parseSnapshot(snapshot({ ...source, [path]: file(content) }))).toThrow(path);
      }
    }
  });
  it('uses each version’s metric labels and drops nonfinite measurements', () => {
    const configured = { ...files,
      'evaluation/v2/definition.json': file({ metrics: [{ id: 'accuracy', label: '准确率' }, { id: 'cost', label: '成本' }] }),
      'experiments/exp-1/evals/b/status.json': file({ state: 'succeeded', metrics: { cost: 2, accuracy: 0.9, invalid: Infinity, nan: NaN } }),
    };
    expect(Object.keys(evaluationRuns(configured)[1].metrics)).toEqual(['accuracy', 'cost']);
    expect(evaluationRuns(configured)[1].metricLabels.accuracy).toBe('准确率');
  });
  it.each(Object.keys(outcomeLabels).filter(outcome => outcome !== 'unknown'))('reads %s analysis independently of execution', outcome => {
    const configured = { ...files,
      'experiments/exp-1/config.json': file({ method: 'LoRA', model_name: 'small-model', framework: 'transformers', hypothesis: 'Test adaptation', parameters: { rank: 8 } }),
      'experiments/exp-1/analysis.json': file({ outcome, summary: 'Measured on fixed examples' }),
    };
    expect(experiments(configured)[0]).toMatchObject({ state: 'succeeded', method: 'LoRA', modelName: 'small-model', framework: 'transformers', hypothesis: 'Test adaptation', parameters: { rank: 8 }, analysis: { outcome, summary: 'Measured on fixed examples' } });
  });
  it('does not infer analysis or optional configuration from execution success', () => {
    expect(experiments(files)[0]).toMatchObject({ method: '', modelName: '', framework: '', hypothesis: '', parameters: {}, analysis: { outcome: 'unknown', summary: '' } });
    expect(experiments({ ...files, 'experiments/exp-1/analysis.json': file({ outcome: 'toString' }) })[0].analysis.outcome).toBe('unknown');
  });
  it('prefers recent successful same-version evidence, never falls back across versions', () => {
    const base = evaluationRuns(files)[1];
    const oldest = { ...base, id: 'z-old', recordedAt: '2026-01-01' };
    const latest = { ...base, id: 'a-new', recordedAt: '2026-01-02' };
    const failed = { ...base, id: 'failure', state: 'failed', recordedAt: '2026-01-03' };
    const otherVersion = { ...latest, id: 'other', version: 'v1', recordedAt: '2026-01-04' };
    expect(preferredEvaluation([failed, oldest, otherVersion, latest], 'v2')).toEqual(latest);
    expect(preferredEvaluation([failed, otherVersion], 'v2')).toEqual(failed);
    expect(preferredEvaluation([failed, otherVersion], 'v3')).toBeUndefined();
    expect(preferredEvaluation([], 'v2')).toBeUndefined();
  });
  it('resolves chosen models only when succeeded and model_path is present', () => {
    const configured = { ...files,
      'project.json': file({ schema_version: 3, deliveries: ['exp-1', 'exp-1', 'missing', 'incomplete', 'no-model'] }),
      'experiments/incomplete/config.json': file({ title: '未核验' }),
      'experiments/incomplete/status.json': file({ state: 'completed', target: { kind: 'local', path: 'experiments/incomplete/model/a', sha256: 'a'.repeat(64) } }),
      'experiments/no-model/config.json': file({ title: '无模型' }),
      'experiments/no-model/status.json': file({ state: 'succeeded' }),
    };
    expect(deliveryIds(configured)).toEqual(['exp-1', 'missing', 'incomplete', 'no-model']);
    expect(deliveredModels(configured).map(item => item.id)).toEqual(['exp-1']);
    expect(deliveredModels({ ...files, 'project.json': file({ deliveries: [] }) })).toEqual([]);
  });
  it('lays out lineage consistently and tolerates unresolved or cyclic ancestry', () => {
    const items = experiments(files);
    const child = { ...items[0], id: 'exp-2', parent: 'exp-1' };
    expect(layout([...items, child]).get('exp-2')!.x).toBeGreaterThan(layout(items).get('exp-1')!.x);
    const changed = [{ ...items[0], state: 'failed' }];
    expect(layout(changed)).toEqual(layout(items));
    expect(layout([{ ...items[0], parent: 'exp-2' }, child]).size).toBe(2);
    expect(layout([{ ...child, parent: 'missing' }]).get('exp-2')!.x).toBe(48);
  });
});

describe('resource observations', () => {
  const now = Date.parse('2026-11-01T12:00:00Z');
  const resource = { id: 'data', status: 'ready', monitor: { kind: 'file' } };
  const observations: Observations = { checked_at: new Date(now).toISOString(), items: [{ id: 'data', state: 'changed', size: 1024, detail: '文件已更新', modified_at: '2026-11-01T11:59:00Z' }] };
  it('parses optional monitor data independently of file revision', () => {
    expect(parseSnapshot(snapshot()).observations).toBeUndefined();
    expect(parseSnapshot(snapshot(files, observations)).observations).toEqual(observations);
    const updated = { ...observations, items: [{ id: 'data', state: 'missing' as const }] };
    expect(parseSnapshot(snapshot(files, updated)).observations?.items[0].state).toBe('missing');
  });
  it('uses fresh measured fields and ignores absent, expired and future observations', () => {
    expect(resourceObservation(resource, observations, now)).toEqual({ state: 'changed', observation: observations.items[0] });
    expect(resourceObservation(resource, observations, now + OBSERVATION_MAX_AGE_MS + 1)).toEqual({ state: 'unknown' });
    expect(resourceObservation(resource, undefined, now)).toEqual({ state: 'unknown' });
    expect(resourceObservation(resource, { ...observations, items: [] }, now)).toEqual({ state: 'unknown' });
    expect(resourceObservation(resource, { ...observations, checked_at: 'invalid' }, now)).toEqual({ state: 'unknown' });
    expect(resourceObservation(resource, observations, now - 60_000)).toEqual({ state: 'unknown' });
    expect(resourceObservation({ id: 'manual', status: 'busy' }, undefined, now)).toEqual({ state: 'busy' });
  });
  it('rejects malformed observations instead of displaying made-up status', () => {
    for (const observations of [null, {}, { checked_at: '', items: [null] }, { checked_at: '', items: [{ id: 'data', state: 'unsupported' }] }, { checked_at: '', items: [{ id: 'data', state: 'ready', size: Infinity }] }, { checked_at: '', items: [{ id: 'data', state: 'ready', detail: {} }] }]) {
      expect(() => parseSnapshot({ ...snapshot(), observations })).toThrow('资源监测');
    }
  });
});
