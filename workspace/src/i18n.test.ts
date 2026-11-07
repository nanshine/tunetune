import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it } from 'vitest';
import { labels, language, list, resolveLanguage, setLanguage, t } from './i18n';
import { en } from './messages';
import { outcomeLabels, type Snapshot } from './model';
import { ProposalView } from './ProjectBrief';

const directory = import.meta.dirname;
const sources = readdirSync(directory).filter(name => /\.tsx?$/.test(name) && !name.endsWith('.test.ts') && !['i18n.ts', 'messages.ts'].includes(name))
  .map(name => [name, readFileSync(join(directory, name), 'utf8')] as const);
const CJK = /[一-鿿]/;
const literal = /\bt\('((?:[^'\\]|\\.)*)'/g;
const placeholders = (value: string) => [...value.matchAll(/\{(\w+)\}/g)].map(match => match[1]).sort();

// Every interface string is either passed to t() or a value in a labels() map, so both are the keys in use.
function keys() {
  const found = new Set<string>();
  for (const [name, source] of sources) {
    for (const match of source.matchAll(literal)) found.add(match[1]);
    for (const line of source.split('\n')) if (line.includes('labels({')) for (const match of line.matchAll(/'((?:[^'\\]|\\.)*)'/g)) if (CJK.test(match[1])) found.add(match[1]);
    if (name === 'App.tsx') for (const match of source.matchAll(/(?:label|title): '([^']*)'/g)) found.add(match[1]);
  }
  return found;
}

afterEach(() => setLanguage('zh'));

describe('interface language', () => {
  it('translates every interface string with matching placeholders and no unused entries', () => {
    const used = keys();
    expect([...used].filter(key => !Object.hasOwn(en, key))).toEqual([]);
    expect(Object.keys(en).filter(key => !used.has(key))).toEqual([]);
    for (const [key, value] of Object.entries(en)) expect(placeholders(value), key).toEqual(placeholders(key));
  });
  it('keeps Chinese text out of source code except through t() and label maps', () => {
    const stray = sources.flatMap(([name, source]) => source.split('\n').map((line, index) => [name, index + 1, line] as const))
      .filter(([name, , line]) => !line.includes('labels({') && !(name === 'App.tsx' && /label: '[^']*', title: '/.test(line)) && CJK.test(line.replace(literal, '')))
      .map(([name, number]) => `${name}:${number}`);
    expect(stray).toEqual([]);
  });
  it('follows the project language before the browser and falls back to English for other languages', () => {
    expect(resolveLanguage('zh-CN', 'en-US')).toBe('zh');
    expect(resolveLanguage('zh-Hant', 'en-US')).toBe('zh');
    expect(resolveLanguage('en', 'zh-CN')).toBe('en');
    expect(resolveLanguage('ja', 'zh-CN')).toBe('en');
    expect(resolveLanguage(undefined, 'zh-TW')).toBe('zh');
    expect(resolveLanguage('  ', 'fr-FR')).toBe('en');
    expect(resolveLanguage(null, undefined)).toBe('zh');
  });
  it('fills placeholders, joins lists and re-reads label maps after a language change', () => {
    const map = labels({ ok: '成功' });
    setLanguage('en');
    expect(language()).toBe('en');
    expect(t('第 {round} 轮', { round: 2 })).toBe('Round 2');
    expect(t('没有这条文本')).toBe('没有这条文本');
    expect(list(['E1', 'E2'])).toBe('E1, E2');
    expect(map.ok).toBe('Succeeded');
    expect(outcomeLabels.keep).toBe('Keep');
    expect(Object.hasOwn(outcomeLabels, 'keep')).toBe(true);
    setLanguage('zh');
    expect(map.ok).toBe('成功');
    expect(list(['E1', 'E2'])).toBe('E1、E2');
  });
  it('renders the interface in English while leaving research content as written', () => {
    setLanguage('en');
    const files: Snapshot['files'] = { 'proposal.json': { sha256: 'a'.repeat(64), content: { summary: '为博客文章推荐标签。', goal: 'Tag new posts', examples: [] } } };
    const html = renderToStaticMarkup(createElement(ProposalView, { files, waiting: null, onRespond: async () => {} }));
    expect(html).toContain('Goal');
    expect(html).toContain('为博客文章推荐标签。');
    expect(html).not.toContain('目标');
  });
});
