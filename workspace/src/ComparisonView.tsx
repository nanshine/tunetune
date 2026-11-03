import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowLeftRight, Box, Info } from 'lucide-react';
import { comparableModels, comparisonSamples, compatibleMeasurements, document, evaluationRuns, object, preferredEvaluation, text } from './model';
import type { Snapshot } from './model';
import { RecordView, sampleLabel } from './RecordView';

export function ComparisonView({ files, projectName, initialExperimentId, connectionError, syncError, connected, onBack }: {
  files: Snapshot['files']; projectName: string; initialExperimentId: string | null;
  connectionError: string | null; syncError: string | null; connected: boolean; onBack: () => void;
}) {
  const models = comparableModels(files);
  const version = text(document(files, 'project.json').current_evaluation);
  const results = evaluationRuns(files);
  const initialRight = models.find(item => item.id === initialExperimentId)?.id ?? models[1]?.id ?? models[0]?.id ?? '';
  const [leftSelection, setLeftSelection] = useState(models.find(item => item.id !== initialRight)?.id ?? initialRight);
  const [rightSelection, setRightSelection] = useState(initialRight);
  const [sampleIndex, setSampleIndex] = useState(0);
  const backButton = useRef<HTMLButtonElement>(null);
  useEffect(() => { backButton.current?.focus(); }, []);

  const right = models.find(item => item.id === rightSelection) ?? models[1] ?? models[0];
  const left = models.find(item => item.id === leftSelection) ?? models.find(item => item.id !== right?.id) ?? models[0];
  const leftId = left?.id ?? '';
  const rightId = right?.id ?? '';
  const outputFile = files['comparison/outputs.jsonl'];
  const rows = comparisonSamples(files, leftId, rightId, version);
  const activeIndex = Math.min(sampleIndex, Math.max(0, rows.length - 1));
  const row = rows[activeIndex];
  const outputs = object(row?.outputs);
  const compatible = compatibleMeasurements(preferredEvaluation(results.filter(item => item.experimentId === leftId), version), preferredEvaluation(results.filter(item => item.experimentId === rightId), version));
  const error = connectionError || syncError;
  const status = error || (connected ? '本地已连接' : '正在连接');

  function renderOutput(id: string) {
    const value = outputs[id];
    return Object.hasOwn(outputs, id) && value != null && (typeof value !== 'string' || value.trim() !== '') && (typeof value !== 'object' || Array.isArray(value) ? !Array.isArray(value) || value.length > 0 : Object.keys(value).length > 0)
      ? <div className="output-paper"><RecordView value={value} /></div>
      : <div className="missing-output"><p>暂无该输入的输出</p><p className="muted">可在 Agent 会话中请求生成对照输出。</p></div>;
  }

  return <div className="comparison-shell">
    <a className="skip-link" href="#model-comparison">跳到输出对照</a>
    <header className="comparison-header">
      <button ref={backButton} className="text-button back-button" onClick={onBack}><ArrowLeft size={18} />返回工作台</button>
      <span className="header-divider" />
      <div className="comparison-project"><Box size={17} /><strong>{projectName}</strong></div>
      <div className={`connection ${error ? 'warning' : ''}`} role="status" title={status}><span className="connection-dot" aria-hidden="true" />{status}</div>
    </header>
    <main className="comparison-layout">
      <aside className="sample-sidebar" aria-label="对照样例">
        <div className="comparison-section-heading"><h2>对照样例</h2><span className="sample-count">{rows.length ? activeIndex + 1 : 0} / {rows.length}</span></div>
        <div className="sample-list">{rows.map((item, index) => <button key={text(item.sample_id, String(index))} className={index === activeIndex ? 'active' : ''} aria-pressed={index === activeIndex} onClick={() => setSampleIndex(index)}><span>{sampleLabel(item, index)}</span><small>{text(item.input, '查看相同输入')}</small></button>)}</div>
        {!rows.length && <div className="empty-section"><h3>尚无对照样例</h3><p className="muted">{outputFile ? '对照输出文件为空。' : '请在 Agent 会话中准备同一输入的模型输出。'}</p></div>}
      </aside>
      <section id="model-comparison" className="comparison-workspace" tabIndex={-1}>
        <div className="comparison-title"><h1>模型对比</h1><p>在相同输入下阅读输出，生成请求与选择请在 Agent 会话中沟通。</p></div>
        {models.length > 0 ? <>
          <div className="model-selectors">
            <div><label>左侧模型<select value={leftId} onChange={event => setLeftSelection(event.target.value)}>{models.map(item => <option key={item.id} value={item.id}>{item.title}{item.targetKind === 'api' ? ' · 在线参照' : ''}</option>)}</select></label><p className="model-description">{[left?.modelName, left?.method].filter(Boolean).join(' · ')}</p></div>
            <button className="icon-button swap-button" aria-label="交换左右模型" onClick={() => { setLeftSelection(rightId); setRightSelection(leftId); }} disabled={models.length < 2}><ArrowLeftRight size={19} /></button>
            <div><label>右侧模型<select value={rightId} onChange={event => setRightSelection(event.target.value)}>{models.map(item => <option key={item.id} value={item.id}>{item.title}{item.targetKind === 'api' ? ' · 在线参照' : ''}</option>)}</select></label><p className="model-description">{[right?.modelName, right?.method].filter(Boolean).join(' · ')}</p></div>
          </div>
          {!compatible && leftId !== rightId && <p className="notice">尚无相同评测条件下的已验证结果；这里仅阅读输出，不据此排名。</p>}
          {leftId === rightId && <div className="notice" role="status"><Info size={15} />左右为同一模型；选择不同模型可对比输出差异。</div>}
        </> : <div className="empty-section"><h3>暂无可对比的模型</h3><p className="muted">验证成功的本地模型和在线参照会出现在这里，在线参照不代表本地交付。</p></div>}
        {row ? <>
          <section className="shared-input"><h3>输入（两侧相同）</h3><div className="reading-block"><RecordView value={row.input} /></div></section>
          {!!models.length && <div className="output-comparison">
            <section><h3>左侧 · {left?.title}</h3>{renderOutput(leftId)}</section>
            <section><h3>右侧 · {right?.title}</h3>{renderOutput(rightId)}</section>
          </div>}
        </> : !!models.length && <div className="empty-section"><h3>没有可显示的输入</h3><p className="muted">等待 Agent 准备对照输出，无需重新训练或在此提交请求。</p></div>}
      </section>
    </main>
  </div>;
}
