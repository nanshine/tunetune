export type JsonObject = Record<string, unknown>;
export type ResearchFile = { content: unknown; sha256: string };
export type Snapshot = { files: Record<string, ResearchFile>; revision: string; synced_at: string; error: string | null };
export type Experiment = { id: string; title: string; parent: string | null; state: string; updatedAt: string; configPath: string };
export type Assessment = { id: string; experimentId: string; version: string; state: string; metrics: Record<string, number>; metricLabels: Record<string, string>; path: string };
export type FeedbackTarget = { kind: 'comment' | 'change' | 'response' | 'preference' | 'acceptance'; target: string | null; request_id?: string; sample_id?: string; title: string; options?: string[] };

export function object(value: unknown): JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as JsonObject : {};
}
export function text(value: unknown, fallback = ''): string { return typeof value === 'string' ? value : fallback; }
export function array(value: unknown): unknown[] { return Array.isArray(value) ? value : []; }
export function document(files: Snapshot['files'], path: string): JsonObject { return object(files[path]?.content); }
export function collection(files: Snapshot['files'], pattern: RegExp): [string, JsonObject][] {
  return Object.entries(files).filter(([path]) => pattern.test(path)).sort(([a], [b]) => a.localeCompare(b)).map(([path, file]) => [path, object(file.content)]);
}

export function parseSnapshot(value: unknown): Snapshot {
  const data = object(value);
  if (!data.files || typeof data.files !== 'object' || Array.isArray(data.files) || typeof data.revision !== 'string' || typeof data.synced_at !== 'string' || (data.error !== null && typeof data.error !== 'string')) throw new Error('文件通道返回了无效格式');
  for (const [path, raw] of Object.entries(data.files)) {
    const file = object(raw);
    if (!/^[a-f0-9]{64}$/.test(text(file.sha256)) || !('content' in file)) throw new Error(`${path}：缺少内容或版本标识`);
    if (path.endsWith('.json') && (file.content === null || typeof file.content !== 'object' || Array.isArray(file.content))) throw new Error(`${path}：需要 JSON 对象`);
    if (path.endsWith('.jsonl') && (!Array.isArray(file.content) || file.content.some(row => row === null || typeof row !== 'object' || Array.isArray(row)))) throw new Error(`${path}：需要逐行 JSON 对象`);
  }
  const files = data.files as Snapshot['files'];
  if (Object.keys(files).length && document(files, 'project.json').schema_version !== 1) throw new Error('不支持此研究文件格式，请显式迁移后打开');
  for (const [path, key] of [['resources.json', 'items'], ['candidates.json', 'items'], ['goal.json', 'examples']]) {
    if (files[path] && !Array.isArray(document(files, path)[key])) throw new Error(`${path}：${key} 必须是列表`);
  }
  return data as Snapshot;
}

export function experiments(files: Snapshot['files']): Experiment[] {
  return collection(files, /^experiments\/[^/]+\/config\.json$/).map(([path, config]) => {
    const id = path.split('/')[1];
    const status = document(files, `experiments/${id}/status.json`);
    return { id, title: text(config.title, id), parent: text(config.parent_experiment_id) || null, state: text(status.state, 'unknown'), updatedAt: text(status.updated_at), configPath: path };
  });
}
export function assessments(files: Snapshot['files']): Assessment[] {
  return collection(files, /^assessments\/[^/]+\/config\.json$/).map(([path, config]) => {
    const result = document(files, path.replace('/config.json', '/result.json'));
    const rawMetrics = Object.fromEntries(Object.entries(object(result.metrics)).filter((entry): entry is [string, number] => typeof entry[1] === 'number' && Number.isFinite(entry[1])));
    const version = text(config.evaluation_version, '未指定');
    const definitions = array(document(files, `evaluation/versions/${version}/definition.json`).metrics).map(object);
    const columns = array(document(files, 'workspace.json').metric_columns).filter((column): column is string => typeof column === 'string');
    const order = [...new Set([...columns, ...definitions.map(metric => text(metric.id)), ...Object.keys(rawMetrics)])];
    const metrics = Object.fromEntries(order.filter(id => Object.hasOwn(rawMetrics, id)).map(id => [id, rawMetrics[id]]));
    const metricLabels = Object.fromEntries(definitions.map(metric => [text(metric.id), text(metric.label, text(metric.id))]));
    return { id: path.split('/')[1], experimentId: text(config.experiment_id), version, state: text(result.state, 'unknown'), metrics, metricLabels, path };
  });
}

export function layout(items: Experiment[]): Map<string, { x: number; y: number }> {
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

export const stateLabels: Record<string, string> = { pending: '待运行', running: '记录为运行中', succeeded: '成功', failed: '失败', cancelled: '已取消', unknown: '尚无记录' };
export function statusLabel(state: string): string { return Object.hasOwn(stateLabels, state) ? stateLabels[state] : state; }
