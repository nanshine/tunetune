import { useEffect, useRef, useState } from 'react';
import { BookOpen, Box, Check, CheckCircle2, ClipboardCheck, Clock3, Database, Files, FlaskConical, MessageSquare, Pencil, ScrollText, Target, X, XCircle } from 'lucide-react';
import { useWorkspace } from './useWorkspace';
import { array, assessments, collection, document, experiments, object, resolvedFeedback, statusLabel, text } from './model';
import type { FeedbackTarget, JsonObject, Snapshot } from './model';
import { FeedbackForm } from './FeedbackForm';
import type { Draft } from './FeedbackForm';
import { Lineage } from './Lineage';
import { RecordView } from './RecordView';
import { AcceptanceView } from './AcceptanceView';

type Panel = 'goal' | 'resources' | 'evaluation' | 'feedback' | 'review' | 'logs';
const emptyFiles: Snapshot['files'] = {};
const panelTitles: Record<Panel, string> = { goal: '目标与场景', resources: '资源', evaluation: '评测定义', feedback: '协作与反馈', review: '研究复盘', logs: '运行日志' };
const generalFeedback: FeedbackTarget = { kind: 'comment', target: null, title: '留下反馈' };
const resourceLabels: Record<string, string> = { data: '数据', dataset: '数据', model: '模型', environment: '环境', hardware: '硬件', tool: '工具', other: '其他资源' };

function StateIcon({ state }: { state: string }) {
  if (state === 'succeeded') return <CheckCircle2 size={17} />;
  if (state === 'failed') return <XCircle size={17} />;
  return <Clock3 size={17} />;
}

export function App() {
  const { snapshot, connectionError, renameProject } = useWorkspace();
  const files = snapshot?.files ?? emptyFiles;
  const project = document(files, 'project.json');
  const goal = document(files, 'goal.json');
  const items = experiments(files);
  const results = assessments(files);
  const candidates = array(document(files, 'candidates.json').items).map(object);
  const releases = collection(files, /^releases\/[^/]+\.json$/);
  const requests = collection(files, /^feedback\/requests\/[^/]+\.json$/);
  const responses = collection(files, /^feedback\/responses\/[^/]+\.json$/);
  const incoming = collection(files, /^feedback\/incoming\/[^/]+\.json$/);
  const handled = collection(files, /^feedback\/handled\/[^/]+\.json$/);
  const answered = new Set(responses.map(([, response]) => text(response.request_id)));
  const resolved = resolvedFeedback(files);
  const openRequests = requests.filter(([, request]) => !answered.has(text(request.id)) && !resolved.has(text(request.id)));
  const pendingFeedback = [...responses, ...incoming].filter(([, entry]) => !resolved.has(text(entry.id)));
  const [panel, setPanel] = useState<Panel>('goal');
  const [panelOpen, setPanelOpen] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [acceptance, setAcceptance] = useState(false);
  const [acceptanceRelease, setAcceptanceRelease] = useState<string | null>(null);
  const [feedbackTarget, setFeedbackTarget] = useState<FeedbackTarget>(generalFeedback);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [pending, setPending] = useState<Record<string, boolean>>({});
  const [assessmentId, setAssessmentId] = useState('');
  const [evaluationSelection, setEvaluationSelection] = useState('');
  const [logSelection, setLogSelection] = useState('');
  const runningCount = items.filter(item => item.state === 'running').length + results.filter(result => result.state === 'running').length;
  const logExperiment = items.find(item => item.id === logSelection) ?? items.find(item => item.id === selected) ?? items.find(item => item.state === 'running') ?? items[0];
  const logPath = logExperiment ? `experiments/${logExperiment.id}/train.log` : '';
  const drawerHeading = useRef<HTMLHeadingElement>(null);
  const lastTrigger = useRef<HTMLElement | null>(null);
  const currentQuestion = feedbackTarget.request_id && feedbackTarget.target ? document(files, feedbackTarget.target) : null;
  const visibleFeedbackTarget = currentQuestion ? { ...feedbackTarget, title: text(currentQuestion.title, feedbackTarget.title), options: array(currentQuestion.options).filter((option): option is string => typeof option === 'string') } : feedbackTarget;
  const feedbackKey = `${feedbackTarget.kind}:${feedbackTarget.target ?? ''}:${feedbackTarget.sample_id ?? ''}:${feedbackTarget.context ?? ''}`;
  const experiment = items.find(item => item.id === selected);
  const experimentResults = results.filter(result => result.experimentId === selected);
  const activeAssessment = experimentResults.find(result => result.id === assessmentId) ?? experimentResults[0];
  const activeResult = activeAssessment ? document(files, activeAssessment.path.replace('/config.json', '/result.json')) : {};
  const experimentRelease = releases.find(([, release]) => text(release.experiment_id) === selected);
  const error = connectionError || snapshot?.error;
  const ready = !!files['project.json'];
  const version = text(project.current_evaluation);
  const evaluationPath = version ? `evaluation/versions/${version}/definition.json` : 'evaluation/draft/definition.json';
  const evaluationDefinitions = collection(files, /^evaluation\/(draft|versions\/[^/]+)\/definition\.json$/);
  const shownEvaluationPath = evaluationSelection && files[evaluationSelection] ? evaluationSelection : evaluationPath;
  const shownEvaluation = document(files, shownEvaluationPath);
  const acceptances = collection(files, /^acceptance\/[^/]+\/config\.json$/);
  const resources = array(document(files, 'resources.json').items).map(object);
  const resourceGroups = new Map<string, JsonObject[]>();
  for (const resource of resources) {
    const type = text(resource.type, 'other').toLowerCase();
    resourceGroups.set(type, [...(resourceGroups.get(type) ?? []), resource]);
  }
  const projectName = text(project.name, 'TuneTune');

  useEffect(() => { window.document.title = `${projectName} · 研究空间`; }, [projectName]);
  useEffect(() => { if (panelOpen) drawerHeading.current?.focus(); }, [panel, panelOpen]);
  function closePanel() { setPanelOpen(false); lastTrigger.current?.focus(); }
  function openPanel(next: Panel) {
    lastTrigger.current = window.document.activeElement as HTMLElement;
    if (panelOpen && panel === next) closePanel(); else { setPanel(next); setPanelOpen(true); }
  }
  function feedback(target: FeedbackTarget) { setFeedbackTarget(target); setPanel('feedback'); setPanelOpen(true); }
  function change(path: string, title: string) { feedback({ kind: 'change', target: files[path] ? path : null, title }); }
  function selectExperiment(id: string) { setSelected(id); setDetailsOpen(true); setAssessmentId(''); }
  function openAcceptance(path: string | null) { setAcceptanceRelease(path); setAcceptance(true); }

  return <>
    {acceptance && <div className="app-shell acceptance-mode" onKeyDown={event => { if (event.key === 'Escape') setAcceptance(false); }}><AcceptanceView files={files} projectName={projectName} releases={releases} acceptances={acceptances} initialReleasePath={acceptanceRelease} connectionError={connectionError} syncError={snapshot?.error ?? null} connected={!!snapshot} onBack={() => setAcceptance(false)} /></div>}
    <div className="app-shell" hidden={acceptance} onKeyDown={event => { if (event.key === 'Escape') { if (panelOpen) closePanel(); else if (detailsOpen) setDetailsOpen(false); } }}>
    <a className="skip-link" href="#workspace">跳到研究空间</a>
    <header className="topbar">
      <div className="utility-controls workspace-tools"><button onClick={() => { setFeedbackTarget(generalFeedback); openPanel('feedback'); }} aria-label={`协作反馈，${openRequests.length + pendingFeedback.length} 条待处理`} title="协作反馈" aria-expanded={panelOpen && panel === 'feedback'}><MessageSquare size={16} /><span className="tool-label">协作反馈</span></button><button onClick={() => openPanel('review')} aria-label="研究复盘" title="研究复盘" aria-expanded={panelOpen && panel === 'review'}><BookOpen size={16} /><span className="tool-label">研究复盘</span></button></div>
      <ProjectName name={projectName} digest={files['project.json']?.sha256} disabled={!ready || !!error} onSave={renameProject} />
      <div className={`connection glass-chip ${error ? 'warning' : ''}`} role="status" title={error ?? (snapshot ? '本地已连接' : '正在连接')}><span className="connection-dot" /><span className="connection-label">{connectionError ? '连接中断' : snapshot?.error ? '同步待恢复' : snapshot ? '本地已连接' : '正在连接'}</span></div>
    </header>
    {error && <div className="sync-banner" role="alert">{error} · {ready ? '保留最后可用内容，正在自动重试。' : '请检查研究目录与文件格式，正在自动重试。'}</div>}
    <main id="workspace" className="workspace" tabIndex={-1}>
      <section className="canvas-region" aria-label="实验与候选谱系">
        <Lineage items={items} results={results} candidates={candidates} selected={selected} releases={new Set(releases.map(([, release]) => text(release.experiment_id)))} onSelect={selectExperiment} onAccept={id => openAcceptance(releases.find(([, release]) => text(release.experiment_id) === id)?.[0] ?? null)} onCandidateFeedback={() => change('candidates.json', '添加或调整候选方案')} />
        {!items.length && <div className="empty-canvas"><div className="empty-symbol"><FlaskConical size={30} strokeWidth={1.4} /></div><div className="eyebrow">从一个值得回答的问题开始</div><h2>{ready ? '研究空间已就绪' : '等待研究文件'}</h2><p>{ready ? '目标、评测与实验都保存在你的目录中。\n在 Agent 会话中准备评测、开展实验，结果会自动出现在这里。' : '使用 init 技能建立研究目录，\n再通过本地脚本打开研究空间。'}</p><button className="primary" onClick={() => openPanel('goal')}><Target size={16} />查看研究目标</button><div className="empty-steps"><span>明确目标</span><span>构建评测</span><span>开始实验</span></div></div>}
      </section>
      <div className={`left-dock ${panelOpen ? 'open' : ''}`}>
        <aside id="left-panel-content" className="drawer left-drawer" aria-labelledby="drawer-title" aria-hidden={!panelOpen} inert={!panelOpen}>
          <div className="drawer-header"><h2 ref={drawerHeading} id="drawer-title" tabIndex={-1}>{panelTitles[panel]}</h2><button className="icon-button" aria-label={`关闭${panelTitles[panel]}`} onClick={closePanel}><X size={19} /></button></div>
          <div className="drawer-content">
            {panel === 'goal' && <><section className="panel-section"><h3>使用情境</h3><div className="reading-block"><RecordView value={goal.context} /></div></section><section className="panel-section"><h3>期望产物</h3><div className="reading-block"><RecordView value={goal.expected_result} /></div></section><section className="panel-section"><h3>理想场景 <span className="count">{array(goal.examples).length}</span></h3><div className="example-list">{array(goal.examples).map(object).map((example, index) => <details className="example-item" key={text(example.id, String(index))} open={index === 0}><summary>{text(example.id, `场景 ${index + 1}`)}</summary><RecordView value={example} /></details>)}</div>{!array(goal.examples).length && <p className="muted">尚无具体例子，可通过修改意见补充。</p>}</section>{!!array(goal.sources).length && <details><summary>来源与修订</summary><RecordView value={goal.sources} /></details>}</>}
            {panel === 'resources' && <>{[...resourceGroups.entries()].map(([type, entries]) => <section className="resource-group" key={type}><h3>{resourceLabels[type] ?? type} <span className="count">{entries.length}</span></h3>{entries.map((resource, index) => <details className="resource-item" key={text(resource.id, String(index))}><summary><span className="resource-name"><Database size={16} /><span>{text(resource.title, '未命名资源')}<small>{text(resource.version)}</small></span></span><span className="resource-status">{text(resource.status, '未记录状态')}</span></summary><RecordView value={resource} /><button onClick={() => change('resources.json', `请求检查 · ${text(resource.title, text(resource.id))}`)}>请求检查</button></details>)}</section>)}{!resources.length && <Empty title="尚无资源记录" detail="由 Agent 调查并记录数据、模型、环境和硬件；也可以先提交资源请求。" />}<section className="hardware-observation"><h3>硬件观测</h3>{files['resources/status.json'] ? <><p className="muted">观测不代表训练进程状态，请核对采集时间。</p><RecordView value={files['resources/status.json'].content} /></> : <div className="notice">尚无实时采集。资源清单中的最近检查不代表硬件当前在线。</div>}</section></>}
            {panel === 'evaluation' && <><div className="evaluation-toolbar"><span className="section-label">{version ? `当前评测 ${version}` : '尚未发布 · 草稿'}</span><select aria-label="查看评测版本或草稿" value={shownEvaluationPath} onChange={event => setEvaluationSelection(event.target.value)}>{evaluationDefinitions.map(([path, definition]) => <option key={path} value={path}>{text(definition.version, path.includes('/draft/') ? '草稿' : path.split('/')[2])}{path === evaluationPath ? ' · 当前' : ''}</option>)}</select></div><div className="reading-block"><RecordView value={shownEvaluation.description} /></div><section className="panel-section"><h3>评分规则</h3>{array(shownEvaluation.metrics).map(object).map((metric, index) => <div className="metric-definition" key={text(metric.id, String(index))}><strong>{text(metric.label, text(metric.id, '未命名指标'))}</strong><span>{text(metric.direction) === 'maximize' ? '越高越好' : text(metric.direction) === 'minimize' ? '越低越好' : text(metric.direction)}</span></div>)}{!array(shownEvaluation.metrics).length && <p className="muted">尚未定义指标。</p>}<RecordView value={shownEvaluation.rubric} /></section><section className="panel-section"><h3>评测数据 <span className="count">{array(shownEvaluation.datasets).length}</span></h3>{array(shownEvaluation.datasets).map(object).map((dataset, index) => <details className="resource-item" key={text(dataset.id, String(index))}><summary>{text(dataset.id, `数据集 ${index + 1}`)}</summary><RecordView value={dataset} /></details>)}</section>{!!openRequests.length && <section className="panel-section"><h3>人工标注 <span className="count">{openRequests.length}</span></h3>{openRequests.map(([path, request]) => <article className="annotation-request" key={path}><strong>{text(request.title, '待回答问题')}</strong><p className="muted">{text(request.prompt)}</p><button onClick={() => feedback({ kind: 'response', target: path, request_id: text(request.id), title: text(request.title, '回答问题'), options: array(request.options).filter((option): option is string => typeof option === 'string') })}>回答问题</button></article>)}</section>}<details><summary>完整定义与执行条件</summary><RecordView value={files[shownEvaluationPath]?.content} /></details><p className="panel-footnote">标注与修改保存后仍待 Agent 整理，不自动更新已发布评测。</p></>}
            {panel === 'logs' && <><p className="muted">训练日志来自实验目录，每 2 秒自动同步，展示末尾最多 64 KiB。评测结果与逐例输出请在实验详情中查看。</p>{logExperiment ? <><label htmlFor="log-experiment">选择实验</label><select id="log-experiment" value={logExperiment.id} onChange={event => setLogSelection(event.target.value)}>{items.map(item => <option key={item.id} value={item.id}>{item.title} · {statusLabel(item.state)}</option>)}</select><p className="file-path">{logPath}</p><pre className="log-view workspace-log" tabIndex={0} aria-label={`${logExperiment.title}的训练日志`}>{text(files[logPath]?.content) || '尚无日志输出。任务写入训练日志后会自动显示。'}</pre><button onClick={() => { selectExperiment(logExperiment.id); setPanelOpen(false); }}>查看实验详情</button></> : <Empty title="尚无运行日志" detail="创建实验并写入训练日志后，可在这里按实验查看。" />}</>}
            {panel === 'review' && <><p className="muted">Agent 的最近一次综合分析；建议不等于下一轮已经开始。</p><pre className="markdown-text">{text(files['review.md']?.content, '尚无综合分析。在会话中使用 review 技能开始复盘。')}</pre></>}
            {panel === 'feedback' && <><FeedbackForm key={feedbackKey} target={visibleFeedbackTarget} files={files} draft={drafts[feedbackKey]} busy={pending[feedbackKey] ?? false} onBusyChange={busy => setPending(previous => ({ ...previous, [feedbackKey]: busy }))} onChange={draft => setDrafts(previous => ({ ...previous, [feedbackKey]: draft }))} onSaved={id => setDrafts(previous => { if (previous[feedbackKey]?.id !== id) return previous; const next = { ...previous }; delete next[feedbackKey]; return next; })} />
              {feedbackTarget.target && <button className="text-button" onClick={() => setFeedbackTarget(generalFeedback)}>改为一般反馈</button>}
              <h3>需要你的回答 <span className="count">{openRequests.length}</span></h3>{openRequests.map(([path, request]) => <article className="panel-card" key={path}><h3>{text(request.title, '待回答问题')}</h3><p className="record-text">{text(request.prompt)}</p><button onClick={() => setFeedbackTarget({ kind: 'response', target: path, request_id: text(request.id), title: text(request.title, '回答问题'), options: array(request.options).filter((option): option is string => typeof option === 'string') })}>回答问题</button></article>)}
              <h3>已保存，待处理 <span className="count">{pendingFeedback.length}</span></h3>{pendingFeedback.map(([path, entry]) => <article className="panel-card" key={path}><p className="record-text">{text(entry.text)}</p><span className="muted">{text(entry.created_at)}</span></article>)}
              {!!handled.length && <><h3>Agent 处理记录</h3>{handled.map(([path, entry]) => <details key={path}><summary>{text(entry.feedback_id)} · {text(entry.disposition)}</summary><RecordView value={entry} /></details>)}</>}
            </>}
          </div>
        </aside>
        <nav className="panel-tabs" aria-label="研究资料">
          <button className={panelOpen && panel === 'goal' ? 'active' : ''} onClick={() => openPanel('goal')} aria-expanded={panelOpen && panel === 'goal'} aria-controls="left-panel-content"><Target size={20} /><span>目标</span></button>
          <button className={panelOpen && panel === 'resources' ? 'active' : ''} onClick={() => openPanel('resources')} aria-expanded={panelOpen && panel === 'resources'} aria-controls="left-panel-content"><Files size={20} /><span>资源</span></button>
          <button className={panelOpen && panel === 'evaluation' ? 'active' : ''} onClick={() => openPanel('evaluation')} aria-expanded={panelOpen && panel === 'evaluation'} aria-controls="left-panel-content" aria-label="评测 Evaluation" title="Evaluation"><ClipboardCheck size={20} /><span>评测</span></button>
        </nav>
      </div>
      {detailsOpen && experiment && <aside className={`drawer right-drawer ${panelOpen ? 'with-left-panel' : ''}`} aria-label="实验详情"><div className="drawer-header"><div className="experiment-title"><span className="node-icon"><Box size={19} /></span><div><span className="eyebrow">{experiment.id}</span><h2>{experiment.title}</h2></div></div><button className="icon-button" aria-label="关闭实验详情" onClick={() => setDetailsOpen(false)}><X size={19} /></button></div><div className="drawer-content">
        <section className="detail-section"><h3>训练状态</h3><div className={`detail-status status ${experiment.state}`}><StateIcon state={experiment.state} />{statusLabel(experiment.state)}</div><p className="muted">记录时间：{experiment.updatedAt || '未知'}。执行状态不代表进程当前存活。</p></section>
        <section className="detail-section"><h3>评测记录</h3>{activeAssessment ? <><label>选择评测<select value={activeAssessment.id} onChange={event => setAssessmentId(event.target.value)}>{experimentResults.map(result => <option key={result.id} value={result.id}>{result.version} · {result.id} · {statusLabel(result.state)}</option>)}</select></label><div className={`detail-status status ${activeAssessment.state}`}><StateIcon state={activeAssessment.state} />评测 {activeAssessment.version} · {statusLabel(activeAssessment.state)}</div><div className="detail-metrics">{Object.entries(activeAssessment.metrics).map(([key, value]) => <div key={key}><span>{Object.hasOwn(activeAssessment.metricLabels, key) ? activeAssessment.metricLabels[key] : key}</span><strong>{value.toLocaleString()}</strong></div>)}</div>{text(activeResult.error) && <p className="error-text">{text(activeResult.error)}</p>}<details><summary>逐例输出</summary><RecordView value={files[activeAssessment.path.replace('/config.json', '/outputs.jsonl')]?.content} /></details></> : <p className="muted">尚无评测记录。训练成功不等于评测通过。</p>}</section>
        <section className="detail-section"><h3>结果分析</h3><pre className="markdown-text">{text(files[`experiments/${experiment.id}/analysis.md`]?.content, '尚无分析')}</pre></section>
        <section className="detail-section"><h3>产物</h3><RecordView value={files[`experiments/${experiment.id}/artifacts.json`]?.content} /></section>
        {experimentRelease && <div className="detail-actions"><button className="primary" onClick={() => openAcceptance(experimentRelease[0])}><ClipboardCheck size={16} />验收此版本</button><button onClick={() => openAcceptance(experimentRelease[0])}>比较结果</button></div>}
        <details><summary>固定输入</summary><RecordView value={files[experiment.configPath]?.content} /></details><details><summary>训练日志（局部预览）</summary><pre className="log-view">{text(files[`experiments/${experiment.id}/train.log`]?.content, '尚无日志')}</pre></details><button onClick={() => change(experiment.configPath, `实验反馈 · ${experiment.id}`)}>反馈这个实验</button>
      </div></aside>}
    </main>
    <footer className="statusbar"><div className="utility-controls"><span className="running-tasks" role="status" title="按训练与评测的最新状态记录统计，不代表进程当前存活。">运行任务 <span className="count">{ready ? runningCount : '—'}</span></span><span className="footer-divider" /><button onClick={() => openPanel('logs')} aria-expanded={panelOpen && panel === 'logs'} aria-controls="left-panel-content"><ScrollText size={16} />日志</button></div></footer>
    </div>
  </>;
}

function ProjectName({ name, digest, disabled, onSave }: { name: string; digest?: string; disabled: boolean; onSave: (name: string, digest: string) => Promise<void> }) {
  const [draft, setDraft] = useState<{ name: string; digest: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const input = useRef<HTMLInputElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const editing = draft !== null;
  useEffect(() => { if (editing) { input.current?.focus(); input.current?.select(); } }, [editing]);
  function close() { setDraft(null); setError(''); requestAnimationFrame(() => trigger.current?.focus()); }
  async function save() {
    if (!draft || saving) return;
    const next = draft.name.trim();
    if (!next || [...next].length > 120 || /[\u0000-\u001f\u007f-\u009f]/.test(next)) { setError('请输入 1–120 个字符的项目名称，不含控制字符。'); return; }
    setSaving(true);
    setError('');
    try { await onSave(next, draft.digest); close(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '名称保存失败，请重试。'); }
    finally { setSaving(false); }
  }
  return <div className={`project-island ${editing ? 'editing' : ''}`}>
    {draft ? <form className="project-name-form" onSubmit={event => { event.preventDefault(); void save(); }} onKeyDown={event => { if (event.key === 'Escape') { event.stopPropagation(); if (!saving) close(); } if (event.key === 'Enter' && event.nativeEvent.isComposing) event.preventDefault(); }} aria-busy={saving}>
      <label className="sr-only" htmlFor="project-name">项目名称</label><input ref={input} id="project-name" value={draft.name} disabled={saving} autoComplete="off" aria-invalid={!!error} aria-describedby="project-name-help" onChange={event => { setDraft({ ...draft, name: event.target.value }); setError(''); }} />
      <button className="icon-button" type="submit" aria-label="保存项目名称" title="保存名称（Enter）" disabled={saving}><Check size={17} /></button><button className="icon-button" type="button" aria-label="取消修改名称" title="取消（Esc）" disabled={saving} onClick={close}><X size={17} /></button>
      <div id="project-name-help" className={`project-name-help ${error ? 'has-error' : ''}`} role="status">{error || (saving ? '正在保存…' : 'Enter 保存 · Esc 取消')}</div>
    </form> : <button ref={trigger} className="project-name-trigger" disabled={disabled} aria-label={`编辑项目名称：${name}`} title={`${name} · 点击编辑名称`} onClick={() => { if (digest) setDraft({ name, digest }); }}><span>{name}</span><Pencil size={13} /></button>}
  </div>;
}

function Empty({ title, detail }: { title: string; detail: string }) { return <div className="empty-section"><h3>{title}</h3><p className="muted">{detail}</p></div>; }
