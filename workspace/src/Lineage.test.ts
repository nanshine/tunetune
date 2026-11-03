import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import type { ReactFlowProps } from '@xyflow/react';
import { describe, expect, it, vi } from 'vitest';
import { ExperimentSummary, Lineage } from './Lineage';
import { ExperimentDetails } from './ExperimentDetails';
import { evaluationRuns, experiments, outcomeLabels, preferredEvaluation } from './model';
import type { Outcome, ResearchFile, Snapshot } from './model';

const flow = vi.hoisted(() => ({ props: null as ReactFlowProps | null }));
vi.mock('@xyflow/react', () => ({
  ReactFlow: (props: ReactFlowProps) => { flow.props = props; return null; },
  Background: () => null, Handle: () => null, Position: { Left: 'left', Right: 'right' },
  useReactFlow: () => ({}), useViewport: () => ({ zoom: 1 }),
}));
const file = (content: unknown): ResearchFile => ({ content, sha256: 'a'.repeat(64) });
const files: Snapshot['files'] = {
  'experiments/parent/config.json': file({ title: '起点实验' }),
  'experiments/child/config.json': file({ title: '小模型适配', parent_experiment_id: 'parent', model_name: 'SmallLM', method: 'LoRA', framework: 'PyTorch', hypothesis: '适配领域表达', parameters: { rank: 8, learning_rate: 0.001, internal: { value: 'hidden-object' }, model_path: 'hidden-path' }, execution: { argv: ['hidden-command'] } }),
  'experiments/child/status.json': file({ state: 'succeeded', model_path: 'experiments/child/model/output.bin', model_sha256: 'hidden-hash' }),
  'experiments/child/analysis.json': file({ outcome: 'keep', summary: '独立检查结果改善' }),
  'experiments/child/run.log': file('hidden-training-log'),
  'evaluation/v1/definition.json': file({ metrics: [{ id: 'quality', label: '质量' }] }),
  'experiments/parent/evals/run/config.json': file({ evaluation_version: 'v1' }),
  'experiments/parent/evals/run/status.json': file({ state: 'succeeded', metrics: { quality: 30 } }),
  'experiments/child/evals/run/config.json': file({ evaluation_version: 'v1' }),
  'experiments/child/evals/run/status.json': file({ state: 'succeeded', metrics: { quality: 50 } }),
  'experiments/child/evals/run/outputs.jsonl': file([{ sample_id: 'hidden-sample-id', input: '真实输入', output: '真实输出' }]),
};
const items = experiments(files);
const results = evaluationRuns(files);
const child = items.find(item => item.id === 'child')!;
const summary = { experiment: child, evaluation: preferredEvaluation(results.filter(item => item.experimentId === 'child'), 'v1'), currentVersion: 'v1', delivered: true, onSelect: vi.fn(), onCompare: vi.fn() };

describe('read-only experiment canvas', () => {
  it('retains lineage edges and viewport controls without using ancestry as a metric comparator', () => {
    renderToStaticMarkup(createElement(Lineage, { items, results, currentVersion: 'v1', selected: 'child', deliveries: new Set(['child']), onSelect: vi.fn(), onCompare: vi.fn() }));
    expect(flow.props?.edges).toMatchObject([{ source: 'parent', target: 'child' }]);
    expect(flow.props?.nodes).toHaveLength(2);
    expect(flow.props?.nodes?.find(node => node.id === 'child')?.data).not.toHaveProperty('deltas');
    expect(flow.props?.nodes?.find(node => node.id === 'child')?.data.evaluation).toMatchObject({ id: 'run', version: 'v1', metrics: { quality: 50 } });
    expect(flow.props).toMatchObject({ fitView: true, nodesDraggable: false, minZoom: 0.25, maxZoom: 1.5 });
    const html = renderToStaticMarkup(createElement(ExperimentSummary, summary));
    for (const phrase of ['child', '小模型适配', 'SmallLM', 'LoRA', 'v1', '已交付', '质量', '50', '模型对比']) expect(html).toContain(phrase);
    for (const phrase of ['+20', 'delta', 'hidden-', '适配领域表达', '独立检查结果改善']) expect(html).not.toContain(phrase);
  });
  it.each(Object.entries(outcomeLabels))('renders %s analysis independently of execution success', (outcome, label) => {
    const html = renderToStaticMarkup(createElement(ExperimentSummary, { ...summary, experiment: { ...child, analysis: { ...child.analysis, outcome: outcome as Outcome | 'unknown' } } }));
    expect(html).toContain(label);
    expect(html).toContain('成功');
    expect(html).not.toContain('<form');
  });
  it('does not put incompatible metrics or unverified measurements on nodes', () => {
    const html = renderToStaticMarkup(createElement(ExperimentSummary, { ...summary, currentVersion: 'v2' }));
    expect(html).toContain('尚无同版本结果');
    expect(html).not.toContain('>v1<');
    expect(html).not.toContain('质量');
    const completed = renderToStaticMarkup(createElement(ExperimentSummary, { ...summary, evaluation: { ...summary.evaluation!, state: 'completed' } }));
    expect(completed).toContain('待核验');
    expect(completed).not.toContain('质量');
  });
  it('renders exactly four detail sections with readable evidence and no technical dump', () => {
    const html = renderToStaticMarkup(createElement(ExperimentDetails, { experiment: child, results, files, currentVersion: 'v1', delivered: true, onClose: vi.fn(), onCompare: vi.fn() }));
    expect(html.match(/class="detail-section"/g)).toHaveLength(4);
    for (const phrase of ['为什么做', '怎么做', '结果', '结论', '适配领域表达', '独立检查结果改善', '真实输入', '真实输出', '学习率', '适配秩', 'PyTorch']) expect(html).toContain(phrase);
    for (const phrase of ['hidden-', '<details', '<pre', '<textarea', '实验配置', '日志', 'sha256', 'parent', 'child']) expect(html).not.toContain(phrase);
    expect(html).toContain('value="v1" selected');
    expect(html).not.toContain('value="run"');
  });
  it('keeps successful evidence when a later same-version attempt fails', () => {
    const later = { ...results.find(item => item.experimentId === 'child')!, id: 'later', state: 'failed', metrics: {}, path: 'experiments/child/evals/later/config.json', recordedAt: '2026-11-01' };
    const html = renderToStaticMarkup(createElement(ExperimentDetails, { experiment: child, results: [...results, later], files, currentVersion: 'v1', delivered: false, onClose: vi.fn(), onCompare: vi.fn() }));
    expect(html).toContain('真实输出');
    expect(html).not.toContain('later');
  });
});
