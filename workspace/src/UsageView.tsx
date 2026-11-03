import type { Usage } from './model';

export function UsageView({ usage }: { usage: Usage }) {
  const values: string[] = [];
  if (typeof usage.requests === 'number') values.push(`${usage.requests.toLocaleString()} 次请求`);
  if (typeof usage.input_tokens === 'number' || typeof usage.output_tokens === 'number') values.push(`输入 / 输出 ${usage.input_tokens?.toLocaleString() ?? '未知'} / ${usage.output_tokens?.toLocaleString() ?? '未知'} tokens`);
  if (typeof usage.cost === 'number') values.push(`费用 ${usage.cost.toLocaleString()} ${usage.currency || '币种未记录'}`);
  if (typeof usage.latency_seconds === 'number') values.push(`耗时 ${usage.latency_seconds.toLocaleString()} 秒`);
  return values.length ? <p className="usage-facts">{values.join(' · ')}</p> : null;
}
