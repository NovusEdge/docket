import { Background, Controls, MiniMap, ReactFlow, ReactFlowProvider, useReactFlow } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { ArrowDown, ArrowRight } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import type { ExportFn, ViewProps } from '@/App'
import { Button } from '@/components/ui/button'
import { neighbours, otherEnd } from '@/lib/model'
import type { ThemeChoice } from '@/lib/theme'
import { cn } from '@/lib/utils'
import { CARD, edgeId, graphInput, largestComponent, signature, type GraphInput } from './elk-input'
import { runLayout, type Layout } from './elk-layout'
import { exportGraph } from './export'
import { RecordNodeView, type RecordNode } from './record-node'
import { marker, RoutedEdgeView, type RoutedEdge } from './routed-edge'
import { UnlinkedList } from './unlinked-list'

const nodeTypes = { record: RecordNodeView }
const edgeTypes = { routed: RoutedEdgeView }

type GraphProps = ViewProps & {
  exportRef: RefObject<ExportFn | null>
  colorMode: ThemeChoice
  onDir(dir: 'RIGHT' | 'DOWN'): void
}

export function GraphView(props: GraphProps) {
  return (
    <ReactFlowProvider>
      <Graph {...props} />
    </ReactFlowProvider>
  )
}

function Graph({ ix, rows, state, fresh, filter, onSelect, exportRef, colorMode, onDir }: GraphProps) {
  const flow = useReactFlow()
  const box = useRef<HTMLDivElement>(null)
  const [laid, setLaid] = useState<{ sig: string; layout: Layout; input: GraphInput } | null>(null)
  const [hover, setHover] = useState<string | null>(null)
  // The view key the viewport was last opened for; a relayout under the same
  // key (a poll that added a record) keeps the reader's pan and zoom.
  const opened = useRef<string | null>(null)
  const dir = state.dir
  const viewKey = `${dir}|${state.lineage ?? ''}`
  const input = useMemo(() => graphInput(ix, rows, state.lineage), [ix, rows, state.lineage])
  const sig = signature(input, dir)

  // Keyed on sig alone: it covers input and dir, and text-only polls leave it unchanged.
  useEffect(() => {
    if (laid?.sig === sig) return
    let stale = false
    runLayout(input, dir).then(layout => {
      if (!stale) setLaid({ sig, layout, input })
    })
    return () => { stale = true }
  }, [sig])

  // The viewport comes from ELK's bounds and the container size, not fitView,
  // which sees no nodes until React Flow has rendered them.
  useEffect(() => {
    if (!laid || opened.current === viewKey || laid.sig !== sig || !box.current) return
    opened.current = viewKey
    if (state.lineage) {
      const { width, height } = box.current.getBoundingClientRect()
      const pad = 48
      const zoom = Math.min(1, (width - pad * 2) / laid.layout.width, (height - pad * 2) / laid.layout.height)
      flow.setViewport({ x: (width - laid.layout.width * zoom) / 2, y: (height - laid.layout.height * zoom) / 2, zoom })
      return
    }
    // The whole ledger opens at 100% on its largest component; fitting 160 cards would shrink the text to nothing.
    const main = [...largestComponent(laid.input)].map(id => laid.layout.pos.get(id)).filter(p => p !== undefined)
    if (!main.length) return
    flow.setViewport({ x: 24 - Math.min(...main.map(p => p.x)), y: 24 - Math.min(...main.map(p => p.y)), zoom: 1 })
  }, [laid, viewKey, sig, state.lineage, flow])

  useEffect(() => {
    exportRef.current = f => { if (laid) void exportGraph(f, laid.layout) }
    return () => { exportRef.current = null }
  }, [exportRef, laid])

  // Only a new selection recentres; a relayout from a poll must not.
  useEffect(() => {
    const p = state.selected && !state.lineage ? laid?.layout.pos.get(state.selected) : undefined
    if (p) void flow.setCenter(p.x + CARD.w / 2, p.y + CARD.h / 2, { zoom: flow.getZoom(), duration: 250 })
  }, [state.selected])

  // In a lineage every card is already related, so only hovering dims.
  const focus = hover ?? (state.lineage ? null : state.selected)
  const near = useMemo(() => (focus ? new Set([focus, ...neighbours(ix, focus).map(l => otherEnd(l, focus))]) : null), [ix, focus])
  const t = filter.trim().toLowerCase()

  const nodes = useMemo<RecordNode[]>(() => {
    if (!laid) return []
    return laid.input.nodes.filter(r => laid.layout.pos.has(r.id)).map(r => ({
      id: r.id,
      type: 'record',
      position: laid.layout.pos.get(r.id)!,
      width: CARD.w,
      height: CARD.h,
      draggable: false,
      data: {
        record: ix.byId.get(r.id) ?? r,
        selected: state.selected === r.id,
        fresh: fresh.has(r.id),
        dim: (!!near && !near.has(r.id)) || (!!t && !(r.id.includes(t) || r.text.toLowerCase().includes(t))),
      },
    }))
  }, [laid, ix, state.selected, fresh, near, t])

  const edges = useMemo<RoutedEdge[]>(() => {
    if (!laid) return []
    return laid.input.links.map(l => ({
      id: edgeId(l),
      source: l.to,
      target: l.from,
      type: 'routed',
      markerEnd: marker(l.kind),
      data: { kind: l.kind, points: laid.layout.points.get(edgeId(l)) ?? [], dim: !!focus && l.from !== focus && l.to !== focus },
    }))
  }, [laid, focus])

  return (
    <div ref={box} className="absolute inset-0">
      <ReactFlow
        nodes={nodes} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} colorMode={colorMode}
        nodesConnectable={false} elementsSelectable={false} minZoom={0.15} maxZoom={2.5} panOnScroll
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, n) => onSelect(n.id)}
        onNodeMouseEnter={(_, n) => setHover(n.id)}
        onNodeMouseLeave={() => setHover(null)}
      >
        <Background gap={20} size={1} />
        <Controls showInteractive={false} position="bottom-left" />
        <MiniMap pannable zoomable position="bottom-right" nodeColor={n => `var(--${(n as RecordNode).data.record.kind})`} />
      </ReactFlow>
      <div className="absolute bottom-[136px] left-[15px] z-10 flex flex-col overflow-hidden rounded-md border bg-background shadow-sm">
        {(['RIGHT', 'DOWN'] as const).map(d => (
          <Button
            key={d} variant="ghost" size="icon" className={cn('rounded-none', dir === d && 'bg-muted')}
            title={d === 'RIGHT' ? 'Left to right' : 'Top to bottom'} onClick={() => onDir(d)}
          >
            {d === 'RIGHT' ? <ArrowRight /> : <ArrowDown />}
          </Button>
        ))}
      </div>
      {!state.lineage && <UnlinkedList records={input.unlinked} onSelect={onSelect} />}
      {laid?.sig !== sig && (
        <div className="absolute left-1/2 top-2/5 z-10 -translate-x-1/2 rounded-md border bg-background px-4 py-2.5 text-muted-foreground shadow-md">Laying out…</div>
      )}
    </div>
  )
}
