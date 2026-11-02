import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { GoalView, ResourcesView } from './ProjectBrief';

describe('project brief', () => {
  it('renders saved content and incomplete examples without inventing a plan', () => {
    const html = renderToStaticMarkup(createElement(GoalView, { goal: {
      revision: 2, summary: '整理客户留言', sections: [{ title: '使用方式', body: '每天整理一次' }],
      examples: [{ id: 'message-1', input: '<script>private message</script>' }], proposal: '先调查有哪些现成数据',
    } }));
    for (const phrase of ['整理客户留言', '使用方式', '每天整理一次', '先调查有哪些现成数据', '待一起确认', '修订 2']) expect(html).toContain(phrase);
    expect(html).not.toContain('<script>');
    expect(html).not.toContain('message-1');
  });

  it('distinguishes a discovered resource from a ready resource with text as well as color', () => {
    const html = renderToStaticMarkup(createElement(ResourcesView, { resources: { items: [
      { id: 'a', title: '公开数据', type: 'dataset', purpose: '了解留言类型', status: 'available', source: '公开目录' },
      { id: 'b', title: '已有留言', type: 'data', purpose: '确认实际需要', status: 'ready', path: 'data/messages.jsonl' },
    ] } }));
    for (const phrase of ['可获取', '已就绪', '了解留言类型', '公开目录', 'data/messages.jsonl']) expect(html).toContain(phrase);
    expect(html).toContain('resource-state available');
    expect(html).toContain('resource-state ready');
  });
});
