import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { EvaluationView, evaluationSamples, SamplesView } from './EvaluationView';
import type { ResearchFile, Snapshot } from './model';

const file = (content: unknown): ResearchFile => ({ content, sha256: 'a'.repeat(64) });
const files: Snapshot['files'] = {};
for (const version of ['v1', 'v2']) {
  files[`evaluation/${version}/definition.json`] = file({
    version, description: `说明 ${version}`, rubric: `评分规则 ${version}`,
    metrics: [{ id: 'quality', label: `质量 ${version}`, direction: 'maximize' }],
    command: ['hidden-command'], internal_metadata: 'hidden-definition-details',
  });
  files[`evaluation/${version}/samples.jsonl`] = file([
    { sample_id: `technical-first-${version}`, input: { message: `输入 ${version}`, attachment: ['<script>unsafe</script>'] }, reference: { category: `参考 ${version}` }, labels: ['代表性样例'], processing: 'hidden-processing' },
    { sample_id: `technical-second-${version}`, label: '长留言', input: `第二例 ${version}` },
  ]);
}
function render(selection: string, source = files) {
  return renderToStaticMarkup(createElement(EvaluationView, { files: source, currentVersion: 'v2', selection, onSelect: vi.fn() }));
}

describe('evaluation definitions and fixed samples', () => {
  it('switches versions without leaking another version’s samples or technical metadata', () => {
    for (const [selected, other] of [['v1', 'v2'], ['v2', 'v1']]) {
      const html = render(`evaluation/${selected}/definition.json`);
      for (const phrase of [`说明 ${selected}`, `评分规则 ${selected}`, `质量 ${selected}`, `输入 ${selected}`, `参考 ${selected}`, '长留言', '代表性样例', '1 / 2', '下一例']) expect(html).toContain(phrase);
      for (const phrase of [`输入 ${other}`, `参考 ${other}`, '<script>', 'technical-first', 'technical-second', 'hidden-', '<details', '完整定义']) expect(html).not.toContain(phrase);
      expect(html).toContain(`value="evaluation/${selected}/definition.json" selected`);
    }
  });
  it('uses the current definition if the selected definition is unavailable', () => {
    expect(render('evaluation/missing/definition.json')).toContain('输入 v2');
  });
  it('only reads samples beside a valid definition path', () => {
    expect(evaluationSamples(files, 'evaluation/v1/definition.json')).toHaveLength(2);
    for (const path of ['private/definition.json', '/etc/definition.json', 'evaluation/../definition.json', 'evaluation/v1/nested/definition.json']) {
      expect(evaluationSamples({ ...files, [path.replace('/definition.json', '/samples.jsonl')]: file([{ input: 'must not appear' }]) }, path)).toBeNull();
    }
  });
  it('supports draft samples, optional references and empty sample files', () => {
    const draft: Snapshot['files'] = {
      'evaluation/draft/definition.json': file({ description: '校准', metrics: [] }),
      'evaluation/draft/samples.jsonl': file([{ input: ['尚待校准', { question: '真实输入' }] }]),
    };
    const html = render('evaluation/draft/definition.json', draft);
    expect(html).toContain('草稿尚未发布');
    expect(html).toContain('尚待校准');
    expect(html).not.toContain('参考输出');
    expect(html).not.toContain('<h4>标签');
    expect(render('', { ...draft, 'evaluation/draft/samples.jsonl': file([]) })).toContain('样例文件为空');
  });
  it('offers clean empty and unavailable sample states', () => {
    expect(render('', {})).toContain('尚无评测定义');
    const unavailable = { ...files };
    delete unavailable['evaluation/v2/samples.jsonl'];
    expect(render('', unavailable)).toContain('尚无可浏览样例');
    expect(render('', unavailable)).not.toContain('输入 v2');
    expect(render('', unavailable)).not.toContain('<form');
  });
  it('renders output, reference and finite scores instead of dumping output records', () => {
    const html = renderToStaticMarkup(createElement(SamplesView, { outputs: true, metricLabels: { quality: '质量' }, rows: [{ sample_id: 'hidden-sample-id', input: '问题', output: { answer: '回答内容' }, reference: '参考内容', scores: { quality: 0.9, invalid: NaN }, internal_metadata: 'hidden-data' }] }));
    for (const phrase of ['问题', '回答内容', '参考内容', '质量', '0.9']) expect(html).toContain(phrase);
    for (const phrase of ['hidden-', 'NaN', 'invalid', '<pre']) expect(html).not.toContain(phrase);
  });
  it('shows each reference review status and a summary, but not on run outputs', () => {
    const reviewed: Snapshot['files'] = {
      'evaluation/v3/definition.json': file({ version: 'v3', description: '审阅', metrics: [] }),
      'evaluation/v3/samples.jsonl': file([
        { sample_id: 'a', input: '一', reference: '甲', reference_status: 'confirmed' },
        { sample_id: 'b', input: '二', reference: '乙', reference_status: 'corrected' },
        { sample_id: 'c', input: '三', reference: '丙', reference_status: 'invented' },
        { sample_id: 'd', input: '四' },
      ]),
    };
    const html = render('evaluation/v3/definition.json', reviewed);
    expect(html).toContain('参考答案：已确认 1 · 已修正 1 · 待审核 1');
    expect(html).toContain('分数只表示与草稿的一致程度');
    expect(html).toContain('review-confirmed');
    const outputs = renderToStaticMarkup(createElement(SamplesView, { outputs: true, rows: [{ input: '一', output: '甲', reference: '甲' }] }));
    expect(outputs).not.toContain('待审核');
    expect(render('evaluation/v1/definition.json')).toContain('待审核 1');
  });
  it('has accessible pagination limits and explicit missing outputs', () => {
    const html = renderToStaticMarkup(createElement(SamplesView, { outputs: true, rows: [{ input: '问题' }] }));
    expect(html).toContain('<button disabled="">上一例');
    expect(html).toContain('<button disabled="">下一例');
    expect(html).toContain('暂无该输入的输出');
  });
});
