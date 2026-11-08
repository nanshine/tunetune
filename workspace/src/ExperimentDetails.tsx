import { useState } from 'react';
import { experimentNumber, preferredEvaluation, recentEvaluations, roleLabels, statusLabel } from './model';
import type { EvaluationRun, Experiment, Snapshot } from './model';
import { OutcomeBadge, StateDot } from './Lineage';
import { UsageView } from './UsageView';
import { SamplesView } from './EvaluationView';
import { rowSource, usePaged } from './rows';
import { Section } from './Parts';
import { labels, t } from './i18n';

const parameterLabels: Record<string, string> = labels({ learning_rate: '学习率', batch_size: '批量大小', epochs: '训练轮数', num_train_epochs: '训练轮数', rank: '适配秩', alpha: 'Alpha', dropout: '丢弃率', max_length: '最大长度', seed: '随机种子', temperature: '生成温度', max_output_tokens: '最多输出 token', context: '上下文长度', text_character_limit: '正文截断字数' });
type Tab = 'overview' | 'evaluation' | 'usage';

function format(value: number): string { return value.toLocaleString(undefined, { maximumFractionDigits: 3 }); }

export function ExperimentDetails({ experiment, experimentsById, results, files, currentVersion, delivered, onOpenAcceptance }: {
  experiment: Experiment; experimentsById: Map<string, Experiment>; results: EvaluationRun[]; files: Snapshot['files']; currentVersion: string; delivered: boolean; onOpenAcceptance: () => void;
}) {
  const [tab, setTab] = useState<Tab>('overview');
  const [selection, setSelection] = useState('');
  const experimentResults = recentEvaluations(results.filter(result => result.experimentId === experiment.id));
  const versions = [...new Set(experimentResults.map(result => result.version))];
  const version = versions.includes(selection) ? selection : versions.includes(currentVersion) ? currentVersion : versions[0] ?? '';
  const active = preferredEvaluation(experimentResults, version);
  const final = preferredEvaluation(experimentResults, version, 'final');
  const paged = usePaged();
  const outputs = active ? rowSource(files, paged, active.path.replace('/config.json', '/outputs.jsonl')) : null;
  const parent = experiment.parent ? experimentsById.get(experiment.parent) : undefined;
  const parentResult = parent ? preferredEvaluation(results.filter(result => result.experimentId === parent.id), version) : undefined;
  const headline = active?.state === 'succeeded' ? Object.entries(active.metrics)[0] : undefined;
  const parentValue = headline && parentResult?.state === 'succeeded' && parentResult.evaluationHash === active!.evaluationHash ? parentResult.metrics[headline[0]] : undefined;
  const parameters = Object.entries(experiment.parameters).filter(([key, value]) => !/(?:^|_)(?:id|path|sha256|hash|command|execution|inputs|environment)(?:_|$)/.test(key) && (typeof value === 'number' && Number.isFinite(value) || typeof value === 'boolean' || typeof value === 'string' && value.length <= 120)).slice(0, 8);
  return <div className="details">
    <div className="details-head">
      <div className="details-ids"><span className="node-number">{experimentNumber(experiment.id)}</span>{experiment.role && <span className={`badge role-${experiment.role}`}>{roleLabels[experiment.role] || experiment.role}</span>}{experiment.targetKind === 'api' && <span className="badge">{t('在线 API')}</span>}{delivered && <span className="badge tone-good">{t('交付模型')}</span>}</div>
      <h3 className="details-title">{experiment.title}</h3>
      <div className="verdict"><OutcomeBadge analysis={experiment.analysis} /><p>{experiment.analysis.summary || t('还没有结论。跑通不等于效果已经验证。')}</p></div>
      {headline && <div className="headline-metric">
        <span>{Object.hasOwn(active!.metricLabels, headline[0]) ? active!.metricLabels[headline[0]] : headline[0]}</span>
        <strong>{format(headline[1])}</strong>
        {parentValue !== undefined && <span className={`delta ${headline[1] >= parentValue ? 'up' : 'down'}`}>{headline[1] >= parentValue ? '+' : ''}{format(headline[1] - parentValue)} {t('对比')} {experimentNumber(parent!.id)}</span>}
      </div>}
    </div>
    <div className="tabbar" role="tablist" aria-label={t('实验内容')}>{(['overview', 'evaluation', 'usage'] as Tab[]).map(item => <button key={item} role="tab" aria-selected={tab === item} className={tab === item ? 'active' : ''} onClick={() => setTab(item)}>{{ overview: t('做了什么'), evaluation: t('评测'), usage: t('怎么用') }[item]}</button>)}</div>
    {tab === 'overview' && <>
      <Section title={t('想验证什么')}><p className="prose">{experiment.hypothesis || t('没有记录假设。')}</p></Section>
      <Section title={t('方法')}><dl className="facts">
        {(experiment.modelName || experiment.method) && <div><dt>{t('做法')}</dt><dd>{[experiment.modelName, experiment.method, experiment.framework].filter(Boolean).join('，')}</dd></div>}
        {parent && <div><dt>{t('基于')}</dt><dd>{experimentNumber(parent.id)} · {parent.title}</dd></div>}
        {parameters.map(([key, value]) => <div key={key}><dt>{Object.hasOwn(parameterLabels, key) ? parameterLabels[key] : key.replaceAll('_', ' ')}</dt><dd>{typeof value === 'boolean' ? value ? t('是') : t('否') : String(value)}</dd></div>)}
      </dl>{experiment.targetKind === 'api' && <p className="muted">{t('在线服务的模型可能更新，这里固定的是调用方式，不能保证远端模型完全复现。')}</p>}</Section>
      <Section title={t('运行')}><p className="status-line"><StateDot state={experiment.state} />{statusLabel(experiment.state)}</p><UsageView usage={experiment.usage} />{experiment.state === 'running' && <p className="muted">{t('文件里记录为运行中，不代表进程现在还在跑。')}</p>}</Section>
    </>}
    {tab === 'evaluation' && (active ? <>
      <div className="inline-controls">{versions.length > 1 && <label className="version-select">{t('评测版本')}<select value={version} onChange={event => setSelection(event.target.value)}>{versions.map(item => <option key={item} value={item}>{item || t('未指定')}{item === currentVersion ? t('（当前）') : ''}</option>)}</select></label>}<span className="status-line"><StateDot state={active.state} />{t('开发集 ·')} {statusLabel(active.state)}</span></div>
      {active.version !== currentVersion && <p className="notice">{t('这是其他评测版本的结果，不和当前版本的分数放在一起比较。')}</p>}
      <div className="metric-grid">{Object.entries(active.metrics).map(([key, value]) => <div key={key}><span>{Object.hasOwn(active.metricLabels, key) ? active.metricLabels[key] : key}</span><strong>{format(value)}</strong></div>)}</div>
      {!Object.keys(active.metrics).length && <p className="muted">{t('这次评测还没有指标。')}</p>}
      {final && <Section title={t('最终检查')}><p className="status-line"><StateDot state={final.state} />{statusLabel(final.state)}</p>
        {final.state === 'succeeded' && <div className="metric-grid">{Object.entries(final.metrics).map(([key, value]) => <div key={key}><span>{Object.hasOwn(final.metricLabels, key) ? final.metricLabels[key] : key}</span><strong>{format(value)}</strong></div>)}</div>}
        <p className="muted">{t('最终检查用的是研究中没有看过的样例，只记录汇总分数，不显示逐条结果。')}</p></Section>}
      <UsageView usage={active.usage} />
      <SamplesView key={active.path} source={outputs} outputs metricLabels={active.metricLabels} />
    </> : <p className="muted">{t('还没有评测。跑通不等于效果已经验证。')}</p>)}
    {tab === 'usage' && <>
      {experiment.invoke.length ? <>
        <p className="prose">{t('在研究目录里运行下面的命令，末尾加上输入和输出文件。输入每行是')} <code>{'{"sample_id", "input"}'}</code>{t('，输出每行是')} <code>{'{"sample_id", "output"}'}</code>{t('。评测和验收用的也是这个入口。')}</p>
        <pre className="command"><code>{[...experiment.invoke, t('输入.jsonl'), t('输出.jsonl')].map(part => /[\s"'$]/.test(part) ? JSON.stringify(part) : part).join(' ')}</code></pre>
      </> : <p className="muted">{t('这个实验没有可直接调用的模型入口。')}</p>}
      {experiment.state === 'succeeded' && experiment.targetKind && <button onClick={onOpenAcceptance}>{t('在验收里看它的输出')}</button>}
    </>}
  </div>;
}
