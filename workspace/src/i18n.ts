import { en } from './messages';

// Interface text is written in Chinese in the source and looked up in a dictionary for other languages.
// Research content comes from the Agent in the person's own language and is never translated here.
export type Language = 'zh' | 'en';

let current: Language = resolveLanguage(undefined, typeof navigator === 'undefined' ? undefined : navigator.language);

// The Agent records the conversation language in project.json; the browser language only fills in before then.
export function resolveLanguage(project: unknown, browser?: string): Language {
  const tag = typeof project === 'string' && project.trim() ? project : browser ?? '';
  return /^zh\b/i.test(tag.trim()) ? 'zh' : tag.trim() ? 'en' : 'zh';
}

export function setLanguage(language: Language) {
  current = language;
  if (typeof document !== 'undefined') document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
}

export function language(): Language {
  return current;
}

export function t(text: string, values?: Record<string, string | number>): string {
  const template = current === 'zh' ? text : en[text] ?? text;
  return values ? template.replace(/\{(\w+)\}/g, (match, key: string) => Object.hasOwn(values, key) ? String(values[key]) : match) : template;
}

// Label maps keep their Chinese source values and translate on every read, so they follow language changes.
export function labels<T extends Record<string, string>>(source: T): T {
  return new Proxy(source, { get: (target, key) => typeof key === 'string' && Object.hasOwn(target, key) ? t(target[key]) : Reflect.get(target, key) });
}

// Lists join with the language's own separator.
export function list(items: string[]): string {
  return items.join(current === 'zh' ? '、' : ', ');
}
