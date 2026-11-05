import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Boxes, ClipboardCheck, FlaskConical, ListChecks, PlayCircle, Target } from 'lucide-react';
import { loadModel, runAcceptance, submitResponse, tryModel, unloadModel, useWorkspace } from './useWorkspace';
import { deliveredModels, document, evaluationRuns, experimentNumber, experiments, plannedNodes, text } from './model';
import type { Snapshot, ViewName } from './model';
import { Lineage } from './Lineage';
import { AcceptanceView } from './AcceptanceView';
import { ProposalView, ResourcesView } from './ProjectBrief';
import { EvaluationView } from './EvaluationView';
import { ExperimentDetails } from './ExperimentDetails';
import { PlanView } from './PlanView';
import { FloatingWindow } from './FloatingWindow';
import type { WindowPlacement } from './FloatingWindow';

type Panel = 'proposal' | 'plan' | 'resources' | 'evaluation' | 'acceptance';
type WindowId = Panel | 'experiment';
const emptyFiles: Snapshot['files'] = {};
const panels: { id: Panel; label: string; title: string; icon: ReactNode }[] = [
  { id: 'proposal', label: '提案', title: '研究提案', icon: <Target size={18} /> },
  { id: 'plan', label: '方案', title: '实验方案', icon: <ListChecks size={18} /> },
  { id: 'resources', label: '资源', title: '资源', icon: <Boxes size={18} /> },
  { id: 'evaluation', label: '评测', title: '评测', icon: <ClipboardCheck size={18} /> },
  { id: 'acceptance', label: '验收', title: '验收', icon: <PlayCircle size={18} /> },
];
const MAX_PANELS = 2;

export function App() {
  const { snapshot, connectionError, renameProject } = useWorkspace();
  const files = snapshot?.files ?? emptyFiles;
  const project = document(files, 'project.json');
  const items = experiments(files);
  const planned = plannedNodes(files);
  const results = evaluationRuns(files);
  const deliveries = new Set(deliveredModels(files).map(item => item.id));
  const [windows, setWindows] = useState<Partial<Record<WindowId, WindowPlacement>>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [focus, setFocus] = useState<{ id: string; at: number } | null>(null);
  const [evaluationSelection, setEvaluationSelection] = useState('');
  const [evaluationTab, setEvaluationTab] = useState<'overview' | 'samples' | 'review' | undefined>(undefined);
  const top = useRef(10);
  const applied = useRef(0);
  const experiment = items.find(item => item.id === selected);
  const error = connectionError || snapshot?.error;
  const ready = !!files['project.json'];
  const version = text(project.current_evaluation);
  const projectName = text(project.name, 'TuneTune');
  const attention = snapshot?.view?.attention ?? [];
  const waiting = (view: ViewName) => attention.find(note => note.view === view)?.message ?? null;
  useEffect(() => { window.document.title = `${projectName} · TuneTune`; }, [projectName]);

  function open(id: WindowId, options: { maximized?: boolean } = {}) {
    setWindows(previous => {
      const next = { ...previous };
      if (!next[id] && id !== 'experiment') {
        const openPanels = (Object.keys(next) as WindowId[]).filter(key => key !== 'experiment');
        if (openPanels.length >= MAX_PANELS) delete next[openPanels.sort((a, b) => next[a]!.z - next[b]!.z)[0]];
      }
      const cascade = (Object.keys(next) as WindowId[]).filter(key => key !== 'experiment' && key !== id).length;
      next[id] = { dock: id === 'experiment' ? 'right' : 'left', position: null, cascade, ...next[id], maximized: options.maximized ?? next[id]?.maximized ?? id === 'acceptance', z: ++top.current };
      return next;
    });
  }
  function close(id: WindowId) {
    setWindows(previous => { const next = { ...previous }; delete next[id]; return next; });
    if (id === 'experiment') setSelected(null);
  }
  function update(id: WindowId, change: Partial<WindowPlacement>) {
    setWindows(previous => previous[id] ? { ...previous, [id]: { ...previous[id]!, ...change } } : previous);
  }
  function toggle(id: Panel) { if (windows[id]) close(id); else open(id); }
  function selectExperiment(id: string) { setSelected(id); open('experiment'); }
  function focusExperiment(id: string) {
    setFocus({ id, at: Date.now() });
    if (items.some(item => item.id === id)) selectExperiment(id);
  }

  // The Agent can ask the panel to show something; each request is applied once, then the person is free to move on.
  const view = snapshot?.view;
  useEffect(() => {
    if (!view || view.revision <= applied.current) return;
    applied.current = view.revision;
    for (const name of view.open) {
      if (name === 'review') { setEvaluationTab('review'); open('evaluation', { maximized: true }); }
      else open(name);
    }
    if (view.focus.experiment) focusExperiment(view.focus.experiment);
  }, [view?.revision]);

  const respond = (kind: 'proposal' | 'plan') => (decision: string, note: string, sha: string) => submitResponse({ kind, decision, target_sha256: sha, ...(note ? { note } : {}) });
  const content: Record<Panel, ReactNode> = {
    proposal: <ProposalView files={files} waiting={waiting('proposal')} onRespond={respond('proposal')} />,
    plan: <PlanView files={files} waiting={waiting('plan')} onRespond={respond('plan')} onFocusExperiment={focusExperiment} />,
    resources: <ResourcesView resources={document(files, 'resources.json')} observations={snapshot?.observations} />,
    evaluation: <EvaluationView key={evaluationTab} files={files} currentVersion={version} selection={evaluationSelection} onSelect={setEvaluationSelection} initialTab={evaluationTab}
      onReview={(reviewItems, sha) => submitResponse({ kind: 'evaluation_review', decision: 'submit', target_sha256: sha, items: reviewItems })} />,
    acceptance: <AcceptanceView files={files} job={snapshot?.acceptance} pool={snapshot?.models} onRun={runAcceptance} onTry={tryModel} onLoad={loadModel} onUnload={unloadModel} />,
  };
  const empty = !items.length && !planned.length;

  return <div className="app">
    <a className="skip-link" href="#canvas">跳到实验画布</a>
    <main id="canvas" className="canvas" tabIndex={-1} aria-label="实验画布">
      <Lineage items={items} planned={planned} results={results} currentVersion={version} selected={selected} focus={focus ? focus.id : null} deliveries={deliveries} onSelect={selectExperiment} />
      {empty && <div className="canvas-empty"><FlaskConical size={20} aria-hidden="true" /><p>{ready ? '实验会出现在这里' : '等待研究文件'}</p><span>{ready ? '每个实验是一个节点，连线表示它基于哪个实验。' : '让 Agent 建立研究目录后，这里会自动更新。'}</span></div>}
    </main>
    <header className="project-pill">
      <span className="brand" aria-hidden="true" />
      <ProjectName name={projectName} digest={files['project.json']?.sha256} disabled={!ready || !!error} onSave={renameProject} />
      {version && <span className="pill-meta" title="当前评测版本">评测 {version}</span>}
    </header>
    <div className={`connection ${error ? 'warning' : ''}`} role="status" title={error ?? undefined}><span className="connection-dot" aria-hidden="true" />{connectionError ? '连接中断' : snapshot?.error ? '同步待恢复' : snapshot ? '本地已连接' : '正在连接'}</div>
    {error && <div className="sync-banner" role="alert">{error}。{ready ? '保留上次的内容，正在自动重试。' : '请检查研究目录，正在自动重试。'}</div>}
    <nav className="tiles" aria-label="研究资料">{panels.map(panel => {
      const note = attention.find(item => item.view === panel.id || (panel.id === 'evaluation' && item.view === 'review'));
      return <button key={panel.id} className={`tile ${windows[panel.id] ? 'active' : ''}`} aria-pressed={!!windows[panel.id]} onClick={() => toggle(panel.id)} title={note?.message}>
        {panel.icon}<span>{panel.label}</span>{note && <span className="attention-dot" aria-label={`待处理：${note.message}`} />}
      </button>;
    })}</nav>
    {panels.filter(panel => windows[panel.id]).map(panel => <FloatingWindow key={panel.id} id={panel.id} title={panel.title} icon={panel.icon} placement={windows[panel.id]!}
      onClose={() => close(panel.id)} onToggleMaximized={() => update(panel.id, { maximized: !windows[panel.id]!.maximized })} onFocus={() => update(panel.id, { z: ++top.current })} onMove={position => update(panel.id, { position })}>
      {content[panel.id]}
    </FloatingWindow>)}
    {windows.experiment && experiment && <FloatingWindow key={experiment.id} id="experiment" title={`实验 ${experimentNumber(experiment.id)}`} icon={<FlaskConical size={18} />} placement={windows.experiment}
      onClose={() => close('experiment')} onToggleMaximized={() => update('experiment', { maximized: !windows.experiment!.maximized })} onFocus={() => update('experiment', { z: ++top.current })} onMove={position => update('experiment', { position })}>
      <ExperimentDetails experiment={experiment} experimentsById={new Map(items.map(item => [item.id, item]))} results={results} files={files} currentVersion={version} delivered={deliveries.has(experiment.id)} onOpenAcceptance={() => open('acceptance')} />
    </FloatingWindow>}
  </div>;
}

function ProjectName({ name, digest, disabled, onSave }: { name: string; digest?: string; disabled: boolean; onSave: (name: string, digest: string) => Promise<void> }) {
  const [draft, setDraft] = useState<{ name: string; digest: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const input = useRef<HTMLInputElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const inFlight = useRef(false);
  const editing = draft !== null;
  useEffect(() => {
    if (editing && input.current) {
      input.current.focus();
      input.current.setSelectionRange(input.current.value.length, input.current.value.length);
    }
  }, [editing]);
  function close(restoreFocus: boolean) {
    const focusTitle = restoreFocus && window.document.activeElement === input.current;
    setDraft(null);
    setError('');
    if (focusTitle) requestAnimationFrame(() => trigger.current?.focus());
  }
  async function save(restoreFocus: boolean) {
    if (!draft || inFlight.current) return;
    const next = draft.name.trim();
    if (!next || next === name) { close(restoreFocus); return; }
    if ([...next].length > 120 || /[\u0000-\u001f\u007f-\u009f]/.test(next)) { setError('名称最多 120 个字符，不能包含控制字符。'); return; }
    inFlight.current = true;
    setSaving(true);
    setError('');
    try { await onSave(next, draft.digest); close(restoreFocus); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '名称保存失败，请重试。'); }
    finally { inFlight.current = false; setSaving(false); }
  }
  return <div className="project-name">
    {draft ? <input ref={input} id="project-name" className="project-name-input" aria-label="项目名称" value={draft.name} readOnly={saving} autoComplete="off" spellCheck={false} aria-busy={saving} aria-invalid={!!error} aria-describedby="project-name-status" onChange={event => { setDraft({ ...draft, name: event.target.value }); setError(''); }} onBlur={() => void save(false)} onKeyDown={event => {
      if (event.nativeEvent.isComposing) return;
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); if (!inFlight.current) close(true); }
      if (event.key === 'Enter') { event.preventDefault(); void save(true); }
    }} /> : <button ref={trigger} className="project-name-trigger" disabled={disabled} aria-label={`编辑项目名称：${name}`} onClick={() => { if (digest) setDraft({ name, digest }); }}>{name}</button>}
    <span id="project-name-status" className={error ? 'project-name-error' : 'sr-only'} role="status">{error || (saving ? '正在保存名称' : '点击外部或按 Enter 保存，Esc 取消')}</span>
  </div>;
}
