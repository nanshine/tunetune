import { useEffect, useRef, useState } from 'react';
import { ClipboardCheck, Columns2, Files, FlaskConical, Target, X } from 'lucide-react';
import { useWorkspace } from './useWorkspace';
import { deliveryIds, document, evaluationRuns, experiments, text } from './model';
import type { Snapshot } from './model';
import { Lineage } from './Lineage';
import { ComparisonView } from './ComparisonView';
import { ProposalView, ResourcesView } from './ProjectBrief';
import { EvaluationView } from './EvaluationView';
import { ExperimentDetails } from './ExperimentDetails';

type Panel = 'proposal' | 'resources' | 'evaluation';
const emptyFiles: Snapshot['files'] = {};
const panelTitles: Record<Panel, string> = { proposal: '研究提案', resources: '资源', evaluation: '评测定义' };

export function App() {
  const { snapshot, connectionError, renameProject } = useWorkspace();
  const files = snapshot?.files ?? emptyFiles;
  const project = document(files, 'project.json');
  const items = experiments(files);
  const results = evaluationRuns(files);
  const deliveries = new Set(deliveryIds(files));
  const [panel, setPanel] = useState<Panel>('proposal');
  // Open the proposal once, not again on file refreshes or navigation back to the canvas.
  const [panelOpen, setPanelOpen] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [comparison, setComparison] = useState(false);
  const [comparisonExperiment, setComparisonExperiment] = useState<string | null>(null);
  const [evaluationSelection, setEvaluationSelection] = useState('');
  const drawerHeading = useRef<HTMLHeadingElement>(null);
  const proposalTab = useRef<HTMLButtonElement>(null);
  const lastTrigger = useRef<HTMLElement | null>(null);
  const detailTrigger = useRef<HTMLElement | null>(null);
  const comparisonTrigger = useRef<HTMLElement | null>(null);
  const experiment = items.find(item => item.id === selected);
  const error = connectionError || snapshot?.error;
  const ready = !!files['project.json'];
  const version = text(project.current_evaluation);
  const projectName = text(project.name, 'TuneTune');
  useEffect(() => { window.document.title = `${projectName} · 研究空间`; }, [projectName]);
  useEffect(() => { if (panelOpen && !comparison) drawerHeading.current?.focus(); }, [panel, panelOpen, comparison]);
  function closePanel() { setPanelOpen(false); (lastTrigger.current ?? proposalTab.current)?.focus(); }
  function openPanel(next: Panel) {
    lastTrigger.current = window.document.activeElement as HTMLElement;
    if (panelOpen && panel === next) closePanel(); else { setDetailsOpen(false); setPanel(next); setPanelOpen(true); }
  }
  function selectExperiment(id: string) {
    detailTrigger.current = window.document.activeElement as HTMLElement;
    setSelected(id); setDetailsOpen(true); setPanelOpen(false);
  }
  function closeDetails() { setDetailsOpen(false); detailTrigger.current?.focus(); }
  function openComparison(id: string | null) {
    comparisonTrigger.current = window.document.activeElement as HTMLElement;
    setComparisonExperiment(id); setComparison(true);
  }
  function closeComparison() {
    setComparison(false);
    requestAnimationFrame(() => comparisonTrigger.current?.focus());
  }

  return <>
    {comparison && <div className="app-shell comparison-mode" onKeyDown={event => { if (event.key === 'Escape') closeComparison(); }}><ComparisonView files={files} projectName={projectName} initialExperimentId={comparisonExperiment} connectionError={connectionError} syncError={snapshot?.error ?? null} connected={!!snapshot} onBack={closeComparison} /></div>}
    {/* Keep the canvas mounted and sized so comparison navigation never resets its viewport. */}
    <div className={`app-shell ${comparison ? 'canvas-hidden' : ''}`} aria-hidden={comparison} inert={comparison} onKeyDown={event => { if (event.key === 'Escape') { if (panelOpen) closePanel(); else if (detailsOpen) closeDetails(); } }}>
      <a className="skip-link" href="#workspace">跳到研究空间</a>
      <header className="topbar">
        <button className="primary comparison-entry" onClick={() => openComparison(null)}><Columns2 size={18} />模型对比</button>
        <ProjectName name={projectName} digest={files['project.json']?.sha256} disabled={!ready || !!error} onSave={renameProject} />
        <div className={`connection glass-chip ${error ? 'warning' : ''}`} role="status" title={error ?? (snapshot ? '本地已连接' : '正在连接')}><span className="connection-dot" aria-hidden="true" /><span className="connection-label">{connectionError ? '连接中断' : snapshot?.error ? '同步待恢复' : snapshot ? '本地已连接' : '正在连接'}</span></div>
      </header>
      {error && <div className="sync-banner" role="alert">{error} · {ready ? '保留最后可用内容，正在自动重试。' : '请检查研究目录与文件格式，正在自动重试。'}</div>}
      <main id="workspace" className="workspace" tabIndex={-1}>
        <section className="canvas-region" aria-label="实验谱系画布">
          <Lineage items={items} results={results} currentVersion={version} selected={selected} deliveries={deliveries} onSelect={selectExperiment} onCompare={openComparison} />
          {!items.length && <div className="empty-canvas"><div className="empty-symbol"><FlaskConical size={30} strokeWidth={1.4} /></div><div className="eyebrow">从一件想完成的小事开始</div><h2>{ready ? '工作空间已就绪' : '等待研究文件'}</h2><p>{ready ? '和 Agent 一起明确提案、了解资源，\n用具体例子确认什么结果对你有用。' : '请让 Agent 建立工作空间，\n准备好后，内容会自动出现在这里。'}</p><button className="primary" onClick={() => openPanel('proposal')}><Target size={16} />查看研究提案</button></div>}
        </section>
        <div className={`left-dock ${panelOpen ? 'open' : ''}`}>
          <aside id="left-panel-content" className="drawer left-drawer" aria-labelledby="drawer-title" aria-hidden={!panelOpen} inert={!panelOpen}>
            <div className="drawer-header"><h2 ref={drawerHeading} id="drawer-title" tabIndex={-1}>{panelTitles[panel]}</h2><button className="icon-button" aria-label={`关闭${panelTitles[panel]}`} onClick={closePanel}><X size={19} /></button></div>
            <div className="drawer-content" key={panel}>
              {panel === 'proposal' && <ProposalView proposal={document(files, 'proposal.json')} />}
              {panel === 'resources' && <ResourcesView resources={document(files, 'resources.json')} observations={snapshot?.observations} />}
              {panel === 'evaluation' && <EvaluationView files={files} currentVersion={version} selection={evaluationSelection} onSelect={setEvaluationSelection} />}
            </div>
          </aside>
          <nav className="panel-tabs" aria-label="研究资料">
            <button ref={proposalTab} className={panelOpen && panel === 'proposal' ? 'active' : ''} onClick={() => openPanel('proposal')} aria-expanded={panelOpen && panel === 'proposal'} aria-controls="left-panel-content"><Target size={20} /><span>提案</span></button>
            <button className={panelOpen && panel === 'resources' ? 'active' : ''} onClick={() => openPanel('resources')} aria-expanded={panelOpen && panel === 'resources'} aria-controls="left-panel-content"><Files size={20} /><span>资源</span></button>
            <button className={panelOpen && panel === 'evaluation' ? 'active' : ''} onClick={() => openPanel('evaluation')} aria-expanded={panelOpen && panel === 'evaluation'} aria-controls="left-panel-content" aria-label="评测 Evaluation"><ClipboardCheck size={20} /><span>评测</span></button>
          </nav>
        </div>
        {detailsOpen && experiment && <ExperimentDetails key={experiment.id} experiment={experiment} results={results} files={files} currentVersion={version} delivered={deliveries.has(experiment.id)} onClose={closeDetails} onCompare={() => openComparison(experiment.id)} />}
      </main>
    </div>
  </>;
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
  return <div className="project-island">
    {draft ? <input ref={input} id="project-name" className="project-name-input" aria-label="项目名称" value={draft.name} readOnly={saving} autoComplete="off" spellCheck={false} aria-busy={saving} aria-invalid={!!error} aria-describedby="project-name-status" onChange={event => { setDraft({ ...draft, name: event.target.value }); setError(''); }} onBlur={() => void save(false)} onKeyDown={event => {
      if (event.nativeEvent.isComposing) return;
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); if (!inFlight.current) close(true); }
      if (event.key === 'Enter') { event.preventDefault(); void save(true); }
    }} /> : <button ref={trigger} className="project-name-trigger" disabled={disabled} aria-label={`编辑项目名称：${name}`} onClick={() => { if (digest) setDraft({ name, digest }); }}><span>{name}</span></button>}
    <span id="project-name-status" className={error ? 'project-name-error' : 'sr-only'} role="status">{error || (saving ? '正在保存名称' : '点击外部或按 Enter 保存，Esc 取消')}</span>
  </div>;
}
