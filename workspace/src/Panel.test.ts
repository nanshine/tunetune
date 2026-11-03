import { createElement } from 'react';
import type { FunctionComponent } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ResearchFile, Snapshot } from './model';
import { evaluationRuns, experiments } from './model';
import { ProposalView, ResourcesView, readableSize } from './ProjectBrief';
import { PlanView } from './PlanView';
import { EvaluationView, SamplesView } from './EvaluationView';
import { ReviewView, parseCorrection } from './ReviewView';
import { AcceptanceView, inputTemplate } from './AcceptanceView';
import { ExperimentSummary } from './Lineage';
import { ExperimentDetails } from './ExperimentDetails';

const workspace = vi.hoisted(() => ({ snapshot: null as Snapshot | null, connectionError: null as string | null, renameProject: vi.fn() }));
vi.mock('./useWorkspace', () => ({ useWorkspace: () => workspace, submitResponse: vi.fn(), runAcceptance: vi.fn(), tryModel: vi.fn() }));
const { App } = await import('./App');

const file = (content: unknown, sha = 'a'): ResearchFile => ({ content, sha256: sha.repeat(64) });
const post = { title: '可拼搭的软件', text: '用多维表格搭一个自己的系统。' };
const files: Snapshot['files'] = {
  'project.json': file({ schema_version: 4, name: '博客标签', current_evaluation: 'v1', deliveries: ['e001-embed'] }),
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

beforeEach(() => { workspace.snapshot = { files, revision: '1', synced_at: '', error: null, view: { revision: 1, open: [], focus: {}, attention: [{ view: 'review', message: '22 篇标签待审阅' }] } }; workspace.connectionError = null; });

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
    const html = render(ProposalView, { files, waiting: '请确认研究提案', onRespond: vi.fn() });
    for (const value of ['请确认研究提案', '确认，开始研究', '需要修改', '目标', '你的例子', '可拼搭的软件', '产品与商业', '采用', '不采用', '16 GB 内存不够', '两轮无提升就停', 'bge 模型卡', 'huggingface.co']) expect(html).toContain(value);
    expect(render(ProposalView, { files, onRespond: vi.fn() })).not.toContain('确认，开始研究');
    const answered = { ...files, 'responses/r1.json': file({ kind: 'proposal', target: { path: 'proposal.json', sha256: 'b'.repeat(64) }, created_at: '2026-11-03T01:00:00Z', decision: 'approve' }) };
    expect(render(ProposalView, { files: answered, waiting: '请确认', onRespond: vi.fn() })).toContain('你已确认');
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
  it('lets the person run models on acceptance inputs and try new content in the same shape', () => {
    const html = render(AcceptanceView, { files, job: { id: 'j', state: 'running', experiments: ['e001-embed'], started_at: '' }, onRun: vi.fn(), onTry: vi.fn() });
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
    expect(render(SamplesView, { rows: [], outputs: true })).toContain('没有逐例输出');
  });
});
