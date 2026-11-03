import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { comparableModels, comparisonSamples, deliveredModels, evaluationRuns, parseSnapshot } from './model';
import type { ResearchFile, Snapshot } from './model';
import { RecordView, mediaUrl } from './RecordView';
import { ProposalView, ResourcesView } from './ProjectBrief';
import { ExperimentDetails } from './ExperimentDetails';
import { experiments } from './model';

const file = (content: unknown): ResearchFile => ({ content, sha256: 'a'.repeat(64) });
const files: Snapshot['files'] = { 'project.json': file({ schema_version: 4, deliveries: ['local', 'api'] }) };
for (const id of ['local', 'api']) {
  files[`experiments/${id}/config.json`] = file({ role: id === 'api' ? 'reference' : 'baseline' });
  files[`experiments/${id}/status.json`] = file({ state: 'succeeded', target: { kind: id, path: `experiments/${id}/model`, sha256: 'b'.repeat(64) } });
  files[`experiments/${id}/evals/a/config.json`] = file({ evaluation_version: 'v1', evaluation_sha256: 'c'.repeat(64) });
  files[`experiments/${id}/evals/a/status.json`] = file({ state: 'succeeded', usage: { cost: 0, currency: 'USD', latency_seconds: 2 } });
  files[`experiments/${id}/evals/a/outputs.jsonl`] = file([{ sample_id: 'same', input: '问题', output: id === 'api' ? { answer: '参照答案' } : ['本地答案'] }]);
}

describe('format 4 research behavior', () => {
  it('keeps API references available for comparison and out of local deliveries', () => {
    expect(comparableModels(files).map(item => item.id)).toEqual(['api', 'local']);
    expect(deliveredModels(files).map(item => item.id)).toEqual(['local']);
    const html = renderToStaticMarkup(createElement(ExperimentDetails, { experiment: experiments(files)[0], experimentsById: new Map(), results: evaluationRuns(files), files, currentVersion: 'v1', delivered: false, onOpenAcceptance: () => {} }));
    for (const value of ['质量参照', '在线 API', '远端模型完全复现']) expect(html).toContain(value);
  });
  it('reuses compatible measured outputs, and never silently merges other inputs or hashes', () => {
    expect(comparisonSamples(files, 'local', 'api', 'v1')).toEqual([{ sample_id: 'same', input: '问题', outputs: { local: ['本地答案'], api: { answer: '参照答案' } } }]);
    expect(comparisonSamples({ ...files, 'experiments/api/evals/a/config.json': file({ evaluation_version: 'v1', evaluation_sha256: 'd'.repeat(64) }) }, 'local', 'api', 'v1')).toEqual([]);
    expect(comparisonSamples({ ...files, 'experiments/api/evals/a/config.json': file({ evaluation_version: 'v1', evaluation_sha256: 'c'.repeat(64), inputs: [{ path: 'data/external.jsonl', sha256: 'e'.repeat(64) }] }) }, 'local', 'api', 'v1')).toEqual([]);
    const input = { path: 'data/external.jsonl', sha256: 'e'.repeat(64) };
    const other = { path: 'data/other.jsonl', sha256: 'f'.repeat(64) };
    const matching = { ...files, 'experiments/api/evals/a/config.json': file({ evaluation_version: 'v1', evaluation_sha256: 'c'.repeat(64), inputs: [input, other] }), 'experiments/local/evals/a/config.json': file({ evaluation_version: 'v1', evaluation_sha256: 'c'.repeat(64), inputs: [other, input] }) };
    expect(comparisonSamples(matching, 'local', 'api', 'v1')).toHaveLength(1);
    expect(comparisonSamples({ ...files, 'experiments/api/evals/a/outputs.jsonl': file([{ sample_id: 'same', input: '不同问题', output: '答案' }]) }, 'local', 'api', 'v1')).toEqual([]);
  });
  it('rejects old projects and invalid usage without replacing usable contents', () => {
    const snapshot = { files, revision: 'r', synced_at: '', error: null };
    expect(parseSnapshot(snapshot).files).toBe(files);
    expect(() => parseSnapshot({ ...snapshot, files: { ...files, 'project.json': file({ schema_version: 2, deliveries: [] }) } })).toThrow('格式 4');
    for (const usage of [{ cost: -1 }, { latency_seconds: Infinity }, { currency: 1 }, { api_key: 'secret' }]) expect(() => parseSnapshot({ ...snapshot, files: { ...files, 'experiments/api/status.json': file({ state: 'failed', usage }) } })).toThrow('用量');
  });
  it('shows researched alternatives, resource plans and safe primary-source links', () => {
    const resources = { items: [{ id: 'm', title: '语义模型', purpose: '识别语义', source: 'https://example.com/model', preparation: '约 100 MB，保存到 models/', access: '仅本地使用' }] };
    const proposal = { summary: '标签分类', examples: [], approaches: [{ title: '语义分类', roles: ['recommended', 'reference'], rationale: '用中文向量模型', limitations: '需验证长文', resource_ids: ['m'] }],
      sources: [{ title: '模型卡', url: 'https://example.com/docs' }, { title: '坏链接', url: 'javascript:alert(1)' }] };
    const html = renderToStaticMarkup(createElement(ProposalView, { files: { 'proposal.json': file(proposal), 'resources.json': file(resources) } })) + renderToStaticMarkup(createElement(ResourcesView, { resources }));
    for (const value of ['推荐路线', '质量参照', '语义模型', '识别语义', 'href="https://example.com/docs"', 'example.com']) expect(html).toContain(value);
    expect(html).not.toContain('javascript:');
  });
});

describe('explicit research attachments', () => {
  it.each(['../secrets.png', '/etc/passwd', '.env', 'data/.hidden/image.png', 'https://example.com/a.png', 'data/a%2f.png', 'data/a.png?x=1', 'data\\a.png', 'secrets/a.png'])('does not request unsafe attachment %s', path => {
    expect(mediaUrl(path)).toBeNull();
    const html = renderToStaticMarkup(createElement(RecordView, { value: { type: 'image', path } }));
    expect(html).not.toContain('src=');
    expect(html).toContain('不可预览');
  });
  it.each([['image', '<img'], ['audio', '<audio'], ['video', '<video'], ['file', '<a']])('renders explicit %s references through the confined media endpoint', (type, tag) => {
    const html = renderToStaticMarkup(createElement(RecordView, { value: { type, path: 'data/中文 sample.bin', title: '真实附件' } }));
    expect(html).toContain(tag);
    expect(html).toContain('/api/media?path=data%2F');
    expect(html).toContain('真实附件');
  });
  it('does not interpret arbitrary paths or untrusted HTML as media', () => {
    const html = renderToStaticMarkup(createElement(RecordView, { value: { path: 'private/file.png', text: '<script>alert(1)</script>' } }));
    expect(html).not.toContain('<img');
    expect(html).not.toContain('<script>');
  });
});
