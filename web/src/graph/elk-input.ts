import type { ElkNode } from 'elkjs/lib/elk-api'
import { inLinks, isRetired, lineageOf, otherEnd, outLinks, type DocketRecord, type LedgerIndex, type Link } from '@/lib/model'

export const CARD = { w: 260, h: 76 }
export interface GraphInput { nodes: DocketRecord[]; links: Link[]; unlinked: DocketRecord[] }

const byTime = (a: DocketRecord, b: DocketRecord) => a.ts.localeCompare(b.ts) || a.id.localeCompare(b.id)
export const edgeId = (l: Link) => `${l.to}>${l.from}>${l.kind}`

// Retired records join when something visible links them, so a supersession
// chain reads whole even while the Retired filter hides them elsewhere.
export function graphInput(ix: LedgerIndex, rows: DocketRecord[], lineage: string | null): GraphInput {
  const ids = lineage ? lineageOf(ix, lineage) : new Set(rows.map(r => r.id))
  if (!lineage) {
    for (const r of rows) {
      for (const l of [...outLinks(ix, r.id), ...inLinks(ix, r.id)]) {
        const other = otherEnd(l, r.id)
        if (isRetired(ix.byId.get(other)!)) ids.add(other)
      }
    }
  }
  const links: Link[] = []
  for (const id of ids) for (const l of outLinks(ix, id)) if (ids.has(l.to)) links.push(l)
  links.sort((a, b) => edgeId(a).localeCompare(edgeId(b)))
  const linked = new Set(links.flatMap(l => [l.from, l.to]))
  const records = [...ids].map(id => ix.byId.get(id)!).sort(byTime)
  return {
    nodes: lineage ? records : records.filter(r => linked.has(r.id)),
    links,
    unlinked: lineage ? [] : records.filter(r => !linked.has(r.id) && !isRetired(r)),
  }
}

export function toElk(input: GraphInput, dir: 'RIGHT' | 'DOWN'): ElkNode {
  return {
    id: 'root',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': dir,
      'elk.edgeRouting': 'ORTHOGONAL',
      'elk.layered.spacing.nodeNodeBetweenLayers': '56',
      'elk.spacing.nodeNode': '18',
      'elk.spacing.edgeNode': '14',
      'elk.spacing.edgeEdge': '8',
      'elk.separateConnectedComponents': 'true',
      'elk.spacing.componentComponent': '48',
      'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
      // Children arrive oldest first; keeping that order puts earlier records first within a layer.
      'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
    },
    children: input.nodes.map(r => ({ id: r.id, width: CARD.w, height: CARD.h })),
    edges: input.links.map(l => ({ id: edgeId(l), sources: [l.to], targets: [l.from] })),
  }
}

export function largestComponent(input: GraphInput): Set<string> {
  const parent = new Map(input.nodes.map(r => [r.id, r.id]))
  const find = (x: string): string => {
    const p = parent.get(x)!
    if (p === x) return x
    const root = find(p)
    parent.set(x, root)
    return root
  }
  for (const l of input.links) parent.set(find(l.from), find(l.to))
  const groups = new Map<string, string[]>()
  for (const id of parent.keys()) groups.set(find(id), [...(groups.get(find(id)) ?? []), id])
  let best: string[] = []
  for (const g of groups.values()) if (g.length > best.length) best = g
  return new Set(best)
}

export const signature = (input: GraphInput, dir: string) =>
  [dir, input.nodes.map(r => r.id).join(','), input.links.map(edgeId).join(',')].join('|')

export function roundedPath(points: { x: number; y: number }[], radius = 8): string {
  let d = `M${points[0].x} ${points[0].y}`
  for (let i = 1; i < points.length - 1; i++) {
    const a = points[i - 1]
    const b = points[i]
    const c = points[i + 1]
    const r = Math.min(radius, Math.hypot(b.x - a.x, b.y - a.y) / 2, Math.hypot(c.x - b.x, c.y - b.y) / 2)
    const ux = Math.sign(b.x - a.x), uy = Math.sign(b.y - a.y), vx = Math.sign(c.x - b.x), vy = Math.sign(c.y - b.y)
    d += ` L${b.x - ux * r} ${b.y - uy * r} Q${b.x} ${b.y} ${b.x + vx * r} ${b.y + vy * r}`
  }
  const end = points[points.length - 1]
  return `${d} L${end.x} ${end.y}`
}
