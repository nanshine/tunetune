import { useMemo } from 'react';
import { Background, Controls, Handle, Position, ReactFlow } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';
import { FlaskConical } from 'lucide-react';
import { layout, statusLabel } from './model';
import type { Assessment, Experiment } from './model';

type ExperimentNode = Node<{ experiment: Experiment; assessments: Assessment[]; released: boolean; onSelect: () => void }, 'experiment'>;
function ExperimentCard({ data, selected }: NodeProps<ExperimentNode>) {
  const experiment = data.experiment;
  return <article className={`experiment-card ${selected ? 'selected' : ''}`}>
    <Handle type="target" position={Position.Left} />
    <div className="card-heading"><FlaskConical size={19} /><span className="mono">{experiment.id}</span>{data.released && <span className="badge">已发布</span>}</div>
    <h3>{experiment.title}</h3>
    <p className="muted">{experiment.parent ? `起点 · ${experiment.parent}` : '独立实验起点'}</p>
    <div className="result-row"><span>训练</span><span className={`status ${experiment.state}`}>{statusLabel(experiment.state)}</span></div>
    {data.assessments.length === 0 && <div className="result-row muted"><span>评测</span><span>尚无记录</span></div>}
    {data.assessments.slice(0, 2).map(assessment => <div key={assessment.id} className="assessment-summary"><div className="result-row"><span>评测 {assessment.version}</span><span className={`status ${assessment.state}`}>{statusLabel(assessment.state)}</span></div><div className="metric-list">{Object.entries(assessment.metrics).map(([key, value]) => <span key={key}>{Object.hasOwn(assessment.metricLabels, key) ? assessment.metricLabels[key] : key} <strong>{value.toLocaleString()}</strong></span>)}</div></div>)}
    <button className="card-footer nodrag" onClick={data.onSelect} aria-label={`查看实验 ${experiment.id}`}>查看实验记录{data.assessments.length > 2 ? ` · 共 ${data.assessments.length} 次评测` : ''} <span aria-hidden="true">↗</span></button>
    <Handle type="source" position={Position.Right} />
  </article>;
}
const nodeTypes = { experiment: ExperimentCard };
export function Lineage({ items, results, selected, releases, onSelect }: { items: Experiment[]; results: Assessment[]; selected: string | null; releases: Set<string>; onSelect: (id: string) => void }) {
  const topology = JSON.stringify(items.map(({ id, parent }) => ({ id, parent })));
  const positions = useMemo(() => layout(JSON.parse(topology) as Experiment[]), [topology]);
  const nodes: ExperimentNode[] = items.map(experiment => ({ id: experiment.id, type: 'experiment', position: positions.get(experiment.id)!, selected: selected === experiment.id, data: { experiment, assessments: results.filter(result => result.experimentId === experiment.id), released: releases.has(experiment.id), onSelect: () => onSelect(experiment.id) } }));
  const edges = items.filter(item => item.parent && items.some(parent => parent.id === item.parent)).map(item => ({ id: `${item.parent}-${item.id}`, source: item.parent!, target: item.id, type: 'smoothstep' }));
  return <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodeClick={(_, node) => onSelect(node.id)} nodesDraggable={false} nodesConnectable={false} edgesReconnectable={false} deleteKeyCode={null} minZoom={0.25} maxZoom={1.5} ariaLabelConfig={{ 'node.a11yDescription.default': '只读实验节点。使用查看实验按钮打开详情。', 'node.a11yDescription.keyboardDisabled': '只读实验节点。使用查看实验按钮打开详情。', 'edge.a11yDescription.default': '只读实验派生关系。', 'controls.zoomIn.ariaLabel': '放大画布', 'controls.zoomOut.ariaLabel': '缩小画布', 'controls.fitView.ariaLabel': '显示全图' }} defaultViewport={{ x: 0, y: 30, zoom: 0.9 }} proOptions={{ hideAttribution: false }}>
    <Background gap={22} size={1} color="#cbd3df" />
    <Controls showInteractive={false} />
  </ReactFlow>;
}
