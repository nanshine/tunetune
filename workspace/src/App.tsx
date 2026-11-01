import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, BookOpen, Box, CheckCheck, ChevronRight, ClipboardCheck, Database, FlaskConical, GitBranch, MessageSquare, PanelLeftClose, SlidersHorizontal, Target, X } from 'lucide-react';
import { useWorkspace } from './useWorkspace';
import { array, assessments, collection, document, experiments, object, statusLabel, text } from './model';
import type { FeedbackTarget, Snapshot } from './model';
import { FeedbackForm } from './FeedbackForm';
import type { Draft } from './FeedbackForm';
import { Lineage } from './Lineage';
import { RecordView } from './RecordView';

type Drawer = 'goal' | 'resources' | 'evaluation' | 'candidates' | 'feedback' | 'review' | null;
const emptyFiles: Snapshot['files'] = {};
const drawerTitles = { goal: '研究目标', resources: '资源与准备', evaluation: '评测定义', candidates: '候选方案', feedback: '协作与反馈', review: '研究复盘' };
const generalFeedback: FeedbackTarget = { kind: 'comment', target: null, title: '留下反馈' };

export function App() {
  const { snapshot, connectionError } = useWorkspace();
  const files = snapshot?.files ?? emptyFiles;
  const project = document(files, 'project.json');
  const settings = document(files, 'workspace.json');
  const items = experiments(files);
  const results = assessments(files);
  const candidates = array(document(files, 'candidates.json').items).map(object);
  const releases = collection(files, /^releases\/[^/]+\.json$/);
  const requests = collection(files, /^feedback\/requests\/[^/]+\.json$/);
  const responses = collection(files, /^feedback\/responses\/[^/]+\.json$/);
  const incoming = collection(files, /^feedback\/incoming\/[^/]+\.json$/);
  const handled = collection(files, /^feedback\/handled\/[^/]+\.json$/);
  const answered = new Set(responses.map(([, response]) => text(response.request_id)));
  const resolved = new Set(handled.map(([, entry]) => text(entry.feedback_id)));
  const openRequests = requests.filter(([, request]) => !answered.has(text(request.id)) && !resolved.has(text(request.id)));
  const pendingFeedback = [...responses, ...incoming].filter(([, entry]) => !resolved.has(text(entry.id)));
  const [drawer, setDrawer] = useState<Drawer>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [acceptance, setAcceptance] = useState(false);
  const [feedbackTarget, setFeedbackTarget] = useState<FeedbackTarget>(generalFeedback);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [pending, setPending] = useState<Record<string, boolean>>({});
  const currentQuestion = feedbackTarget.request_id && feedbackTarget.target ? document(files, feedbackTarget.target) : null;
  const visibleFeedbackTarget = currentQuestion ? { ...feedbackTarget, title: text(currentQuestion.title, feedbackTarget.title), options: array(currentQuestion.options).filter((option): option is string => typeof option === 'string') } : feedbackTarget;
  const [assessmentId, setAssessmentId] = useState('');
  const drawerHeading = useRef<HTMLHeadingElement>(null);
  const lastTrigger = useRef<HTMLElement | null>(null);
  const feedbackKey = `${feedbackTarget.kind}:${feedbackTarget.target ?? ''}:${feedbackTarget.sample_id ?? ''}`;
  const experiment = items.find(item => item.id === selected);
  const experimentResults = results.filter(result => result.experimentId === selected);
  const activeAssessment = experimentResults.find(result => result.id === assessmentId) ?? experimentResults[0];
  const error = connectionError || snapshot?.error;
  const ready = !!files['project.json'];
  const version = text(project.current_evaluation);
  const evaluationPath = version ? `evaluation/versions/${version}/definition.json` : 'evaluation/draft/definition.json';
  const currentEvaluation = document(files, evaluationPath);
  const acceptances = collection(files, /^acceptance\/[^/]+\/config\.json$/);

  useEffect(() => { window.document.title = `${text(project.name, 'TuneTune')} · 研究空间`; }, [project.name]);
  useEffect(() => { if (drawer) drawerHeading.current?.focus(); }, [drawer]);
  function closeDrawer() { setDrawer(null); lastTrigger.current?.focus(); }
  function openDrawer(next: Drawer) {
    lastTrigger.current = window.document.activeElement as HTMLElement;
    if (drawer === next) closeDrawer(); else setDrawer(next);
  }
  function feedback(target: FeedbackTarget) { setFeedbackTarget(target); setDrawer('feedback'); }
  function change(path: string, title: string) { feedback({ kind: 'change', target: files[path] ? path : null, title }); }

  return <div className="app-shell" onKeyDown={event => { if (event.key === 'Escape') { if (drawer) closeDrawer(); else setSelected(null); } }}>
    <a className="skip-link" href="#workspace">跳到研究空间</a>
    <header className="topbar">
      <div className="brand-mark" aria-label="TuneTune"><SlidersHorizontal size={23} /></div>
      <button className={`project-button ${drawer === 'goal' ? 'active' : ''}`} onClick={() => openDrawer('goal')} aria-expanded={drawer === 'goal'}><span>{text(project.name, 'TuneTune')}</span><ChevronRight size={15} /></button>
      <span className="topbar-divider" />
      <nav aria-label="研究资料">
        <button className={drawer === 'resources' ? 'active' : ''} onClick={() => openDrawer('resources')} aria-expanded={drawer === 'resources'}><Database size={17} /><span>资源</span></button>
        <button className={drawer === 'evaluation' ? 'active' : ''} onClick={() => openDrawer('evaluation')} aria-expanded={drawer === 'evaluation'}><GitBranch size={17} /><span>评测定义</span></button>
        <button className={drawer === 'candidates' ? 'active' : ''} onClick={() => openDrawer('candidates')} aria-expanded={drawer === 'candidates'}><Box size={17} /><span>候选</span><span className="count">{candidates.length}</span></button>
      </nav>
      <span className="workspace-title">{text(settings.title, '研究空间')}</span>
      <div className={`connection ${error ? 'warning' : ''}`} role="status"><span className="connection-dot" />{connectionError ? '连接中断' : snapshot?.error ? '同步待恢复' : snapshot ? '文件已连接' : '正在连接'}</div>
    </header>
    {error && <div className="sync-banner" role="alert">{error} · {ready ? '保留最后可用内容，正在自动重试。' : '请检查研究目录与文件格式，正在自动重试。'}</div>}
    <main id="workspace" className="workspace" tabIndex={-1}>
      <section className="canvas-region" aria-label="实验谱系" aria-hidden={acceptance} inert={acceptance} style={{ visibility: acceptance ? 'hidden' : 'visible' }}>
        <Lineage items={items} results={results} selected={selected} releases={new Set(releases.map(([, release]) => text(release.experiment_id)))} onSelect={id => { setSelected(id); setDrawer(null); }} />
        <div className="workspace-heading"><div className="eyebrow">RESEARCH WORKSPACE</div><h1>实验谱系</h1><p>{items.length} 次实验 <span>·</span> {version ? `当前评测 ${version}` : '评测尚未发布'}</p></div>
        <div className="workspace-actions"><button onClick={() => { setAcceptance(true); setDrawer(null); }}><ClipboardCheck size={16} />发布与验收<span className="count">{releases.length}</span></button></div>
        {!items.length && <div className="empty-canvas"><div className="empty-symbol"><FlaskConical size={30} strokeWidth={1.4} /></div><div className="eyebrow">从一个值得回答的问题开始</div><h2>{ready ? '研究空间已就绪' : '等待研究文件'}</h2><p>{ready ? '目标、评测与实验都保存在你的目录中。\n在 Agent 会话中准备评测、开展实验，结果会自动出现在这里。' : '使用 init 技能建立研究目录，\n再通过本地脚本打开研究空间。'}</p><button className="primary" onClick={() => openDrawer('goal')}><Target size={16} />查看研究目标</button><div className="empty-steps"><span>明确目标</span><ChevronRight size={13} /><span>构建评测</span><ChevronRight size={13} /><span>开始实验</span></div></div>}
      </section>
      {acceptance && <section className="acceptance-view" aria-label="发布与验收"><button className="text-button" onClick={() => setAcceptance(false)}><ArrowLeft size={16} />返回实验谱系</button><div className="eyebrow">RELEASES & ACCEPTANCE</div><h1>发布与验收</h1><p className="muted">比较相同输入下的输出。单例偏好与整体验收分别保存，不自动发布或接受成果。</p>
        <div className="release-grid">{releases.map(([path, release]) => <article className="panel-card" key={path}><h3>{text(release.id, path)}</h3><RecordView value={release} /><button onClick={() => feedback({ kind: 'acceptance', target: path, title: `整体验收意见 · ${text(release.id)}` })}>填写整体验收意见</button></article>)}</div>
        {!releases.length && <Empty title="尚无发布成果" detail="在会话中明确选择发布后，由 Agent 保存发布记录。" />}
        {acceptances.map(([path, config]) => {
          const outputPath = path.replace('/config.json', '/outputs.jsonl');
          const rows = array(files[outputPath]?.content).map(object);
          return <section className="comparison-set" key={path}><h2>对照样例 · {text(config.version, text(config.id))}</h2>{!rows.length && <p className="muted">对照输出尚未准备。</p>}{rows.map((row, index) => <article className="comparison-row" key={text(row.sample_id, String(index))}><div className="sample-input"><span className="eyebrow">{text(row.sample_id, `样例 ${index + 1}`)}</span><RecordView value={row.input} /></div><div className="output-grid">{Object.entries(object(row.outputs)).map(([id, output]) => <div key={id}><h3>{id}</h3><RecordView value={output} /></div>)}</div><button onClick={() => feedback({ kind: 'preference', target: outputPath, sample_id: text(row.sample_id, String(index)), title: `逐例偏好 · ${text(row.sample_id, String(index))}` })}>记录本例偏好</button></article>)}</section>;
        })}
      </section>}
      {drawer && <aside className="drawer left-drawer" aria-labelledby="drawer-title"><div className="drawer-header"><div><span className="eyebrow">WORKSPACE / {drawer.toUpperCase()}</span><h2 ref={drawerHeading} id="drawer-title" tabIndex={-1}>{drawerTitles[drawer]}</h2></div><button className="icon-button" aria-label="关闭抽屉" onClick={closeDrawer}><PanelLeftClose size={20} /></button></div><div className="drawer-content">
        {drawer === 'goal' && <><p className="muted">从真实使用情境出发，让每次实验有据可循。</p><RecordView value={files['goal.json']?.content} /><button className="primary" onClick={() => change('goal.json', '建议修改研究目标')}>提出修改意见</button></>}
        {drawer === 'resources' && <><div className="notice">硬件实时状态未知。下方清单是最后检查记录，不代表资源当前在线。</div><RecordView value={document(files, 'resources.json').items} />{files['resources/status.json'] && <section><h3>最近采集记录</h3><RecordView value={files['resources/status.json'].content} /></section>}<button onClick={() => change('resources.json', '资源补充或准备建议')}>提出资源建议</button></>}
        {drawer === 'evaluation' && <><div className="section-label">{version ? `当前评测版本 · ${version}` : '尚未发布 · 草稿'}</div><RecordView value={files[evaluationPath]?.content} /><button onClick={() => change(evaluationPath, '评测修改建议')}>提出评测建议</button><h3>版本与草稿</h3>{collection(files, /^evaluation\/(draft|versions\/[^/]+)\/definition\.json$/).map(([path, definition]) => <details key={path}><summary>{text(definition.version, path.includes('/draft/') ? '草稿' : path.split('/')[2])}</summary><RecordView value={definition} /></details>)}{array(currentEvaluation.metrics).length === 0 && <p className="muted">由 build-evaluation 技能准备可执行评测包，再发布固定版本。</p>}</>}
        {drawer === 'candidates' && <><p className="muted">候选是待讨论的方向，不是已排入执行的任务。</p>{candidates.length ? candidates.map((candidate, index) => <article className="panel-card" key={text(candidate.id, String(index))}><h3>{text(candidate.title, '待命名方案')}</h3><RecordView value={candidate} /></article>) : <Empty title="还没有候选方案" detail="让 review 分析已有证据，或直接向 Agent 提出想尝试的方向。" />}<button onClick={() => change('candidates.json', '添加或调整候选方案')}>提出候选建议</button></>}
        {drawer === 'review' && <><p className="muted">Agent 的最近一次综合分析；建议不等于下一轮已经开始。</p><pre className="markdown-text">{text(files['review.md']?.content, '尚无综合分析。在会话中使用 review 技能开始复盘。')}</pre></>}
        {drawer === 'feedback' && <><FeedbackForm key={feedbackKey} target={visibleFeedbackTarget} files={files} draft={drafts[feedbackKey]} busy={pending[feedbackKey] ?? false} onBusyChange={busy => setPending(previous => ({ ...previous, [feedbackKey]: busy }))} onChange={draft => setDrafts(previous => ({ ...previous, [feedbackKey]: draft }))} onSaved={id => setDrafts(previous => { if (previous[feedbackKey]?.id !== id) return previous; const next = { ...previous }; delete next[feedbackKey]; return next; })} />
          {feedbackTarget.target && <button className="text-button" onClick={() => setFeedbackTarget(generalFeedback)}>改为一般反馈</button>}
          <h3>需要你的回答 <span className="count">{openRequests.length}</span></h3>{openRequests.map(([path, request]) => <article className="panel-card" key={path}><h3>{text(request.title, '待回答问题')}</h3><p className="record-text">{text(request.prompt)}</p><button onClick={() => setFeedbackTarget({ kind: 'response', target: path, request_id: text(request.id), title: text(request.title, '回答问题'), options: array(request.options).filter((option): option is string => typeof option === 'string') })}>回答问题</button></article>)}
          <h3>已保存，待处理 <span className="count">{pendingFeedback.length}</span></h3>{pendingFeedback.map(([path, entry]) => <article className="panel-card" key={path}><p className="record-text">{text(entry.text)}</p><span className="muted">{text(entry.created_at)}</span></article>)}
          {!!handled.length && <><h3>Agent 处理记录</h3>{handled.map(([path, entry]) => <details key={path}><summary>{text(entry.feedback_id)} · {text(entry.disposition)}</summary><RecordView value={entry} /></details>)}</>}
        </>}
      </div></aside>}
      {!drawer && experiment && !acceptance && <aside className="drawer right-drawer" aria-label="实验详情"><div className="drawer-header"><div><span className="eyebrow">EXPERIMENT / {experiment.id}</span><h2>{experiment.title}</h2></div><button className="icon-button" aria-label="关闭实验详情" onClick={() => setSelected(null)}><X size={20} /></button></div><div className="drawer-content"><div className="section-label">训练 · {statusLabel(experiment.state)}</div><p className="muted">记录时间：{experiment.updatedAt || '未知'}。执行状态不代表进程当前存活。</p><details open><summary>固定输入</summary><RecordView value={files[experiment.configPath]?.content} /></details><details><summary>产物引用</summary><RecordView value={files[`experiments/${experiment.id}/artifacts.json`]?.content} /></details>
        <h3>评测记录</h3>{activeAssessment ? <><label>选择评测<select value={activeAssessment.id} onChange={event => setAssessmentId(event.target.value)}>{experimentResults.map(result => <option key={result.id} value={result.id}>{result.version} · {result.id} · {statusLabel(result.state)}</option>)}</select></label><p className="muted">不同评测版本分开展示，不合并排名。</p><RecordView value={files[activeAssessment.path.replace('/config.json', '/result.json')]?.content} /><details><summary>逐例输出</summary><RecordView value={files[activeAssessment.path.replace('/config.json', '/outputs.jsonl')]?.content} /></details></> : <p className="muted">尚无评测记录。训练成功不等于评测通过。</p>}
        <details open><summary>结果分析</summary><pre className="markdown-text">{text(files[`experiments/${experiment.id}/analysis.md`]?.content, '尚无分析')}</pre></details><details><summary>训练日志（局部预览）</summary><pre className="log-view">{text(files[`experiments/${experiment.id}/train.log`]?.content, '尚无日志')}</pre></details><button onClick={() => change(experiment.configPath, `实验反馈 · ${experiment.id}`)}>反馈这个实验</button>
      </div></aside>}
    </main>
    <footer className="statusbar"><div><button onClick={() => { setFeedbackTarget(generalFeedback); openDrawer('feedback'); }} aria-expanded={drawer === 'feedback'}><MessageSquare size={16} />协作与反馈<span className="count">{openRequests.length + pendingFeedback.length}</span></button><span className="footer-divider" /><button onClick={() => openDrawer('review')}><BookOpen size={16} />研究复盘</button></div><span className="footer-note"><CheckCheck size={15} />文件驱动 · 训练由 Agent 执行</span></footer>
  </div>;
}

function Empty({ title, detail }: { title: string; detail: string }) { return <div className="empty-section"><h3>{title}</h3><p className="muted">{detail}</p></div>; }
