import { useMemo, useState } from 'react';
import { Background, Handle, Position, ReactFlow, useReactFlow, useViewport } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';
import { ArrowUpRight, Box, CheckCircle2, CircleDashed, Clock3, FlaskConical, Maximize2, Minus, Plus, XCircle } from 'lucide-react';
import { layout, statusLabel, text } from './model';
import type { Assessment, Experiment, JsonObject } from './model';

type ExperimentNode = Node<{ experiment: Experiment; assessments: Assessment[]; deltas: Record<string, Record<string, number>>; released: boolean; onSelect: () => void; onAccept: () => void }, 'experiment'>;
type CandidateNode = Node<{ candidate: JsonObject; onFeedback: () => void }, 'candidate'>;

function StateIcon({ state }: { state: string }) {
  if (state === 'succeeded') return <CheckCircle2 size={16} />;
  if (state === 'failed') return <XCircle size={16} />;
  return <Clock3 size={16} />;
}
function ExperimentCard({ data, selected }: NodeProps<ExperimentNode>) {
  const experiment = data.experiment;
  return <article className={`experiment-card ${selected ? 'selected' : ''}`}>
    <Handle type="target" position={Position.Left} />
    <div className="card-heading"><span className="node-icon"><FlaskConical size={18} /></span><div><span className="mono">{experiment.id}</span><h3>{experiment.title}</h3></div>{data.released && <span className="badge">已发布</span>}</div>
    <div className="result-row"><span>训练</span><span className={`status ${experiment.state}`}><StateIcon state={experiment.state} />{statusLabel(experiment.state)}</span></div>
    {data.assessments.length === 0 && <div className="result-row muted"><span>评测</span><span>尚无记录</span></div>}
    {data.assessments.slice(0, 2).map(assessment => <div key={assessment.id} className="assessment-summary"><div className="result-row"><span>评测 {assessment.version}</span><span className={`status ${assessment.state}`}><StateIcon state={assessment.state} />{statusLabel(assessment.state)}</span></div><div className="metric-list">{Object.entries(assessment.metrics).map(([key, value]) => {
      const delta = data.deltas[assessment.id]?.[key];
      return <span key={key}>{Object.hasOwn(assessment.metricLabels, key) ? assessment.metricLabels[key] : key}<strong>{value.toLocaleString()}</strong>{delta !== undefined && delta !== 0 && <small className={delta > 0 ? 'delta-positive' : 'delta-negative'}>{delta > 0 ? '+' : ''}{delta.toLocaleString(undefined, { maximumFractionDigits: 3 })}</small>}</span>;
    })}</div></div>)}
    {experiment.artifact && <div className="artifact-row"><Box size={14} /><span>产物</span><span className="mono">{experiment.artifact}</span></div>}
    <div className="node-actions"><button className="primary nodrag" onClick={data.onSelect} aria-label={`查看实验 ${experiment.id}`}>查看结果<ArrowUpRight size={14} /></button>{data.released && <button className="nodrag" onClick={data.onAccept}>验收</button>}</div>
    <Handle type="source" position={Position.Right} />
  </article>;
}
function CandidateCard({ data }: NodeProps<CandidateNode>) {
  const candidate = data.candidate;
  return <article className="candidate-card"><Handle type="target" position={Position.Left} /><span className="node-icon"><CircleDashed size={19} /></span><div><span className="eyebrow">候选方案</span><h3>{text(candidate.title, '待命名方案')}</h3><p>{text(candidate.hypothesis, '等待讨论与验证')}</p>{text(candidate.parent_experiment_id) && <small>起点 · {text(candidate.parent_experiment_id)}</small>}<button className="text-button nodrag" onClick={data.onFeedback}>提出调整建议<ArrowUpRight size={13} /></button></div></article>;
}
const nodeTypes = { experiment: ExperimentCard, candidate: CandidateCard };

function CanvasControls() {
  const { zoomIn, zoomOut, fitView } = useReactFlow();
  const { zoom } = useViewport();
  return <div className="canvas-controls" aria-label="画布缩放"><button className="icon-button" aria-label="缩小画布" onClick={() => zoomOut({ duration: 0 })}><Minus size={16} /></button><span>{Math.round(zoom * 100)}%</span><button className="icon-button" aria-label="放大画布" onClick={() => zoomIn({ duration: 0 })}><Plus size={16} /></button><span className="control-divider" /><button className="fit-button" onClick={() => fitView({ padding: 0.2, duration: 0 })}><Maximize2 size={15} />回到全图</button></div>;
}

export function Lineage({ items, results, candidates, selected, releases, onSelect, onAccept, onCandidateFeedback }: { items: Experiment[]; results: Assessment[]; candidates: JsonObject[]; selected: string | null; releases: Set<string>; onSelect: (id: string) => void; onAccept: (id: string) => void; onCandidateFeedback: () => void }) {
  const topology = JSON.stringify(items.map(({ id, parent }) => ({ id, parent })));
  const positions = useMemo(() => layout(JSON.parse(topology) as Experiment[]), [topology]);
  const [dimensions, setDimensions] = useState<Record<string, { width: number; height: number }>>({});
  const experimentNodes: ExperimentNode[] = items.map(experiment => {
    const experimentResults = results.filter(result => result.experimentId === experiment.id);
    const parentResults = results.filter(result => result.experimentId === experiment.parent);
    const deltas = Object.fromEntries(experimentResults.map(assessment => {
      const parent = parentResults.find(result => result.version === assessment.version);
      return [assessment.id, Object.fromEntries(Object.entries(assessment.metrics).filter(([key]) => typeof parent?.metrics[key] === 'number').map(([key, value]) => [key, value - parent!.metrics[key]]))];
    }));
    return { id: experiment.id, type: 'experiment', measured: dimensions[experiment.id], position: positions.get(experiment.id)!, selected: selected === experiment.id, data: { experiment, assessments: experimentResults, deltas, released: releases.has(experiment.id), onSelect: () => onSelect(experiment.id), onAccept: () => onAccept(experiment.id) } };
  });
  const siblingCounts = new Map<string, number>();
  const maxX = Math.max(0, ...items.map(item => positions.get(item.id)?.x ?? 0));
  const candidateNodes: CandidateNode[] = candidates.map((candidate, index) => {
    const parent = text(candidate.parent_experiment_id);
    const sibling = siblingCounts.get(parent) ?? 0;
    siblingCounts.set(parent, sibling + 1);
    const parentPosition = positions.get(parent);
    const position = parentPosition ? { x: parentPosition.x + 340, y: parentPosition.y + 160 + sibling * 190 } : { x: maxX + 360, y: 160 + index * 200 };
    const id = text(candidate.id, `candidate-${index}`);
    return { id: `candidate:${id}`, type: 'candidate', measured: dimensions[`candidate:${id}`], position, data: { candidate, onFeedback: onCandidateFeedback } };
  });
  const experimentEdges = items.filter(item => item.parent && items.some(parent => parent.id === item.parent)).map(item => ({ id: `${item.parent}-${item.id}`, source: item.parent!, target: item.id, type: 'smoothstep' }));
  const candidateEdges = candidates.map((candidate, index) => ({ candidate, index })).filter(({ candidate }) => items.some(item => item.id === text(candidate.parent_experiment_id))).map(({ candidate, index }) => ({ id: `candidate-edge-${text(candidate.id, String(index))}`, source: text(candidate.parent_experiment_id), target: `candidate:${text(candidate.id, `candidate-${index}`)}`, type: 'smoothstep', animated: false, style: { strokeDasharray: '6 5' } }));
  return <ReactFlow nodes={[...experimentNodes, ...candidateNodes]} edges={[...experimentEdges, ...candidateEdges]} nodeTypes={nodeTypes} onNodesChange={changes => {
    const measured = changes.flatMap(change => change.type === 'dimensions' && change.dimensions ? [[change.id, change.dimensions]] : []);
    if (measured.length) setDimensions(previous => ({ ...previous, ...Object.fromEntries(measured) }));
  }} onNodeClick={(_, node) => { if (node.type === 'experiment') onSelect(node.id); }} nodesDraggable={false} nodesConnectable={false} edgesReconnectable={false} deleteKeyCode={null} minZoom={0.25} maxZoom={1.5} fitView fitViewOptions={{ padding: 0.2, maxZoom: 1 }} ariaLabelConfig={{ 'node.a11yDescription.default': '只读研究节点。使用节点内按钮查看详情或反馈。', 'node.a11yDescription.keyboardDisabled': '只读研究节点。使用节点内按钮查看详情或反馈。', 'edge.a11yDescription.default': '实线为实验派生关系，虚线为候选拟议关系。' }} proOptions={{ hideAttribution: false }}>
    <Background gap={24} size={1} color="#d8dee8" />
    <CanvasControls />
  </ReactFlow>;
}
