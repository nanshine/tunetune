export type JsonObject = Record<string, unknown>;
export type ResearchFile = { content: unknown; sha256: string };
export type ResourceState = 'ready' | 'missing' | 'changed' | 'busy' | 'unknown';
export type ResourceObservation = { id: string; state: ResourceState; detail?: string; size?: string | number; modified_at?: string };
export type Observations = { checked_at: string; items: ResourceObservation[] };
export type Snapshot = { files: Record<string, ResearchFile>; revision: string; synced_at: string; error: string | null; observations?: Observations };
export type Outcome = 'baseline' | 'keep' | 'discard' | 'inconclusive' | 'invalid';
export type Analysis = { outcome: Outcome | 'unknown'; summary: string };
export type Usage = { requests?: number; input_tokens?: number; output_tokens?: number; cost?: number; currency?: string; latency_seconds?: number };
export const roleLabels: Record<string, string> = { baseline: '基线', candidate: '候选改进', reference: '质量参照', recommended: '推荐路线', challenge: '挑战路线' };
export type Experiment = { id: string; title: string; parent: string | null; state: string; modelPath: string; targetKind: 'local' | 'api' | ''; invoke: string[]; role: string; usage: Usage; method: string; modelName: string; framework: string; hypothesis: string; parameters: JsonObject; analysis: Analysis };
export type EvaluationRun = { id: string; experimentId: string; version: string; state: string; metrics: Record<string, number>; metricLabels: Record<string, string>; path: string; recordedAt: string; evaluationHash: string; inputFingerprint: string; usage: Usage };

export const outcomeLabels: Record<Outcome | 'unknown', string> = { baseline: '基线', keep: '保留', discard: '舍弃', inconclusive: '暂不确定', invalid: '无效', unknown: '尚无结论' };
export const resourceStates: Record<ResourceState, string> = { ready: '已就绪', missing: '缺失', changed: '已变化', busy: '使用中', unknown: '未知' };
export type ReferenceStatus = 'confirmed' | 'corrected' | 'draft';
export const referenceStatusLabels: Record<ReferenceStatus, string> = { confirmed: '已确认', corrected: '已修正', draft: '待审核' };
// Unmarked references are drafts: only the person's review makes them their judgment.
export function referenceStatus(row: JsonObject): ReferenceStatus | null {
  if (!Object.hasOwn(row, 'reference')) return null;
  const value = text(row.reference_status);
  return value === 'confirmed' || value === 'corrected' ? value : 'draft';
}
export function referenceReview(rows: JsonObject[]): Record<ReferenceStatus, number> {
  const counts: Record<ReferenceStatus, number> = { confirmed: 0, corrected: 0, draft: 0 };
  for (const row of rows) {
    const status = referenceStatus(row);
    if (status) counts[status] += 1;
  }
  return counts;
}
export const stateLabels: Record<string, string> = { pending: '待运行', running: '记录为运行中', completed: '待核验', succeeded: '成功', failed: '失败', cancelled: '已取消', unknown: '尚无记录' };

export function object(value: unknown): JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as JsonObject : {};
}
export function text(value: unknown, fallback = ''): string { return typeof value === 'string' ? value : fallback; }
export function array(value: unknown): unknown[] { return Array.isArray(value) ? value : []; }
export function document(files: Snapshot['files'], path: string): JsonObject { return object(files[path]?.content); }
export function collection(files: Snapshot['files'], pattern: RegExp): [string, JsonObject][] {
  return Object.entries(files).filter(([path]) => pattern.test(path)).sort(([a], [b]) => a.localeCompare(b)).map(([path, file]) => [path, object(file.content)]);
}
export function statusLabel(state: string): string { return Object.hasOwn(stateLabels, state) ? stateLabels[state] : stateLabels.unknown; }

export function parseSnapshot(value: unknown): Snapshot {
  const data = object(value);
  if (!data.files || typeof data.files !== 'object' || Array.isArray(data.files) || typeof data.revision !== 'string' || typeof data.synced_at !== 'string' || (data.error !== null && typeof data.error !== 'string')) throw new Error('文件通道返回了无效格式');
  for (const [path, raw] of Object.entries(data.files)) {
    const file = object(raw);
    if (!/^[a-f0-9]{64}$/.test(text(file.sha256)) || !('content' in file)) throw new Error(`${path}：缺少内容或版本标识`);
    if (path.endsWith('.json') && (file.content === null || typeof file.content !== 'object' || Array.isArray(file.content))) throw new Error(`${path}：需要 JSON 对象`);
    if (path.endsWith('.jsonl') && (!Array.isArray(file.content) || file.content.some(row => row === null || typeof row !== 'object' || Array.isArray(row)))) throw new Error(`${path}：需要逐行 JSON 对象`);
    if (/^experiments\/[^/]+\/(?:evals\/[^/]+\/)?status\.json$/.test(path)) {
      const state = text(object(file.content).state);
      if (!Object.hasOwn(stateLabels, state) || state === 'unknown') throw new Error(`${path}：无效执行状态`);
      const status = object(file.content);
      if (status.target !== undefined) {
        const target = object(status.target);
        if (!['local', 'api'].includes(text(target.kind)) || !text(target.path) || !/^[a-f0-9]{64}$/.test(text(target.sha256))) throw new Error(`${path}：模型记录不完整`);
      }
      if (status.usage !== undefined) {
        const usage = object(status.usage);
        if (!status.usage || typeof status.usage !== 'object' || Array.isArray(status.usage) || Object.entries(usage).some(([key, value]) => key === 'currency' ? typeof value !== 'string' : !['requests', 'input_tokens', 'output_tokens', 'cost', 'latency_seconds'].includes(key) || typeof value !== 'number' || !Number.isFinite(value) || value < 0)) throw new Error(`${path}：运行用量记录无效`);
      }
    }
  }
  const files = data.files as Snapshot['files'];
  if (Object.keys(files).length && document(files, 'project.json').schema_version !== 3) throw new Error('此研究使用旧版文件，请使用支持该版本的工具打开；新版仅支持格式 3');
  for (const [path, key] of [['resources.json', 'items'], ['proposal.json', 'sections'], ['proposal.json', 'examples'], ['project.json', 'deliveries']]) {
    if (files[path] && !Array.isArray(document(files, path)[key])) throw new Error(`${path}：${key} 必须是列表`);
  }
  if (data.observations !== undefined) {
    const observations = object(data.observations);
    if (typeof observations.checked_at !== 'string' || !Array.isArray(observations.items)) throw new Error('资源监测返回了无效格式');
    const ids = new Set<string>();
    for (const raw of observations.items) {
      const item = object(raw);
      if (!text(item.id) || ids.has(text(item.id)) || !Object.hasOwn(resourceStates, text(item.state))
        || (item.detail !== undefined && typeof item.detail !== 'string')
        || (item.modified_at !== undefined && typeof item.modified_at !== 'string')
        || (item.size !== undefined && typeof item.size !== 'string' && !(typeof item.size === 'number' && Number.isFinite(item.size) && item.size >= 0))) throw new Error('资源监测条目格式无效');
      ids.add(text(item.id));
    }
  }
  return data as Snapshot;
}

export function experiments(files: Snapshot['files']): Experiment[] {
  return collection(files, /^experiments\/[a-zA-Z0-9_-]+\/config\.json$/).map(([path, config]) => {
    const id = path.split('/')[1];
    const status = document(files, `experiments/${id}/status.json`);
    const record = document(files, `experiments/${id}/analysis.json`);
    const outcome = text(record.outcome);
    const modelPath = text(object(status.target).path);
    const argv = array(document(files, `experiments/${id}/model/invoke.json`).argv);
    return {
      id, title: text(config.title, id), parent: text(config.parent_experiment_id) || null,
      state: text(status.state, 'pending'), modelPath,
      invoke: modelPath === `experiments/${id}/model` && argv.length && argv.every(item => typeof item === 'string') ? argv as string[] : [],
      targetKind: object(status.target).kind === 'local' || object(status.target).kind === 'api' ? object(status.target).kind as 'local' | 'api' : '', role: text(config.role), usage: object(status.usage) as Usage,
      method: text(config.method), modelName: text(config.model_name), framework: text(config.framework), hypothesis: text(config.hypothesis), parameters: object(config.parameters),
      analysis: { outcome: Object.hasOwn(outcomeLabels, outcome) ? outcome as Analysis['outcome'] : 'unknown', summary: text(record.summary) },
    };
  });
}
export function evaluationRuns(files: Snapshot['files']): EvaluationRun[] {
  return collection(files, /^experiments\/[a-zA-Z0-9_-]+\/evals\/[a-zA-Z0-9_-]+\/config\.json$/).map(([path, config]) => {
    const status = document(files, path.replace('/config.json', '/status.json'));
    const state = text(status.state, 'pending');
    const rawMetrics = Object.fromEntries(Object.entries(object(status.metrics)).filter((entry): entry is [string, number] => typeof entry[1] === 'number' && Number.isFinite(entry[1])));
    const version = text(config.evaluation_version);
    const definitions = array(document(files, `evaluation/${version}/definition.json`).metrics).map(object);
    const order = [...new Set([...definitions.map(metric => text(metric.id)).filter(Boolean), ...Object.keys(rawMetrics)])];
    const metrics = Object.fromEntries(order.filter(id => Object.hasOwn(rawMetrics, id)).map(id => [id, rawMetrics[id]]));
    const metricLabels = Object.fromEntries(definitions.map(metric => [text(metric.id), text(metric.label, text(metric.id))]));
    return { id: path.split('/')[3], experimentId: path.split('/')[1], version, state, metrics, metricLabels, path, recordedAt: text(status.completed_at, text(status.updated_at)), evaluationHash: text(config.evaluation_sha256), inputFingerprint: JSON.stringify(array(config.inputs).map(object).map(input => [text(input.path), text(input.sha256)]).sort(([a, b], [c, d]) => a.localeCompare(c) || b.localeCompare(d))), usage: object(status.usage) as Usage };
  });
}
export function recentEvaluations(results: EvaluationRun[]): EvaluationRun[] {
  return [...results].sort((a, b) => {
    const time = (value: string) => Number.isFinite(Date.parse(value)) ? Date.parse(value) : 0;
    return time(b.recordedAt) - time(a.recordedAt) || b.id.localeCompare(a.id);
  });
}

// A canvas always uses one evaluation version. Other versions belong in the detail selector.
export function preferredEvaluation(results: EvaluationRun[], version: string): EvaluationRun | undefined {
  const sorted = recentEvaluations(results.filter(result => result.version === version));
  return sorted.find(result => result.state === 'succeeded') ?? sorted[0];
}
export function deliveryIds(files: Snapshot['files']): string[] {
  return [...new Set(array(document(files, 'project.json').deliveries).filter((id): id is string => typeof id === 'string'))];
}
export function deliveredModels(files: Snapshot['files']): Experiment[] {
  const byId = new Map(experiments(files).map(item => [item.id, item]));
  return deliveryIds(files).flatMap(id => {
    const item = byId.get(id);
    return item?.state === 'succeeded' && item.targetKind === 'local' && item.modelPath ? [item] : [];
  });
}

export const OBSERVATION_MAX_AGE_MS = 30_000;
export function resourceObservation(resource: JsonObject, observations: Observations | undefined, now: number): { state: ResourceState; observation?: ResourceObservation } {
  const monitored = Object.keys(object(resource.monitor)).length > 0;
  const recordedState = text(resource.status);
  const fallback: ResourceState = !monitored && Object.hasOwn(resourceStates, recordedState) ? recordedState as ResourceState : 'unknown';
  const age = now - Date.parse(observations?.checked_at ?? '');
  if (!Number.isFinite(age) || age < -5000 || age > OBSERVATION_MAX_AGE_MS) return { state: fallback };
  const observation = observations?.items.find(item => item.id === resource.id);
  return observation ? { state: observation.state, observation } : { state: fallback };
}

export function layout(items: Pick<Experiment, 'id' | 'parent'>[]): Map<string, { x: number; y: number }> {
  const byId = new Map(items.map(item => [item.id, item]));
  const levels = new Map<string, number>();
  function depth(id: string, visited = new Set<string>()): number {
    if (levels.has(id)) return levels.get(id)!;
    if (visited.has(id)) return 0;
    visited.add(id);
    const parent = byId.get(id)?.parent;
    const level = parent && byId.has(parent) ? depth(parent, visited) + 1 : 0;
    levels.set(id, level);
    return level;
  }
  const rows = new Map<number, number>();
  return new Map(items.map(item => {
    const level = depth(item.id);
    const row = rows.get(level) ?? 0;
    rows.set(level, row + 1);
    return [item.id, { x: level * 360 + 48, y: row * 360 + 160 }];
  }));
}

export function comparableModels(files: Snapshot['files']): Experiment[] {
  return experiments(files).filter(item => item.state === 'succeeded' && item.targetKind && item.modelPath);
}
export function compatibleMeasurements(left: EvaluationRun | undefined, right: EvaluationRun | undefined): boolean {
  return !!left && !!right && left.state === 'succeeded' && right.state === 'succeeded' && !!left.evaluationHash && left.evaluationHash === right.evaluationHash && left.version === right.version && left.inputFingerprint === right.inputFingerprint;
}

export function acceptanceInputs(files: Snapshot['files']): boolean {
  return Array.isArray(files['comparison/inputs.jsonl']?.content);
}
export function comparisonSamples(files: Snapshot['files'], leftId: string, rightId: string, version: string): JsonObject[] {
  const explicit = files['comparison/outputs.jsonl'];
  if (acceptanceInputs(files)) {
    // Acceptance inputs define the rows; outputs for a since-changed input are not shown.
    const produced = new Map(array(explicit?.content).map(object).map(row => [text(row.sample_id), row]));
    return array(files['comparison/inputs.jsonl'].content).map(object).map(row => {
      const done = produced.get(text(row.sample_id));
      return { ...row, outputs: done && JSON.stringify(done.input) === JSON.stringify(row.input) ? object(done.outputs) : {} };
    });
  }
  if (explicit) return array(explicit.content).map(object);
  const results = evaluationRuns(files);
  const left = preferredEvaluation(results.filter(run => run.experimentId === leftId), version);
  const right = preferredEvaluation(results.filter(run => run.experimentId === rightId), version);
  if (!compatibleMeasurements(left, right)) return [];
  const leftRows = array(files[left!.path.replace('/config.json', '/outputs.jsonl')]?.content).map(object);
  const rightRows = new Map(array(files[right!.path.replace('/config.json', '/outputs.jsonl')]?.content).map(object).map(row => [text(row.sample_id), row]));
  return leftRows.flatMap(row => {
    const other = rightRows.get(text(row.sample_id));
    if (!other || JSON.stringify(row.input) !== JSON.stringify(other.input)) return [];
    return [{ sample_id: row.sample_id, input: row.input, outputs: { [leftId]: row.output, [rightId]: other.output } }];
  });
}
