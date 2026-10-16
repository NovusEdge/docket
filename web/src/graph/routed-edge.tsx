import { MarkerType, type Edge, type EdgeMarker, type EdgeProps } from '@xyflow/react'
import { memo } from 'react'
import type { LinkKind } from '@/lib/model'
import { roundedPath } from './elk-input'
import type { Point } from './elk-layout'

export type RoutedEdge = Edge<{ kind: LinkKind; points: Point[]; dim: boolean }, 'routed'>

export const EDGE_STYLE: Record<LinkKind, { stroke: string; width: number; dash?: string }> = {
  sup: { stroke: 'var(--link)', width: 1.7 },
  ans: { stroke: 'var(--question)', width: 1.7, dash: '5 4' },
  supp: { stroke: 'var(--muted-foreground)', width: 1.2 },
  dep: { stroke: 'var(--muted-foreground)', width: 1.2, dash: '2 3' },
}

// React Flow draws these markers inside its viewport, so PNG and SVG export keep the arrowheads.
export const marker = (kind: LinkKind): EdgeMarker => ({ type: MarkerType.ArrowClosed, color: EDGE_STYLE[kind].stroke, width: 16, height: 16 })

// Drawn from ELK's bend points, not React Flow's handle coordinates, so the
// orthogonal routing ELK computed survives.
export const RoutedEdgeView = memo(function RoutedEdgeView({ id, data, markerEnd }: EdgeProps<RoutedEdge>) {
  if (!data || data.points.length < 2) return null
  const s = EDGE_STYLE[data.kind]
  return (
    <path
      id={id} d={roundedPath(data.points)} fill="none" stroke={s.stroke} strokeWidth={s.width} strokeDasharray={s.dash}
      markerEnd={markerEnd} opacity={data.dim ? 0.15 : 1} className="transition-opacity"
    />
  )
})
