import type { Usage } from './model';
import { t } from './i18n';

export function UsageView({ usage }: { usage: Usage }) {
  const values: string[] = [];
  if (typeof usage.requests === 'number') values.push(t('{count} 次请求', { count: usage.requests.toLocaleString() }));
  if (typeof usage.input_tokens === 'number' || typeof usage.output_tokens === 'number') values.push(t('输入 / 输出 {input} / {output} tokens', { input: usage.input_tokens?.toLocaleString() ?? t('未知'), output: usage.output_tokens?.toLocaleString() ?? t('未知') }));
  if (typeof usage.cost === 'number') values.push(t('费用 {cost} {currency}', { cost: usage.cost.toLocaleString(), currency: usage.currency || t('币种未记录') }));
  if (typeof usage.latency_seconds === 'number') values.push(t('耗时 {seconds} 秒', { seconds: usage.latency_seconds.toLocaleString() }));
  return values.length ? <p className="usage-facts">{values.join(' · ')}</p> : null;
}
