import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { array, object, text } from './model';
import type { JsonObject, PagedFile, Snapshot } from './model';
import { t } from './i18n';

// A JSONL record too large to send whole arrives as a description and is read in pages on request,
// always for the exact version the snapshot described, so a page never mixes two versions of a file.
export const PAGE_SIZE = 100;
export const PagedContext = createContext<Record<string, PagedFile>>({});
export function usePaged(): Record<string, PagedFile> { return useContext(PagedContext); }

export type RowSource = { kind: 'inline'; rows: JsonObject[]; sha256: string } | { kind: 'paged'; path: string; file: PagedFile };

export function rowSource(files: Snapshot['files'], paged: Record<string, PagedFile>, path: string): RowSource | null {
  const file = files[path];
  if (file && Array.isArray(file.content)) return { kind: 'inline', rows: array(file.content).map(object), sha256: file.sha256 };
  return paged[path] ? { kind: 'paged', path, file: paged[path] } : null;
}
export function sourceTotal(source: RowSource | null): number {
  return !source ? 0 : source.kind === 'inline' ? source.rows.length : source.file.rows;
}
export function sourceSha(source: RowSource | null): string {
  return !source ? '' : source.kind === 'inline' ? source.sha256 : source.file.sha256;
}
// The version a response target was shown in, whether sent whole or in pages.
export function targetSha(files: Snapshot['files'], paged: Record<string, PagedFile>, path: string): string | undefined {
  return files[path]?.sha256 ?? paged[path]?.sha256;
}

type Page = { path: string; sha256: string; total: number; rows: JsonObject[] };
async function request(query: URLSearchParams): Promise<Page> {
  const response = await fetch(`api/rows?${query}`, { cache: 'no-store' });
  if (!response.ok) throw new Error(response.status === 409 ? t('文件刚更新，正在重新读取。') : t('读取失败（HTTP {status}）', { status: response.status }));
  const value = object(await response.json());
  if (!Array.isArray(value.rows) || value.rows.some(row => row === null || typeof row !== 'object' || Array.isArray(row))) throw new Error(t('文件通道返回了无效格式'));
  return value as unknown as Page;
}
export function fetchRows(path: string, sha256: string, offset: number, limit: number): Promise<Page> {
  return request(new URLSearchParams({ path, sha256, offset: String(offset), limit: String(limit) }));
}
export function fetchRowsById(path: string, sha256: string, ids: string[]): Promise<Page> {
  const query = new URLSearchParams({ path, sha256 });
  for (const id of ids) query.append('id', id);
  return request(query);
}

type Loaded<T> = { value: T | null; error: string };
function useLoaded<T>(key: string, inline: T | null, load: (() => Promise<T>) | null): Loaded<T> {
  const [state, setState] = useState<{ key: string } & Loaded<T>>({ key: '', value: null, error: '' });
  useEffect(() => {
    if (!load) return;
    let live = true;
    load().then(value => { if (live) setState({ key, value, error: '' }); })
      .catch(cause => { if (live) setState({ key, value: null, error: cause instanceof Error ? cause.message : String(cause) }); });
    return () => { live = false; };
  }, [key]);
  if (inline !== null || !load) return { value: inline, error: '' };
  return state.key === key ? state : { value: null, error: '' };
}

// One page of rows: sliced at once when the file was sent whole, fetched when it is paged.
export function useRowPage(source: RowSource | null, page: number, size = PAGE_SIZE): Loaded<JsonObject[]> {
  const inline = source?.kind === 'inline' ? source.rows.slice(page * size, page * size + size) : null;
  const key = source?.kind === 'paged' ? `${source.path}\u0000${source.file.sha256}\u0000${page}\u0000${size}` : '';
  const load = source?.kind === 'paged' ? () => fetchRows(source.path, source.file.sha256, page * size, size).then(answer => answer.rows) : null;
  return useLoaded(key, source ? inline : [], load);
}

// Rows of a second file matching one page's sample IDs, for side-by-side views.
export function useRowsById(source: RowSource | null, ids: string[]): Loaded<Map<string, JsonObject>> {
  const byId = (rows: JsonObject[]) => new Map(rows.map(row => [text(row.sample_id), row]));
  const inline = useMemo(() => source?.kind === 'inline' ? byId(source.rows) : null, [source]);
  const key = source?.kind === 'paged' ? `${source.path}\u0000${source.file.sha256}\u0000${ids.join('\u0000')}` : '';
  const load = source?.kind === 'paged' && ids.length ? () => fetchRowsById(source.path, source.file.sha256, ids).then(answer => byId(answer.rows)) : null;
  return useLoaded(key, source ? inline ?? (source.kind === 'paged' && !ids.length ? new Map() : null) : new Map(), load);
}
