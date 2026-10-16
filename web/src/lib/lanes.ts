import { branchOf, type DocketRecord } from './model'

export interface LaneLayout { lane: Map<string, number>; span: Map<string, [number, number]>; count: number }

// Each branch takes the leftmost lane that is free over its active span, as
// git graph renderers do, so finished branches give their lane back.
export function assignLanes(rows: DocketRecord[]): LaneLayout {
  const span = new Map<string, [number, number]>()
  rows.forEach((r, i) => {
    const b = branchOf(r)
    const s = span.get(b)
    if (s) s[1] = i
    else span.set(b, [i, i])
  })
  const order = [...span.keys()].sort((a, b) => (a === 'main' ? -1 : b === 'main' ? 1 : span.get(a)![0] - span.get(b)![0]))
  const lane = new Map<string, number>()
  const busyUntil: number[] = []
  for (const b of order) {
    const [start, end] = span.get(b)!
    let l = b === 'main' ? 0 : 1
    while (busyUntil[l] !== undefined && busyUntil[l] >= start) l++
    lane.set(b, l)
    busyUntil[l] = end
  }
  return { lane, span, count: lane.size ? Math.max(...lane.values()) + 1 : 0 }
}

const BRANCH_COLORS = ['#0ea5e9', '#a855f7', '#f97316', '#10b981', '#ec4899', '#eab308', '#6366f1']
export const laneColor = (l: number) => (l === 0 ? 'var(--lane-0)' : BRANCH_COLORS[(l - 1) % BRANCH_COLORS.length])
