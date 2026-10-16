import ELK from 'elkjs/lib/elk-api'
import workerUrl from 'elkjs/lib/elk-worker.min.js?url'
import { toElk, type GraphInput } from './elk-input'

export interface Point { x: number; y: number }
export interface Layout {
  pos: Map<string, Point>
  points: Map<string, Point[]>
  width: number
  height: number
}

let elk: InstanceType<typeof ELK> | null = null

export async function runLayout(input: GraphInput, dir: 'RIGHT' | 'DOWN'): Promise<Layout> {
  // ELK runs in a worker so a large ledger never blocks scrolling or input.
  elk ??= new ELK({ workerUrl })
  const g = await elk.layout(toElk(input, dir))
  const pos = new Map((g.children ?? []).map(n => [n.id, { x: n.x ?? 0, y: n.y ?? 0 }]))
  const points = new Map<string, Point[]>()
  for (const e of g.edges ?? []) {
    const s = e.sections?.[0]
    if (s) points.set(e.id, [s.startPoint, ...(s.bendPoints ?? []), s.endPoint])
  }
  return { pos, points, width: g.width ?? 0, height: g.height ?? 0 }
}
