import { createElement } from 'react';
import type { FunctionComponent } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ResearchFile, Snapshot } from './model';
import { acceptanceModels, evaluationRuns, experiments, preferredEvaluation, runState } from './model';
import { ProposalView, ResourcesView, readableSize } from './ProjectBrief';
import { PlanView } from './PlanView';
import { EvaluationView, SamplesView } from './EvaluationView';
import { ReviewView, parseCorrection } from './ReviewView';
import { AcceptanceView, inputTemplate } from './AcceptanceView';
import { ExperimentSummary } from './Lineage';
import { ExperimentDetails } from './ExperimentDetails';
import { setLanguage } from './i18n';

// These assertions read the Chinese source text; English is covered in i18n.test.ts.
setLanguage('zh');

const workspace = vi.hoisted(() => ({ snapshot: null as Snapshot | null, connectionError: null as string | null, renameProject: vi.fn() }));
vi.mock('./useWorkspace', () => ({ useWorkspace: () => workspace, submitResponse: vi.fn(), runAcceptance: vi.fn(), tryModel: vi.fn(), loadModel: vi.fn(), unloadModel: vi.fn() }));
const { App } = await import('./App');

const file = (content: unknown, sha = 'a'): ResearchFile => ({ content, sha256: sha.repeat(64) });
const post = { title: '可拼搭的软件', text: '用多维表格搭一个自己的系统。' };
const files: Snapshot['files'] = {
  'project.json': file({ name: '博客标签', language: 'zh-CN', current_evaluation: 'v1', deliveries: ['e001-embed'] }),
  'proposal.json': file({ summary: '为博客文章推荐导航标签。', goal: '给新文章打 1–2 个宽主题标签', examples: [{ id: 'one', input: post, expected_output: ['产品与商业'] }],
    considered: [{ family: '冻结向量加分类头', decision: 'adopted', reason: '标签少也能用' }, { family: '微调大模型', decision: 'excluded', reason: '16 GB 内存不够' }],
    approaches: [{ id: 'a', title: '关键词', roles: ['baseline'], rationale: '最便宜' }], budget: '下载不超过 1 GB', stopping: '两轮无提升就停', sources: [{ title: 'bge 模型卡', url: 'https://huggingface.co/BAAI/bge-small-zh-v1.5' }] }, 'b'),
  'resources.json': file({ items: [{ id: 'm', title: 'bge-small-zh', type: 'model', status: 'ready', size: '95000000 bytes', purpose: '中文向量', path: 'resources/bge' }, { id: 'd', title: '博客文章', type: 'data', status: 'missing' }] }),
  'plan.json': file({ rounds: [{ round: 1, goal: '语义方法能否超过关键词', budget: '2 个实验', items: [
    { id: 'e001-embed', title: '向量加逻辑回归', question: '语义向量是否更准', expected: '开发集 F1 高于 E000', state: 'done', comparator: 'e000-keyword', intervention: '冻结向量加分类头' },
    { id: 'e002-setfit', title: 'SetFit', question: '少样本对比微调', expected: 'F1 再高 0.05', state: 'planned', parent: 'e001-embed' }] }] }, 'c'),
  'experiments/e000-keyword/config.json': file({ title: '关键词基线', role: 'baseline', hypothesis: '词频能区分主题' }),
  'experiments/e000-keyword/status.json': file({ state: 'succeeded', target: { kind: 'local', path: 'experiments/e000-keyword/model', sha256: 'd'.repeat(64) } }),
  'experiments/e000-keyword/evals/r1/config.json': file({ evaluation_version: 'v1', evaluation_sha256: 'e'.repeat(64) }),
  'experiments/e000-keyword/evals/r1/status.json': file({ state: 'succeeded', metrics: { f1: 0.62 } }),
  'experiments/e001-embed/config.json': file({ title: '向量加逻辑回归', parent_experiment_id: 'e000-keyword', role: 'candidate', parameters: { context: 512 } }),
  'experiments/e001-embed/status.json': file({ state: 'succeeded', target: { kind: 'local', path: 'experiments/e001-embed/model', sha256: 'd'.repeat(64) } }),
  'experiments/e001-embed/analysis.json': file({ outcome: 'keep', summary: '比关键词更稳。' }),
  'experiments/e001-embed/evals/r1/config.json': file({ evaluation_version: 'v1', evaluation_sha256: 'e'.repeat(64) }),
  'experiments/e001-embed/evals/r1/status.json': file({ state: 'succeeded', metrics: { f1: 0.81 } }),
  'evaluation/v1/definition.json': file({ version: 'v1', description: '22 篇作者确认的文章', rubric: '按集合比较', metrics: [{ id: 'f1', label: '标签 F1', direction: 'maximize', description: '标签整体对上的程度' }], command: ['python3'] }),
  'evaluation/v1/samples.jsonl': file([{ sample_id: 's1', input: post, reference: ['产品与商业'], reference_status: 'confirmed' }]),
  'evaluation/draft/samples.jsonl': file([{ sample_id: 's1', input: post, reference: ['产品与商业'], reference_status: 'draft' }, { sample_id: 's2', input: { title: '走山路', text: '…' }, reference: ['个人成长'], reference_status: 'draft' }], 'f'),
  'comparison/inputs.jsonl': file([{ sample_id: 'p1', input: post }]),
  'comparison/outputs.jsonl': file([{ sample_id: 'p1', input: post, outputs: { 'e001-embed': ['产品与商业'] } }]),
};
// Views take differing props; each test passes the props that view expects.
const render = (type: FunctionComponent<any>, props: Record<string, unknown>) => renderToStaticMarkup(createElement(type, props));

vi.stubGlobal('navigator', { language: 'zh-CN' });
beforeEach(() => { setLanguage('zh'); workspace.snapshot = { files, revision: '1', synced_at: '', error: null, view: { revision: 1, open: [], focus: {}, attention: [{ view: 'review', message: '22 篇标签待审阅' }] } }; workspace.connectionError = null; });

describe('workspace shell', () => {
  it('shows the canvas, five research tiles and an attention mark without opening windows by itself on the server', () => {
    const html = render(App, {});
    for (const label of ['提案', '方案', '资源', '评测', '验收', '博客标签', '评测 v1', 'E001', 'E002', '计划中']) expect(html).toContain(label);
    expect(html).toContain('待处理：22 篇标签待审阅');
    expect(html).not.toContain('role="dialog"');
  });
  it('keeps the empty canvas short', () => {
    workspace.snapshot = { files: { 'project.json': files['project.json'] }, revision: '1', synced_at: '', error: null };
    const html = render(App, {});
    expect(html).toContain('实验会出现在这里');
    workspace.snapshot = null;
    workspace.connectionError = '无法连接';
    expect(render(App, {})).toContain('连接中断');
  });
});

describe('research views', () => {
  it('shows the proposal as structured decisions with a confirmation bar when the Agent asks', () => {
    const html = render(ProposalView, { files, waiting: '请确认研究提案', onRespond: vi.fn(), delivered: true });
    for (const value of ['请确认研究提案', '确认，开始研究', '需要修改', '目标', '你的例子', '可拼搭的软件', '产品与商业', '采用', '不采用', '16 GB 内存不够', '两轮无提升就停', 'bge 模型卡', 'huggingface.co']) expect(html).toContain(value);
    expect(render(ProposalView, { files, onRespond: vi.fn(), delivered: true })).not.toContain('确认，开始研究');
    // Where panel answers do not reach the conversation, the decision is asked there and only shown as waiting here.
    const undelivered = render(ProposalView, { files, waiting: '请确认研究提案', onRespond: vi.fn() });
    expect(undelivered).toContain('请确认研究提案');
    expect(undelivered).toContain('Agent 在对话里等你的回复');
    expect(undelivered).not.toContain('确认，开始研究');
    const answered = { ...files, 'responses/r1.json': file({ kind: 'proposal', target: { path: 'proposal.json', sha256: 'b'.repeat(64) }, created_at: '2026-11-03T01:00:00Z', decision: 'approve' }) };
    expect(render(ProposalView, { files: answered, waiting: '请确认', onRespond: vi.fn() })).toContain('你已确认');
    expect(render(ProposalView, { files: answered, waiting: '请确认', onRespond: vi.fn(), delivered: true })).toContain('已转给对话中的 Agent');
    expect(render(ProposalView, { files: {} })).toContain('还没有研究提案');
  });
  it('lists the round with numbers, states, comparators and expectations', () => {
    const html = render(PlanView, { files, onFocusExperiment: vi.fn() });
    for (const value of ['语义方法能否超过关键词', 'E001', '已完成', 'E002', '计划中', '对比 E000', '开发集 F1 高于 E000']) expect(html).toContain(value);
    expect(render(PlanView, { files: {}, onFocusExperiment: vi.fn() })).toContain('还没有实验方案');
  });
  it('summarizes resources and expands facts on demand', () => {
    const html = render(ResourcesView, { resources: files['resources.json'].content });
    for (const value of ['1</strong> / 2 已就绪', 'bge-small-zh', '90.6 MB', '中文向量', '缺失']) expect(html).toContain(value);
    expect(html).not.toContain('resources/bge');
    expect(readableSize('12 条')).toBe('12 条');
  });
  it('explains metrics in plain words and opens reference review for drafts', () => {
    const overview = render(EvaluationView, { files, currentVersion: 'v1', selection: '', onSelect: vi.fn() });
    for (const value of ['标签 F1', '越高越好', '标签整体对上的程度', '审阅参考答案', '（当前）']) expect(overview).toContain(value);
    const review = render(EvaluationView, { files, currentVersion: 'v1', selection: '', onSelect: vi.fn(), initialTab: 'review', onReview: vi.fn() });
    for (const value of ['可拼搭的软件', '走山路', '产品与商业', '已看 0 / 2', '提交审阅', '拿不准']) expect(review).toContain(value);
    expect(render(EvaluationView, { files: {}, currentVersion: '', selection: '', onSelect: vi.fn() })).toContain('还没有评测');
  });
  it('turns corrected tag lists back into arrays and keeps other shapes', () => {
    expect(parseCorrection(['a'], '产品与商业， 个人成长、')).toEqual(['产品与商业', '个人成长']);
    expect(parseCorrection('good', ' better ')).toBe('better');
    expect(parseCorrection({ score: 1 }, '{"score":2}')).toEqual({ score: 2 });
    const done = { ...files, 'responses/r2.json': file({ kind: 'evaluation_review', target: { path: 'evaluation/draft/samples.jsonl', sha256: 'f'.repeat(64) }, created_at: '2026-11-03T01:00:00Z', decision: 'submit', items: [{ sample_id: 's1', verdict: 'confirm' }] }) };
    expect(render(ReviewView, { files: done, rows: [] })).toContain('审阅已提交');
  });
  it('leads acceptance with deliverable candidates and says whether each model can run', () => {
    const extra = { ...files,
      'experiments/e001-embed/model/invoke.json': file({ argv: ['python3', 'predict.py'] }),
      'experiments/e002-prompt/config.json': file({ title: '提示词版本' }),
      'experiments/e002-prompt/status.json': file({ state: 'succeeded', target: { kind: 'local', path: 'experiments/e002-prompt/model', sha256: 'd'.repeat(64) } }),
      'experiments/e002-prompt/analysis.json': file({ outcome: 'discard', summary: '过度标记。' }),
      'experiments/e003-api/config.json': file({ title: '在线模型' }),
      'experiments/e003-api/status.json': file({ state: 'succeeded', target: { kind: 'api', path: 'experiments/e003-api/model', sha256: 'd'.repeat(64) } }) };
    const groups = acceptanceModels(extra);
    expect(groups.primary.map(item => item.id)).toEqual(['e001-embed', 'e000-keyword', 'e003-api']);
    expect(groups.more.map(item => item.id)).toEqual(['e002-prompt']);
    const byId = new Map(experiments(extra).map(item => [item.id, item]));
    expect(runState(byId.get('e001-embed')!, null)).toBe('runnable');
    expect(runState(byId.get('e000-keyword')!, null)).toBe('no-entry');
    expect(runState(byId.get('e003-api')!, null)).toBe('api');
    expect(runState(byId.get('e001-embed')!, { id: 'j', state: 'failed', experiments: ['e001-embed'], started_at: '', failed: ['e001-embed'] })).toBe('failed');
    const html = render(AcceptanceView, { files: extra, job: null, onRun: vi.fn(), onTry: vi.fn() });
    for (const value of ['其他实验 1 个', '可运行 · 每次运行时加载', '缺少调用入口，无法运行', '在线参照 · 面板不调用']) expect(html).toContain(value);
    expect(html).not.toContain('提示词版本');
    const served = { ...extra, 'experiments/e001-embed/model/invoke.json': file({ argv: ['python3', 'predict.py'], serve: { argv: ['python3', 'serve.py'] } }) };
    const pool = { budget_gb: 8, used_gb: 2.6, items: { 'e001-embed': { state: 'loaded' as const, memory_gb: 2.6 } } };
    const embed = experiments(served).find(item => item.id === 'e001-embed')!;
    expect(embed.serve).toBe(true);
    expect(runState(embed, null, pool)).toBe('loaded');
    expect(runState(embed, null, { ...pool, items: { 'e001-embed': { state: 'failed', memory_gb: 2.6, error: 'x' } } })).toBe('load-failed');
    const loaded = render(AcceptanceView, { files: served, job: null, pool, onRun: vi.fn(), onTry: vi.fn(), onLoad: vi.fn(), onUnload: vi.fn() });
    for (const value of ['已加载 · 即时回答', '约 2.6 GB', '卸载', '常驻内存 2.6 / 8.0 GB']) expect(loaded).toContain(value);
    expect(render(AcceptanceView, { files: served, job: null, pool: { ...pool, used_gb: 0, items: {} }, onRun: vi.fn(), onTry: vi.fn(), onLoad: vi.fn(), onUnload: vi.fn() })).toContain('>加载<');
  });
  it('lets the person run models on acceptance inputs and try new content in the same shape', () => {
    const runnable = { ...files, 'experiments/e001-embed/model/invoke.json': file({ argv: ['python3', 'predict.py'] }) };
    const html = render(AcceptanceView, { files: runnable, job: { id: 'j', state: 'running', experiments: ['e001-embed'], started_at: '' }, onRun: vi.fn(), onTry: vi.fn() });
    for (const value of ['E001', '向量加逻辑回归', '可拼搭的软件', '正在让 E001', '试一段新内容', '标题', '正文', '不会写入研究记录']) expect(html).toContain(value);
    expect(inputTemplate([{ sample_id: 'x', input: post }])).toEqual(['title', 'text']);
    expect(inputTemplate([{ sample_id: 'x', input: '纯文本' }])).toBeNull();
    expect(render(AcceptanceView, { files: { 'project.json': files['project.json'] }, job: null, onRun: vi.fn(), onTry: vi.fn() })).toContain('还没有可验收的模型');
  });
  it('keeps nodes compact and details led by the conclusion and the change against the parent', () => {
    const items = experiments(files);
    const results = evaluationRuns(files);
    const node = render(ExperimentSummary, { experiment: items[1], evaluation: results.find(run => run.experimentId === 'e001-embed'), delivered: true });
    for (const value of ['E001', '向量加逻辑回归', '交付', '标签 F1', '0.81', '保留']) expect(node).toContain(value);
    const details = render(ExperimentDetails, { experiment: items[1], experimentsById: new Map(items.map(item => [item.id, item])), results, files, currentVersion: 'v1', delivered: true, onOpenAcceptance: vi.fn() });
    for (const value of ['比关键词更稳。', '+0.19 对比 E000', '做了什么', '评测', '怎么用', '交付模型']) expect(details).toContain(value);
    expect(render(SamplesView, { source: { kind: 'inline', rows: [], sha256: '' }, outputs: true })).toContain('没有逐例输出');
    // Long tables show one page at a time; paged files load their page on request.
    const many = Array.from({ length: 230 }, (_, i) => ({ sample_id: `s${i}`, input: `第 ${i} 条`, output: 'x' }));
    const first = render(SamplesView, { source: { kind: 'inline', rows: many, sha256: '' }, outputs: true });
    expect(first).toContain('第 1 / 3 页');
    expect(first).toContain('1 / 230');
    expect(first).not.toContain('s100');
    expect(render(SamplesView, { source: { kind: 'paged', path: 'experiments/e/evals/r/outputs.jsonl', file: { sha256: 'c'.repeat(64), size: 9, rows: 4677 } }, outputs: true })).toContain('正在读取第 1 页');
    const review = render(ReviewView, { files, source: { kind: 'inline', rows: many.map(row => ({ ...row, reference: '甲', reference_status: 'draft' })), sha256: 'd'.repeat(64) } });
    expect(review).toContain('已看 0 / 230');
    expect(review).toContain('第 1 / 3 页');
  });
  it('keeps the final check apart from development scores and shows how often it ran', () => {
    const split = { ...files,
      'evaluation/v1/samples.jsonl': file([{ sample_id: 's1', input: post, reference: ['产品与商业'] }, { sample_id: 's2', input: post, reference: ['写作'], split: 'final' }]),
      'experiments/e001-embed/evals/f1/config.json': file({ evaluation_version: 'v1', evaluation_sha256: 'e'.repeat(64), split: 'final' }),
      'experiments/e001-embed/evals/f1/status.json': file({ state: 'succeeded', metrics: { f1: 0.55 }, completed_at: '2030-01-01T00:00:00Z' }) };
    const runs = evaluationRuns(split).filter(run => run.experimentId === 'e001-embed');
    expect(preferredEvaluation(runs, 'v1')?.metrics.f1).toBe(0.81);
    expect(preferredEvaluation(runs, 'v1', 'final')?.metrics.f1).toBe(0.55);
    const overview = render(EvaluationView, { files: split, currentVersion: 'v1', selection: '', onSelect: vi.fn(), initialTab: 'overview' });
    for (const value of ['开发样例 1 条，最终检查 1 条', '已运行 1 次']) expect(overview).toContain(value);
    const unsplit = { ...files, 'evaluation/v1/definition.json': file({ ...(files['evaluation/v1/definition.json'].content as object), no_final_reason: '只有 12 篇文章' }) };
    expect(render(EvaluationView, { files: unsplit, currentVersion: 'v1', selection: '', onSelect: vi.fn(), initialTab: 'overview' })).toContain('没有另留最终检查：只有 12 篇文章');
  });
  it('lets the person judge each acceptance output and shows when feedback was sent', () => {
    const props = { files, job: null, onRun: vi.fn(), onTry: vi.fn() };
    expect(render(AcceptanceView, props)).not.toContain('这个输出好不好');
    const judging = render(AcceptanceView, { ...props, onFeedback: vi.fn() });
    for (const value of ['这个输出好不好', '>好<', '不好']) expect(judging).toContain(value);
    const answered = { ...files, 'responses/r1.json': file({ id: 'r1', kind: 'acceptance', target: { path: 'comparison/outputs.jsonl', sha256: 'a'.repeat(64) }, created_at: '2030-01-01T00:00:00Z', decision: 'submit',
      items: [{ sample_id: 'p1', experiment_id: 'e001-embed', verdict: 'bad', note: '少了旅行' }] }) };
    expect(render(AcceptanceView, { ...props, files: answered, onFeedback: vi.fn() })).toContain('这批输出的意见已提交（1 条）');
  });
});
