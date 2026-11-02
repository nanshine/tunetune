import { useEffect, useState } from 'react';
import { ArrowLeft, ArrowLeftRight, Box, Info } from 'lucide-react';
import { array, object, text } from './model';
import type { JsonObject, Snapshot } from './model';
import { RecordView } from './RecordView';

type Collection = [string, JsonObject][];

export function AcceptanceView({ files, projectName, releases, acceptances, initialReleasePath, connectionError, syncError, connected, onBack }: {
  files: Snapshot['files']; projectName: string; releases: Collection; acceptances: Collection; initialReleasePath: string | null;
  connectionError: string | null; syncError: string | null; connected: boolean; onBack: () => void;
}) {
  const validInitial = releases.some(([path]) => path === initialReleasePath) ? initialReleasePath! : releases[0]?.[0] ?? '';
  const initialLeft = releases.find(([path]) => path !== validInitial)?.[0] ?? validInitial;
  const [leftPath, setLeftPath] = useState(initialLeft);
  const [rightPath, setRightPath] = useState(validInitial);
  const [setPath, setSetPath] = useState(acceptances[0]?.[0] ?? '');
  const [sampleIndex, setSampleIndex] = useState(0);
  const releasePaths = releases.map(([path]) => path).join('|');
  const acceptancePaths = acceptances.map(([path]) => path).join('|');

  useEffect(() => {
    if (!releases.some(([path]) => path === leftPath)) setLeftPath(releases[0]?.[0] ?? '');
    if (!releases.some(([path]) => path === rightPath)) setRightPath(releases[0]?.[0] ?? '');
  }, [releasePaths]);
  useEffect(() => {
    if (!acceptances.some(([path]) => path === setPath)) setSetPath(acceptances[0]?.[0] ?? '');
    setSampleIndex(0);
  }, [acceptancePaths]);

  const leftRelease = releases.find(([path]) => path === leftPath)?.[1];
  const rightRelease = releases.find(([path]) => path === rightPath)?.[1];
  const leftId = text(leftRelease?.id, leftPath);
  const rightId = text(rightRelease?.id, rightPath);
  const outputPath = setPath.replace('/config.json', '/outputs.jsonl');
  const rows = setPath ? array(files[outputPath]?.content).map(object) : [];
  const activeIndex = Math.min(sampleIndex, Math.max(0, rows.length - 1));
  const row = rows[activeIndex];
  const outputs = object(row?.outputs);
  const status = connectionError || syncError || (connected ? '本地已连接' : '正在连接');

  function missingOutput() {
    return <div className="missing-output"><p>暂无该输入的输出</p><p className="muted">可在 Agent 客户端请求生成对照输出。</p></div>;
  }

  return <div className="acceptance-shell">
    <a className="skip-link" href="#acceptance-comparison">跳到输出对照</a>
    <header className="acceptance-header">
      <button className="text-button back-button" onClick={onBack}><ArrowLeft size={18} />返回工作台</button>
      <span className="header-divider" />
      <div className="acceptance-project"><Box size={17} /><strong>{projectName}</strong></div>
      <div className={`connection ${connectionError || syncError ? 'warning' : ''}`} role="status" title={status}><span className="connection-dot" />{status}</div>
    </header>
    <main className="acceptance-layout">
      <aside className="sample-sidebar" aria-label="对照样例">
        <div className="acceptance-section-heading"><h1>对照样例</h1>{acceptances.length > 0 && <span className="sample-count">{rows.length ? activeIndex + 1 : 0} / {rows.length}</span>}</div>
        {acceptances.length > 1 && <label>样例集<select value={setPath} onChange={event => { setSetPath(event.target.value); setSampleIndex(0); }}>{acceptances.map(([path, config]) => <option key={path} value={path}>{text(config.version, text(config.id, path))}</option>)}</select></label>}
        {acceptances.length === 1 && <div className="sample-set-label">样例集 {text(acceptances[0][1].version, text(acceptances[0][1].id, '已固定'))}</div>}
        <div className="sample-list">{rows.map((item, index) => <button key={text(item.sample_id, String(index))} className={index === activeIndex ? 'active' : ''} onClick={() => setSampleIndex(index)}><span>{text(item.sample_id, `样例 ${index + 1}`)}</span><small>{text(item.input, '查看相同输入')}</small></button>)}</div>
        {!acceptances.length && <div className="empty-section"><h3>尚无对照样例</h3><p className="muted">由 Agent 准备固定样例集与交付输出后，在这里进行比较。</p></div>}
        {!!acceptances.length && !rows.length && <p className="muted">对照输出尚未准备。</p>}
      </aside>
      <section id="acceptance-comparison" className="comparison-workspace" tabIndex={-1}>
        <div className="comparison-title"><h2>输出对照</h2><p>左右均可选择任意已交付模型。</p></div>
        {releases.length > 0 ? <>
          <div className="release-selectors">
            <label>左侧交付模型<select value={leftPath} onChange={event => setLeftPath(event.target.value)}>{releases.map(([path, release]) => <option key={path} value={path}>{text(release.id, path)} · {text(release.artifact_id, '未记录产物')}</option>)}</select><span className="artifact-label">{text(leftRelease?.artifact_id, '未记录产物')}</span></label>
            <button className="icon-button swap-button" aria-label="交换左右交付模型" onClick={() => { setLeftPath(rightPath); setRightPath(leftPath); }} disabled={releases.length < 2}><ArrowLeftRight size={19} /></button>
            <label>右侧交付模型<select value={rightPath} onChange={event => setRightPath(event.target.value)}>{releases.map(([path, release]) => <option key={path} value={path}>{text(release.id, path)} · {text(release.artifact_id, '未记录产物')}</option>)}</select><span className="artifact-label">{text(rightRelease?.artifact_id, '未记录产物')}</span></label>
          </div>
          {leftPath === rightPath && <div className="notice"><Info size={15} />左右为同一交付模型；选择不同模型可对比输出差异。</div>}
          {row ? <>
            <section className="shared-input"><h3>用户输入（相同）</h3><div className="reading-block"><RecordView value={row.input} /></div></section>
            <div className="output-comparison">
              <section><h3>左侧模型输出</h3>{Object.hasOwn(outputs, leftId) ? <div className="output-paper"><RecordView value={outputs[leftId]} /></div> : missingOutput()}</section>
              <section><h3>右侧模型输出</h3>{Object.hasOwn(outputs, rightId) ? <div className="output-paper"><RecordView value={outputs[rightId]} /></div> : missingOutput()}</section>
            </div>
          </> : <div className="empty-section"><h3>没有可显示的输入</h3><p className="muted">选择其他样例集，或等待 Agent 准备对照输出。</p></div>}
        </> : <div className="empty-section"><h3>暂无交付模型</h3><p className="muted">在 Agent 会话中明确选择发布后，交付成果会出现在这里。</p></div>}
      </section>
    </main>
  </div>;
}
