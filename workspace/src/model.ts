export type JsonObject = Record<string, unknown>;
export type ResearchFile = { content: unknown; sha256: string };
export type ResourceState = 'ready' | 'missing' | 'changed' | 'busy' | 'unknown';
export type ResourceObservation = { id: string; state: ResourceState; detail?: string; size?: string | number; modified_at?: string };
export type Observations = { checked_at: string; items: ResourceObservation[] };
export type Snapshot = { files: Record<string, ResearchFile>; revision: string; synced_at: string; error: string | null; observations?: Observations };
export type Outcome = 'baseline' | 'keep' | 'discard' | 'inconclusive' | 'invalid';
export type Analysis = { outcome: Outcome | 'unknown'; summary: string };
export type Experiment = { id: string; title: string; parent: string | null; state: string; modelPath: string; method: string; modelName: string; framework: string; hypothesis: string; parameters: JsonObject; analysis: Analysis };
export type EvaluationRun = { id: string; experimentId: string; version: string; state: string; metrics: Record<string, number>; metricLabels: Record<string, string>; path: string; recordedAt: string };

export const outcomeLabels: Record<Outcome | 'unknown', string> = { baseline: '基线', keep: '保留', discard: '舍弃', inconclusive: '暂不确定', invalid: '无效', unknown: '尚无结论' };
export const resourceStates: Record<ResourceState, string> = { ready: '已就绪', missing: '缺失', changed: '已变化', busy: '使用中', unknown: '未知' };
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
    }
  }
  const files = data.files as Snapshot['files'];
  if (Object.keys(files).length && document(files, 'project.json').schema_version !== 2) throw new Error('不支持此研究文件格式，请使用 format 2 研究文件');
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
    return {
      id, title: text(config.title, id), parent: text(config.parent_experiment_id) || null,
      state: text(status.state, 'pending'), modelPath: text(status.model_path),
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
    return { id: path.split('/')[3], experimentId: path.split('/')[1], version, state, metrics, metricLabels, path, recordedAt: text(status.completed_at, text(status.updated_at)) };
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
    return item?.state === 'succeeded' && item.modelPath ? [item] : [];
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
