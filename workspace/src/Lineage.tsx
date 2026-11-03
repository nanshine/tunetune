import { useEffect, useMemo } from 'react';
import { Background, Handle, Position, ReactFlow, useReactFlow, useViewport } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';
import { Maximize2, Minus, Plus, Star } from 'lucide-react';
import { compatibleMeasurements, experimentNumber, layout, NODE_HEIGHT, NODE_WIDTH, outcomeLabels, preferredEvaluation, statusLabel } from './model';
import type { Analysis, EvaluationRun, Experiment, PlanItem } from './model';

type ExperimentData = { kind: 'experiment'; experiment: Experiment; evaluation?: EvaluationRun; delivered: boolean; comparisonWarning?: boolean };
type PlannedData = { kind: 'planned'; item: PlanItem };
type CanvasNode = Node<ExperimentData | PlannedData, 'experiment'>;

export function OutcomeBadge({ analysis }: { analysis: Analysis }) {
  return <span className={`badge outcome-${analysis.outcome}`}>{outcomeLabels[analysis.outcome]}</span>;
}
export function StateDot({ state }: { state: string }) {
  return <span className={`state-dot state-${state}`} role="img" aria-label={statusLabel(state)} title={statusLabel(state)} />;
}

// The node shows identity, state and one headline measurement; everything else is in the details window.
export function ExperimentSummary({ experiment, evaluation, delivered, comparisonWarning }: Omit<ExperimentData, 'kind'>) {
  const measured = evaluation?.state === 'succeeded' ? Object.entries(evaluation.metrics)[0] : undefined;
  return <>
    <div className="node-top"><span className="node-number">{experimentNumber(experiment.id)}</span><StateDot state={experiment.state} />{delivered && <span className="node-delivered" title="已选为交付模型"><Star size={12} aria-hidden="true" />交付</span>}</div>
    <h3 className="node-title">{experiment.title}</h3>
    <div className="node-bottom">
      {measured ? <span className={`node-metric ${comparisonWarning ? 'incompatible' : ''}`} title={comparisonWarning ? '评测内容或输入不同，分数不宜直接比较' : undefined}><span>{Object.hasOwn(evaluation!.metricLabels, measured[0]) ? evaluation!.metricLabels[measured[0]] : measured[0]}</span><strong>{measured[1].toLocaleString(undefined, { maximumFractionDigits: 3 })}</strong></span> : <span className="node-metric empty">尚无同版本评测</span>}
      {experiment.analysis.outcome !== 'unknown' && <OutcomeBadge analysis={experiment.analysis} />}
    </div>
  </>;
}

function CanvasCard({ data, selected }: NodeProps<CanvasNode>) {
  if (data.kind === 'planned') return <article className="experiment-node planned" aria-label={`计划中的实验 ${data.item.title}`}>
    <Handle type="target" position={Position.Left} />
    <div className="node-top"><span className="node-number">{experimentNumber(data.item.id)}</span><span className="badge">计划中</span></div>
    <h3 className="node-title">{data.item.title}</h3>
    <p className="node-question">{data.item.question}</p>
    <Handle type="source" position={Position.Right} />
  </article>;
  return <article className={`experiment-node ${selected ? 'selected' : ''}`}>
    <Handle type="target" position={Position.Left} />
    <ExperimentSummary {...data} />
    <Handle type="source" position={Position.Right} />
  </article>;
}
const nodeTypes = { experiment: CanvasCard };

function CanvasControls() {
  const { zoomIn, zoomOut, fitView } = useReactFlow();
  const { zoom } = useViewport();
  return <div className="canvas-controls" aria-label="画布缩放"><button className="icon-button" aria-label="缩小画布" onClick={() => zoomOut({ duration: 0 })}><Minus size={15} /></button><span className="zoom-value">{Math.round(zoom * 100)}%</span><button className="icon-button" aria-label="放大画布" onClick={() => zoomIn({ duration: 0 })}><Plus size={15} /></button><span className="control-divider" /><button className="ghost-button" onClick={() => fitView({ padding: 0.25, duration: 200 })}><Maximize2 size={14} />全图</button></div>;
}

function FocusNode({ id, positions }: { id: string | null; positions: Map<string, { x: number; y: number }> }) {
  const { setCenter, getZoom } = useReactFlow();
  useEffect(() => {
    const position = id ? positions.get(id) : undefined;
    if (position) void setCenter(position.x + NODE_WIDTH / 2, position.y + NODE_HEIGHT / 2, { zoom: Math.max(getZoom(), 0.8), duration: 250 });
  }, [id, positions, setCenter, getZoom]);
  return null;
}

export function Lineage({ items, planned = [], results, currentVersion, selected, focus = null, deliveries, onSelect }: { items: Experiment[]; planned?: PlanItem[]; results: EvaluationRun[]; currentVersion: string; selected: string | null; focus?: string | null; deliveries: Set<string>; onSelect: (id: string) => void }) {
  const topology = JSON.stringify([...items.map(({ id, parent }) => ({ id, parent })), ...planned.map(({ id, parent }) => ({ id, parent }))]);
  const positions = useMemo(() => layout(JSON.parse(topology) as { id: string; parent: string | null }[]), [topology]);
  const nodes: CanvasNode[] = items.map(experiment => ({
    id: experiment.id, type: 'experiment', position: positions.get(experiment.id)!, selected: selected === experiment.id, width: NODE_WIDTH, height: NODE_HEIGHT,
    data: { kind: 'experiment', experiment, evaluation: preferredEvaluation(results.filter(result => result.experimentId === experiment.id), currentVersion), delivered: deliveries.has(experiment.id) },
  }));
  nodes.push(...planned.map(item => ({ id: item.id, type: 'experiment' as const, position: positions.get(item.id)!, width: NODE_WIDTH, height: NODE_HEIGHT, selectable: false, data: { kind: 'planned' as const, item } })));
  const measured = nodes.flatMap(node => node.data.kind === 'experiment' && node.data.evaluation?.state === 'succeeded' ? [node.data.evaluation] : []);
  for (const node of nodes) {
    if (node.data.kind !== 'experiment') continue;
    const result = node.data.evaluation;
    if (result?.state === 'succeeded') node.data.comparisonWarning = measured.some(other => other.experimentId !== result.experimentId && !compatibleMeasurements(result, other));
  }
  const ids = new Set(nodes.map(node => node.id));
  const edges = [...items.map(item => ({ id: item.id, parent: item.parent, planned: false })), ...planned.map(item => ({ id: item.id, parent: item.parent, planned: true }))]
    .filter(item => item.parent && ids.has(item.parent))
    .map(item => ({ id: `${item.parent}-${item.id}`, source: item.parent!, target: item.id, type: 'default', className: item.planned ? 'planned-edge' : '' }));
  return <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodeClick={(_, node) => { if (items.some(item => item.id === node.id)) onSelect(node.id); }} nodesDraggable={false} nodesConnectable={false} edgesReconnectable={false} deleteKeyCode={null} minZoom={0.25} maxZoom={1.5} fitView fitViewOptions={{ padding: 0.3, maxZoom: 1 }} ariaLabelConfig={{ 'node.a11yDescription.default': '实验节点，按 Enter 查看详情。', 'node.a11yDescription.keyboardDisabled': '实验节点，点击查看详情。', 'edge.a11yDescription.default': '方法派生关系，不代表指标比较对象。' }} proOptions={{ hideAttribution: false }}>
    <Background gap={20} size={1.2} color="#d3d9e3" />
    <CanvasControls />
    <FocusNode id={focus} positions={positions} />
  </ReactFlow>;
}
