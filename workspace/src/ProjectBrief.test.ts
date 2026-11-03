import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ProposalView, groupResources, ResourcesView } from './ProjectBrief';
import { resourceStates } from './model';
import type { ResourceState } from './model';

afterEach(() => vi.useRealTimers());

describe('current proposal', () => {
  it('renders summary, sections and incomplete examples without technical metadata', () => {
    const html = renderToStaticMarkup(createElement(ProposalView, { proposal: {
      summary: '整理客户留言', sections: [{ title: '使用方式', body: '每天整理一次' }],
      examples: [{ id: 'hidden-example-id', input: '<script>private message</script>' }],
      internal_metadata: 'must-not-display', updated_at: 'hidden-time',
    } }));
    for (const phrase of ['整理客户留言', '使用方式', '每天整理一次', '待一起补充']) expect(html).toContain(phrase);
    for (const phrase of ['<script>', 'hidden-example-id', 'must-not-display', 'hidden-time']) expect(html).not.toContain(phrase);
  });
  it.each([['feasible', '可行'], ['conditional', '有条件可行'], ['infeasible', '不可行'], ['unknown', '待评估']])('shows %s feasibility and structured examples', (verdict, label) => {
    const html = renderToStaticMarkup(createElement(ProposalView, { proposal: {
      summary: '有依据的提案', feasibility: { verdict, reason: '需先核验资源' },
      examples: [{ input: { message: '真实输入' }, expected_output: ['分类结果'] }],
    } }));
    for (const phrase of [label, '需先核验资源', '真实输入', '分类结果']) expect(html).toContain(phrase);
    expect(html).toContain('<details class="proposal-examples">');
    expect(html).not.toContain('<form');
  });
  it('keeps empty states honest and feasibility optional', () => {
    const html = renderToStaticMarkup(createElement(ProposalView, { proposal: {} }));
    expect(html).toContain('和 Agent 聊聊');
    expect(html).not.toContain('可行性');
  });
});

describe('finite resource cards', () => {
  it('groups Agent-chosen resource types and displays relevant facts inline', () => {
    const items = [
      { title: '留言', type: 'data', path: 'data/messages.jsonl', size: '200 条', status: 'ready' },
      { title: '检查集', type: 'dataset' },
      { title: 'Python', type: 'environment', version: '3.11', status: 'ready' },
      { title: '审阅者', type: '领域支持', location: '本地团队', internal_metadata: { secret: 'must-not-display' } },
      { title: '未分类' },
    ];
    expect(groupResources(items).map(([type, resources]) => [type, resources.length])).toEqual([['数据', 2], ['环境', 1], ['领域支持', 1], ['其他', 1]]);
    const html = renderToStaticMarkup(createElement(ResourcesView, { resources: { items } }));
    for (const phrase of ['data/messages.jsonl · 200 条', 'Python 3.11', '本地团队', '领域支持']) expect(html).toContain(phrase);
    for (const phrase of ['<details', '<dl', '用途待补充', '查看详情', 'must-not-display', '>版本<']) expect(html).not.toContain(phrase);
  });
  it.each(Object.entries(resourceStates))('shows %s with a labeled distinct icon but no visible status word', (state, label) => {
    const html = renderToStaticMarkup(createElement(ResourcesView, { resources: { items: [{ title: '资源', status: state }] } }));
    expect(html).toContain(`class="resource-state ${state}" role="img" title="${label}" aria-label="${label}"`);
    expect(html).not.toContain(`>${label}<`);
    const glyphs = Object.keys(resourceStates).map(state => renderToStaticMarkup(createElement(ResourcesView, { resources: { items: [{ title: '资源', status: state }] } })).match(/<svg[\s\S]*?<\/svg>/)?.[0]);
    expect(new Set(glyphs).size).toBe(5);
  });
  it('uses live readable file, memory, GPU and Python observations', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-11-01T12:00:00Z'));
    const kinds = ['file', 'memory', 'nvidia_gpu', 'python'];
    const details = ['文件存在', '可用内存 8 GB / 16 GB', 'RTX 4090 · 使用率 20%', 'Python 3.11.8'];
    const html = renderToStaticMarkup(createElement(ResourcesView, {
      resources: { items: kinds.map(kind => ({ id: kind, title: kind, monitor: { kind }, status: 'ready', ...(kind === 'file' ? { size: '52 条' } : {}) })) },
      observations: { checked_at: '2026-11-01T12:00:00Z', items: kinds.map((id, index) => ({ id, state: 'ready' as ResourceState, detail: details[index], ...(id === 'file' ? { size: 2048, modified_at: '2026-11-01T11:59:00Z' } : {}) })) },
    }));
    for (const phrase of [...details, '52 条 · 2 KB', '文件修改于']) expect(html).toContain(phrase);
    expect(html).not.toContain('[object Object]');
    expect(html).not.toContain('<details');
    expect(html.replace(/<[^>]*>/g, '')).not.toContain('文件存在');
    expect(html.replace(/<[^>]*>/g, '')).not.toContain('文件修改于');
  });
  it('removes expired facts and never substitutes ready inventory status for missing monitoring', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-11-01T12:01:00Z'));
    const resources = { items: [{ id: 'data', title: '数据', status: 'ready', monitor: { kind: 'file' } }] };
    const observations = { checked_at: '2026-11-01T12:00:00Z', items: [{ id: 'data', state: 'ready' as ResourceState, size: 'expired-size', detail: 'expired-detail' }] };
    for (const props of [{ resources }, { resources, observations }]) {
      const html = renderToStaticMarkup(createElement(ResourcesView, props));
      expect(html).toContain('aria-label="未知"');
      expect(html).not.toContain('expired');
      expect(html).not.toContain('aria-label="已就绪"');
    }
  });
});
