import { useMemo, useState } from 'react';
import { Background, Handle, Position, ReactFlow, useReactFlow, useViewport } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';
import { ArrowUpRight, CheckCircle2, Clock3, FlaskConical, Maximize2, Minus, Plus, XCircle } from 'lucide-react';
import { outcomeLabels, layout, compatibleMeasurements, preferredEvaluation, roleLabels, statusLabel } from './model';
import { UsageView } from './UsageView';
import type { Analysis, EvaluationRun, Experiment } from './model';

type ExperimentNode = Node<{ experiment: Experiment; evaluation?: EvaluationRun; currentVersion: string; delivered: boolean; comparisonWarning?: boolean; onSelect: () => void; onCompare: () => void }, 'experiment'>;

export function StateIcon({ state }: { state: string }) {
  if (state === 'succeeded') return <CheckCircle2 size={16} aria-hidden="true" />;
  if (state === 'failed') return <XCircle size={16} aria-hidden="true" />;
  return <Clock3 size={16} aria-hidden="true" />;
}
export function OutcomeBadge({ analysis }: { analysis: Analysis }) {
  return <span className={`record-badge outcome-${analysis.outcome}`}>{outcomeLabels[analysis.outcome]}</span>;
}

export function ExperimentSummary({ experiment, evaluation, currentVersion, delivered, comparisonWarning, onSelect, onCompare }: ExperimentNode['data']) {
  const sameVersion = evaluation?.version === currentVersion ? evaluation : undefined;
  return <>
    <div className="card-heading"><span className="node-icon"><FlaskConical size={18} aria-hidden="true" /></span><div><span className="mono">{experiment.id}</span><h3>{experiment.title}</h3></div>{delivered && <span className="badge">已交付</span>}</div>
    <div className="role-list">{experiment.role && <span className="record-badge">{roleLabels[experiment.role] || experiment.role}</span>}{experiment.targetKind && <span className="record-badge">{experiment.targetKind === 'api' ? '在线 API' : '本地模型'}</span>}</div>
    <UsageView usage={experiment.usage} />
    <div className="result-row"><span>执行</span><span className={`status ${experiment.state}`}><StateIcon state={experiment.state} />{statusLabel(experiment.state)}</span></div>
    <div className="result-row"><span>结论</span><OutcomeBadge analysis={experiment.analysis} /></div>
    {(experiment.modelName || experiment.method) && <p className="node-method">{[experiment.modelName, experiment.method].filter(Boolean).join(' · ')}</p>}
    {sameVersion ? <div className="evaluation-summary"><div className="result-row"><span>评测 <strong>{sameVersion.version}</strong></span><span className={`status ${sameVersion.state}`}><StateIcon state={sameVersion.state} />{statusLabel(sameVersion.state)}</span></div>{sameVersion.state === 'succeeded' && <div className="metric-list">{Object.entries(sameVersion.metrics).slice(0, 3).map(([key, value]) => <span key={key}>{Object.hasOwn(sameVersion.metricLabels, key) ? sameVersion.metricLabels[key] : key}<strong>{value.toLocaleString()}</strong></span>)}</div>}</div> : <div className="result-row muted"><span>评测 {currentVersion}</span><span>尚无同版本结果</span></div>}
    {comparisonWarning && <p className="muted">评测内容或输入不同，分数不宜直接比较。</p>}
    <div className="node-actions"><button className="primary nodrag" onClick={event => { event.stopPropagation(); onSelect(); }} aria-label={`查看实验 ${experiment.id}`}>查看详情<ArrowUpRight size={14} /></button>{experiment.state === 'succeeded' && experiment.targetKind && <button className="nodrag" onClick={event => { event.stopPropagation(); onCompare(); }}>模型对比</button>}</div>
  </>;
}

function ExperimentCard({ data, selected }: NodeProps<ExperimentNode>) {
  return <article className={`experiment-card ${selected ? 'selected' : ''}`}>
    <Handle type="target" position={Position.Left} />
    <ExperimentSummary {...data} />
    <Handle type="source" position={Position.Right} />
  </article>;
}
const nodeTypes = { experiment: ExperimentCard };

function CanvasControls() {
  const { zoomIn, zoomOut, fitView } = useReactFlow();
  const { zoom } = useViewport();
  return <div className="canvas-controls" aria-label="画布缩放"><button className="icon-button" aria-label="缩小画布" onClick={() => zoomOut({ duration: 0 })}><Minus size={16} /></button><span>{Math.round(zoom * 100)}%</span><button className="icon-button" aria-label="放大画布" onClick={() => zoomIn({ duration: 0 })}><Plus size={16} /></button><span className="control-divider" /><button className="fit-button" onClick={() => fitView({ padding: 0.2, duration: 0 })}><Maximize2 size={15} />回到全图</button></div>;
}

export function Lineage({ items, results, currentVersion, selected, deliveries, onSelect, onCompare }: { items: Experiment[]; results: EvaluationRun[]; currentVersion: string; selected: string | null; deliveries: Set<string>; onSelect: (id: string) => void; onCompare: (id: string) => void }) {
  const topology = JSON.stringify(items.map(({ id, parent }) => ({ id, parent })));
  const positions = useMemo(() => layout(JSON.parse(topology) as Experiment[]), [topology]);
  const [dimensions, setDimensions] = useState<Record<string, { width: number; height: number }>>({});
  const nodes: ExperimentNode[] = items.map(experiment => ({
    id: experiment.id, type: 'experiment', measured: dimensions[experiment.id], position: positions.get(experiment.id)!, selected: selected === experiment.id,
    data: { experiment, evaluation: preferredEvaluation(results.filter(result => result.experimentId === experiment.id), currentVersion), currentVersion, delivered: deliveries.has(experiment.id), onSelect: () => onSelect(experiment.id), onCompare: () => onCompare(experiment.id) },
  }));
  const measured = nodes.flatMap(node => node.data.evaluation?.state === 'succeeded' ? [node.data.evaluation] : []);
  for (const node of nodes) {
    const result = node.data.evaluation;
    if (result?.state === 'succeeded') node.data.comparisonWarning = measured.some(other => other.experimentId !== result.experimentId && !compatibleMeasurements(result, other));
  }
  const edges = items.filter(item => item.parent && items.some(parent => parent.id === item.parent)).map(item => ({ id: `${item.parent}-${item.id}`, source: item.parent!, target: item.id, type: 'smoothstep' }));
  return <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodesChange={changes => {
    const measured = changes.flatMap(change => change.type === 'dimensions' && change.dimensions ? [[change.id, change.dimensions]] : []);
    if (measured.length) setDimensions(previous => ({ ...previous, ...Object.fromEntries(measured) }));
  }} onNodeClick={(_, node) => onSelect(node.id)} nodesDraggable={false} nodesConnectable={false} edgesReconnectable={false} deleteKeyCode={null} minZoom={0.25} maxZoom={1.5} fitView fitViewOptions={{ padding: 0.2, maxZoom: 1 }} ariaLabelConfig={{ 'node.a11yDescription.default': '只读实验节点，可查看详情或模型对比。', 'node.a11yDescription.keyboardDisabled': '只读实验节点，可查看详情或模型对比。', 'edge.a11yDescription.default': '实验派生关系，不代表指标比较对象。' }} proOptions={{ hideAttribution: false }}>
    <Background gap={24} size={1} color="#d8dee8" />
    <CanvasControls />
  </ReactFlow>;
}
