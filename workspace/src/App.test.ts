import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { ComparisonView } from './ComparisonView';
import type { ResearchFile, Snapshot } from './model';

const workspace = vi.hoisted(() => ({ snapshot: null as Snapshot | null, connectionError: null as string | null, renameProject: vi.fn() }));
vi.mock('./useWorkspace', () => ({ useWorkspace: () => workspace }));
const file = (content: unknown): ResearchFile => ({ content, sha256: 'a'.repeat(64) });
const files: Snapshot['files'] = {
  'project.json': file({ schema_version: 2, name: '研究空间主题', deliveries: ['first', 'second'] }),
  'proposal.json': file({ summary: '整理客户留言', sections: [], examples: [] }),
  'experiments/first/config.json': file({ title: '基础模型', model_name: 'SmallLM', method: '固定规则' }),
  'experiments/first/status.json': file({ state: 'succeeded', model_path: 'experiments/first/model/output.bin' }),
  'experiments/second/config.json': file({ title: '领域适配模型', model_name: 'SmallLM', method: 'LoRA' }),
  'experiments/second/status.json': file({ state: 'succeeded', model_path: 'experiments/second/model/output.bin' }),
  'comparison/outputs.jsonl': file([
    { sample_id: 'hidden-first-sample', input: '客户留言', outputs: { first: '第一版输出', second: '第二版输出' } },
    { sample_id: 'hidden-second-sample', input: '另一条留言', outputs: { first: '另一个输出' } },
  ]),
};
const baseProps = { files, projectName: '研究空间主题', initialExperimentId: 'second', connectionError: null, syncError: null, connected: true, onBack: vi.fn() };

beforeEach(() => { workspace.snapshot = { files, revision: '1', synced_at: '', error: null }; workspace.connectionError = null; vi.clearAllMocks(); });

describe('read-only research panel', () => {
  it('opens the proposal by default and retains editable project name', () => {
    const html = renderToStaticMarkup(createElement(App));
    expect(html).toContain('整理客户留言');
    expect(html).toContain('class="left-dock open"');
    expect(html).toContain('编辑项目名称：研究空间主题');
    expect(html).toMatch(/class="project-name-trigger"[^>]*><span>研究空间主题<\/span><\/button>/);
    expect(html).toMatch(/<button class="primary comparison-entry">[\s\S]*?模型对比<\/button>/);
    for (const phrase of ['<form', '<textarea', '运行任务', '运行日志', '候选方案']) expect(html).not.toContain(phrase);
    expect(workspace.renameProject).not.toHaveBeenCalled();
  });
  it('preserves accessible disconnected and initial empty states', () => {
    workspace.connectionError = '连接失败';
    const html = renderToStaticMarkup(createElement(App));
    expect(html).toContain('role="alert"');
    expect(html).toContain('保留最后可用内容');
    expect(html).toMatch(/class="project-name-trigger" disabled/);
    workspace.snapshot = null;
    workspace.connectionError = null;
    const empty = renderToStaticMarkup(createElement(App));
    expect(empty).toContain('等待研究文件');
    expect(empty).toContain('正在连接');
    expect(empty).toContain('模型对比');
  });
  it('always exposes comparison even without deliveries', () => {
    workspace.snapshot = { files: { 'project.json': file({ schema_version: 2, name: '新研究', deliveries: [] }) }, revision: '2', synced_at: '', error: null };
    const html = renderToStaticMarkup(createElement(App));
    expect(html).toContain('模型对比');
    expect(html).toContain('实验谱系画布');
    expect(html).toContain('研究提案');
  });
});

describe('dedicated model output comparison', () => {
  it('shows outputs keyed by experiment, named selectors and sample navigation without forms', () => {
    const html = renderToStaticMarkup(createElement(ComparisonView, baseProps));
    for (const phrase of ['第一版输出', '第二版输出', '客户留言', '另一条留言', '交换左右模型', '1 / 2', '返回工作台', '基础模型', '领域适配模型', 'SmallLM', 'LoRA']) expect(html).toContain(phrase);
    for (const phrase of ['<form', '<textarea', '<details', 'hidden-', 'output.bin', '样例集', '固定样例记录']) expect(html).not.toContain(phrase);
  });
  it('keeps missing outputs read-only and directs generation to the Agent conversation', () => {
    const html = renderToStaticMarkup(createElement(ComparisonView, { ...baseProps, files: { ...files, 'comparison/outputs.jsonl': file([{ sample_id: 'missing', input: '输入', outputs: { first: '已有输出' } }]) } }));
    expect(html).toContain('暂无该输入的输出');
    expect(html).toContain('Agent 会话');
    expect(html).not.toContain('<form');
  });
  it('explains a single-model comparison and disables swap', () => {
    const html = renderToStaticMarkup(createElement(ComparisonView, { ...baseProps, files: { ...files, 'project.json': file({ deliveries: ['first'] }) } }));
    expect(html).toContain('左右为同一模型');
    expect(html).toMatch(/aria-label="交换左右模型" disabled/);
    expect(html).not.toContain('第二版输出');
  });
  it('handles missing and empty comparison files explicitly', () => {
    const missing = { ...files };
    delete missing['comparison/outputs.jsonl'];
    const html = renderToStaticMarkup(createElement(ComparisonView, { ...baseProps, files: missing }));
    expect(html).toContain('尚无对照样例');
    expect(html).toContain('没有可显示的输入');
    const empty = renderToStaticMarkup(createElement(ComparisonView, { ...baseProps, files: { ...missing, 'comparison/outputs.jsonl': file([]) } }));
    expect(empty).toContain('对照输出文件为空');
  });
  it('shows shared inputs but no model output if deliveries are empty or not usable', () => {
    for (const overrides of [
      { 'project.json': file({ deliveries: [] }) },
      { 'project.json': file({ deliveries: ['first'] }), 'experiments/first/status.json': file({ state: 'completed', model_path: 'experiments/first/model/output.bin' }) },
      { 'project.json': file({ deliveries: ['first'] }), 'experiments/first/status.json': file({ state: 'succeeded' }) },
    ] as Snapshot['files'][]) {
      const html = renderToStaticMarkup(createElement(ComparisonView, { ...baseProps, files: { ...files, ...overrides } }));
      expect(html).toContain('暂无可对比的交付模型');
      expect(html).toContain('输入（两侧相同）');
      expect(html).toContain('客户留言');
      expect(html).not.toContain('第一版输出');
    }
  });
  it.each([null, '', '   ', {}])('treats a missing or invalid output (%s) as missing', value => {
    const html = renderToStaticMarkup(createElement(ComparisonView, { ...baseProps, files: { ...files, 'comparison/outputs.jsonl': file([{ input: '输入', outputs: { first: value } }]) } }));
    expect(html.match(/暂无该输入的输出/g)).toHaveLength(2);
  });
  it('escapes untrusted sample and output text', () => {
    const html = renderToStaticMarkup(createElement(ComparisonView, { ...baseProps, files: { ...files, 'comparison/outputs.jsonl': file([{ input: '<script>input</script>', outputs: { first: '<script>output</script>' } }]) } }));
    expect(html).not.toContain('<script>');
    expect(html).toContain('&lt;script&gt;output');
  });
});
