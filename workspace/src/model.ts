export type JsonObject = Record<string, unknown>;
export type ResearchFile = { content: unknown; sha256: string };
export type ResourceState = 'ready' | 'missing' | 'changed' | 'busy' | 'unknown';
export type ResourceObservation = { id: string; state: ResourceState; detail?: string; size?: string | number; modified_at?: string };
export type Observations = { checked_at: string; items: ResourceObservation[] };
export type ViewName = 'proposal' | 'plan' | 'resources' | 'evaluation' | 'review' | 'acceptance';
export type ViewState = { revision: number; open: ViewName[]; focus: { experiment?: string }; attention: { view: ViewName; message: string }[] };
export type AcceptanceJob = { id: string; state: 'running' | 'succeeded' | 'failed'; experiments: string[]; started_at: string; finished_at?: string; failed?: string[]; message?: string };
export type LoadedModel = { state: 'loading' | 'loaded' | 'failed'; memory_gb: number; estimated?: boolean; error?: string };
export type ModelPool = { budget_gb: number; used_gb: number; items: Record<string, LoadedModel> };
export type Snapshot = { files: Record<string, ResearchFile>; revision: string; synced_at: string; error: string | null; observations?: Observations; view?: ViewState | null; acceptance?: AcceptanceJob | null; models?: ModelPool };
export type Outcome = 'baseline' | 'keep' | 'discard' | 'inconclusive' | 'invalid';
export type Analysis = { outcome: Outcome | 'unknown'; summary: string };
export type Usage = { requests?: number; input_tokens?: number; output_tokens?: number; cost?: number; currency?: string; latency_seconds?: number };
export const roleLabels: Record<string, string> = { baseline: '基线', candidate: '候选改进', reference: '质量参照', recommended: '推荐路线', challenge: '挑战路线' };
export type Experiment = { id: string; title: string; parent: string | null; state: string; modelPath: string; targetKind: 'local' | 'api' | ''; invoke: string[]; serve: boolean; role: string; usage: Usage; method: string; modelName: string; framework: string; hypothesis: string; parameters: JsonObject; analysis: Analysis };
export type Split = 'development' | 'final';
export type EvaluationRun = { id: string; experimentId: string; version: string; split: Split; state: string; metrics: Record<string, number>; metricLabels: Record<string, string>; path: string; recordedAt: string; evaluationHash: string; inputFingerprint: string; usage: Usage };

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
  if (Object.keys(files).length && document(files, 'project.json').schema_version !== 4) throw new Error('这个研究目录使用旧版文件格式，当前工作台只能打开格式 4 的研究');
  for (const [path, key] of [['resources.json', 'items'], ['proposal.json', 'examples'], ['project.json', 'deliveries']]) {
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

export type PlanState = 'planned' | 'running' | 'done' | 'dropped';
export type PlanItem = { id: string; title: string; question: string; expected: string; state: PlanState; intervention: string; parent: string | null; comparator: string; cost: string; note: string; resourceIds: string[] };
export type PlanRound = { round: number; goal: string; budget: string; conclusion: string; items: PlanItem[] };
export const planStateLabels: Record<PlanState, string> = { planned: '计划中', running: '进行中', done: '已完成', dropped: '已放弃' };
export function plan(files: Snapshot['files']): { rounds: PlanRound[]; ideas: { title: string; reason: string }[] } {
  const raw = document(files, 'plan.json');
  const rounds = array(raw.rounds).map(object).map((round, index) => ({
    round: typeof round.round === 'number' ? round.round : index + 1, goal: text(round.goal), budget: text(round.budget), conclusion: text(round.conclusion),
    items: array(round.items).map(object).filter(item => /^[A-Za-z0-9_-]+$/.test(text(item.id))).map(item => {
      const state = text(item.state);
      return { id: text(item.id), title: text(item.title, text(item.id)), question: text(item.question), expected: text(item.expected),
        state: (Object.hasOwn(planStateLabels, state) ? state : 'planned') as PlanState, intervention: text(item.intervention), parent: text(item.parent) || null,
        comparator: text(item.comparator), cost: text(item.cost), note: text(item.note), resourceIds: array(item.resource_ids).filter((id): id is string => typeof id === 'string') };
    }),
  }));
  return { rounds, ideas: array(raw.ideas).map(object).map(idea => ({ title: text(idea.title), reason: text(idea.reason) })).filter(idea => idea.title) };
}
// Planned work that has no experiment yet; shown as dashed canvas nodes.
export function plannedNodes(files: Snapshot['files']): PlanItem[] {
  const existing = new Set(experiments(files).map(item => item.id));
  const seen = new Set<string>();
  return plan(files).rounds.flatMap(round => round.items).reverse().filter(item => {
    if (seen.has(item.id)) return false;
    seen.add(item.id);
    return !existing.has(item.id) && (item.state === 'planned' || item.state === 'running');
  }).reverse();
}
// "e002-embed-lr" reads as "E002"; other IDs are shown as written.
export function experimentNumber(id: string): string {
  const match = /^e(\d{3,})(?:-|$)/.exec(id);
  return match ? `E${match[1]}` : id;
}

export type ResponseKind = 'proposal' | 'plan' | 'evaluation_review' | 'acceptance';
export const responseTargets: Record<ResponseKind, string> = { proposal: 'proposal.json', plan: 'plan.json', evaluation_review: 'evaluation/draft/samples.jsonl', acceptance: 'comparison/outputs.jsonl' };
// The person's latest answer still applies only while the file they answered is unchanged.
export function currentResponse(files: Snapshot['files'], kind: ResponseKind): JsonObject | null {
  const target = files[responseTargets[kind]];
  if (!target) return null;
  const answers = collection(files, /^responses\/[A-Za-z0-9_-]+\.json$/).map(([, value]) => value)
    .filter(value => value.kind === kind && text(object(value.target).sha256) === target.sha256)
    .sort((a, b) => text(a.created_at).localeCompare(text(b.created_at)));
  return answers.at(-1) ?? null;
}

export function experiments(files: Snapshot['files']): Experiment[] {
  return collection(files, /^experiments\/[a-zA-Z0-9_-]+\/config\.json$/).map(([path, config]) => {
    const id = path.split('/')[1];
    const status = document(files, `experiments/${id}/status.json`);
    const record = document(files, `experiments/${id}/analysis.json`);
    const outcome = text(record.outcome);
    const modelPath = text(object(status.target).path);
    const entry = document(files, `experiments/${id}/model/invoke.json`);
    const argv = array(entry.argv);
    return {
      id, title: text(config.title, id), parent: text(config.parent_experiment_id) || null,
      state: text(status.state, 'pending'), modelPath,
      invoke: modelPath === `experiments/${id}/model` && argv.length && argv.every(item => typeof item === 'string') ? argv as string[] : [],
      serve: modelPath === `experiments/${id}/model` && array(object(entry.serve).argv).length > 0,
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
    return { id: path.split('/')[3], experimentId: path.split('/')[1], version, split: config.split === 'final' ? 'final' : 'development', state, metrics, metricLabels, path, recordedAt: text(status.completed_at, text(status.updated_at)), evaluationHash: text(config.evaluation_sha256), inputFingerprint: JSON.stringify(array(config.inputs).map(object).map(input => [text(input.path), text(input.sha256)]).sort(([a, b], [c, d]) => a.localeCompare(c) || b.localeCompare(d))), usage: object(status.usage) as Usage };
  });
}
export function recentEvaluations(results: EvaluationRun[]): EvaluationRun[] {
  return [...results].sort((a, b) => {
    const time = (value: string) => Number.isFinite(Date.parse(value)) ? Date.parse(value) : 0;
    return time(b.recordedAt) - time(a.recordedAt) || b.id.localeCompare(a.id);
  });
}

// A canvas always uses one evaluation version. Other versions belong in the detail selector.
// Development scores guide the research; a final check is shown apart and never ranks the canvas.
export function preferredEvaluation(results: EvaluationRun[], version: string, split: Split = 'development'): EvaluationRun | undefined {
  const sorted = recentEvaluations(results.filter(result => result.version === version && result.split === split));
  return sorted.find(result => result.state === 'succeeded') ?? sorted[0];
}
export function sampleSplit(row: JsonObject): Split { return row.split === 'final' ? 'final' : 'development'; }
export function splitCounts(rows: JsonObject[]): Record<Split, number> {
  return { development: rows.filter(row => sampleSplit(row) === 'development').length, final: rows.filter(row => sampleSplit(row) === 'final').length };
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

export const NODE_WIDTH = 248;
export const NODE_HEIGHT = 92;
const COLUMN_GAP = 72;
const ROW_GAP = 24;
// A tidy tree: each subtree occupies its own rows and a parent is centred on its children,
// so fixed-size nodes never overlap and branches never cross.
export function layout(items: { id: string; parent: string | null }[]): Map<string, { x: number; y: number }> {
  const byId = new Map(items.map(item => [item.id, item]));
  const children = new Map<string, string[]>();
  const roots: string[] = [];
  function reachesSelf(id: string): boolean {
    const seen = new Set<string>();
    let current = byId.get(id)?.parent ?? null;
    while (current && byId.has(current)) {
      if (current === id || seen.has(current)) return true;
      seen.add(current);
      current = byId.get(current)?.parent ?? null;
    }
    return false;
  }
  for (const item of items) {
    if (item.parent && byId.has(item.parent) && !reachesSelf(item.id)) children.set(item.parent, [...(children.get(item.parent) ?? []), item.id]);
    else roots.push(item.id);
  }
  const positions = new Map<string, { x: number; y: number }>();
  let row = 0;
  function place(id: string, depth: number): number {
    const kids = children.get(id) ?? [];
    const centre = kids.length ? kids.map(kid => place(kid, depth + 1)).reduce((sum, value, _, all) => sum + value / all.length, 0) : row++;
    positions.set(id, { x: depth * (NODE_WIDTH + COLUMN_GAP), y: centre * (NODE_HEIGHT + ROW_GAP) });
    return centre;
  }
  for (const root of roots) place(root, 0);
  return positions;
}

export function comparableModels(files: Snapshot['files']): Experiment[] {
  return experiments(files).filter(item => item.state === 'succeeded' && item.targetKind && item.modelPath);
}
// Acceptance leads with what could be delivered; rejected experiments stay reachable but out of the way.
const setAside = new Set<Analysis['outcome']>(['discard', 'inconclusive', 'invalid']);
export function acceptanceModels(files: Snapshot['files']): { primary: Experiment[]; more: Experiment[] } {
  const delivered = new Set(deliveryIds(files));
  const ordered = comparableModels(files).sort((a, b) => Number(delivered.has(b.id)) - Number(delivered.has(a.id)) || a.id.localeCompare(b.id));
  const primary = ordered.filter(item => delivered.has(item.id) || !setAside.has(item.analysis.outcome));
  return { primary, more: ordered.filter(item => !primary.includes(item)) };
}
export type RunState = 'runnable' | 'loading' | 'loaded' | 'load-failed' | 'running' | 'failed' | 'no-entry' | 'api';
export const runStateLabels: Record<RunState, string> = { runnable: '可运行 · 每次运行时加载', loading: '正在加载…', loaded: '已加载 · 即时回答', 'load-failed': '加载失败', running: '运行中', failed: '上次运行失败', 'no-entry': '缺少调用入口，无法运行', api: '在线参照 · 面板不调用' };
export function runState(item: Experiment, job: AcceptanceJob | null | undefined, pool?: ModelPool | null): RunState {
  if (item.targetKind === 'api') return 'api';
  if (!item.invoke.length) return 'no-entry';
  const loaded = pool?.items[item.id];
  if (job?.experiments.includes(item.id)) {
    if (job.state === 'running') return 'running';
    if (job.state === 'failed' && job.failed?.includes(item.id)) return 'failed';
  }
  if (loaded) return loaded.state === 'failed' ? 'load-failed' : loaded.state;
  return 'runnable';
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
