import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { AcceptanceView } from './AcceptanceView';
import type { ResearchFile, Snapshot } from './model';

const workspace = vi.hoisted(() => ({ snapshot: null as Snapshot | null, connectionError: null, renameProject: vi.fn() }));
vi.mock('./useWorkspace', () => ({ useWorkspace: () => workspace }));
const file = (content: unknown): ResearchFile => ({ content, sha256: 'a'.repeat(64) });
const files: Snapshot['files'] = {
  'project.json': file({ schema_version: 1, name: '研究空间主题' }),
  'goal.json': file({ summary: '整理客户留言', examples: [] }),
  'feedback/requests/old.json': file({ id: 'old', title: '历史问题', prompt: '待回答问题' }),
  'feedback/incoming/old.json': file({ id: 'old', text: '历史意见' }),
  'acceptance/set/outputs.jsonl': file([
    { sample_id: 'one', input: '客户留言', outputs: { first: '第一版输出', second: '第二版输出' } },
    { sample_id: 'two', input: '另一条留言', outputs: { first: '另一个输出' } },
  ]),
};
const releases: [string, Record<string, unknown>][] = [
  ['releases/first.json', { id: 'first', artifact_id: 'model-1' }],
  ['releases/second.json', { id: 'second', artifact_id: 'model-2' }],
];
const baseProps = { files, projectName: '研究空间主题', releases, acceptances: [['acceptance/set/config.json', { id: 'set' }]] as [string, Record<string, unknown>][], initialReleasePath: 'releases/second.json', connectionError: null, syncError: null, connected: true, onBack: vi.fn() };

beforeEach(() => { workspace.snapshot = { files, revision: '1', synced_at: '', error: null }; });

describe('read-only research panel', () => {
  it('keeps the brief and editable name without feedback or review entry points', () => {
    const html = renderToStaticMarkup(createElement(App));
    expect(html).toContain('整理客户留言');
    expect(html).toContain('编辑项目名称：研究空间主题');
    expect(html).toMatch(/class="project-name-trigger"[^>]*><span>研究空间主题<\/span><\/button>/);
    for (const phrase of ['协作反馈', '研究复盘', '补充说明', '补充资源', '回答问题', '反馈这个实验', '历史意见', '<textarea', 'feedback-form']) expect(html).not.toContain(phrase);
    expect(workspace.renameProject).not.toHaveBeenCalled();
  });

  it('shows output comparison and sample navigation without submission forms', () => {
    const html = renderToStaticMarkup(createElement(AcceptanceView, baseProps));
    for (const phrase of ['第一版输出', '第二版输出', '客户留言', '另一条留言', '交换左右交付模型', '1 / 2']) expect(html).toContain(phrase);
    for (const phrase of ['<form', '<textarea', '验收意见', '本例偏好', '保存并下一例', 'acceptance-notes']) expect(html).not.toContain(phrase);
  });

  it('keeps missing outputs read-only and directs generation to the Agent client', () => {
    const html = renderToStaticMarkup(createElement(AcceptanceView, { ...baseProps, files: { ...files, 'acceptance/set/outputs.jsonl': file([{ sample_id: 'missing', input: '输入', outputs: { first: '已有输出' } }]) } }));
    expect(html).toContain('暂无该输入的输出');
    expect(html).toContain('Agent 客户端');
    expect(html).not.toContain('<form');
    expect(html).not.toContain('保存生成请求');
  });

  it('explains same-model comparisons without prompting for preferences', () => {
    const html = renderToStaticMarkup(createElement(AcceptanceView, { ...baseProps, releases: releases.slice(0, 1) }));
    expect(html).toContain('左右为同一交付模型');
    expect(html).not.toContain('偏好');
    expect(html).toMatch(/aria-label="交换左右交付模型" disabled/);
  });

  it('handles empty releases and sample sets without a feedback fallback', () => {
    const html = renderToStaticMarkup(createElement(AcceptanceView, { ...baseProps, releases: [], acceptances: [] }));
    expect(html).toContain('尚无对照样例');
    expect(html).toContain('暂无交付模型');
    expect(html).not.toContain('<form');
  });
});
