import { dayOf, neighbours, otherEnd, type DocketRecord, type LedgerIndex, type LinkKind } from '@/lib/model'

export const ROW_H = 38
export const DAY_H = 32
export const LANE_W = 18
const MAX_PILLS = 4

export type Item = { type: 'day'; day: string; count: number; y: number } | { type: 'row'; record: DocketRecord; y: number }

export function layoutRows(rows: DocketRecord[]) {
  const counts = new Map<string, number>()
  for (const r of rows) counts.set(dayOf(r), (counts.get(dayOf(r)) ?? 0) + 1)
  const items: Item[] = []
  const centre = new Map<string, number>()
  let y = 0
  let last: string | null = null
  for (const r of rows) {
    if (dayOf(r) !== last) {
      last = dayOf(r)
      items.push({ type: 'day', day: last, count: counts.get(last)!, y })
      y += DAY_H
    }
    items.push({ type: 'row', record: r, y })
    centre.set(r.id, y + ROW_H / 2)
    y += ROW_H
  }
  return { items, centre, height: y }
}

export interface Pill { id: string; kind: LinkKind; rows: number }

// Linked rows outside [top, bottom], nearest first, for the pills pinned to
// the viewport edges.
export function offscreenPills(ix: LedgerIndex, id: string, centre: Map<string, number>, top: number, bottom: number) {
  const from = centre.get(id)
  const above: Pill[] = []
  const below: Pill[] = []
  const seen = new Set<string>()
  for (const l of neighbours(ix, id)) {
    const other = otherEnd(l, id)
    const y = centre.get(other)
    if (from === undefined || y === undefined || seen.has(other)) continue
    seen.add(other)
    const pill = { id: other, kind: l.kind, rows: Math.round(Math.abs(y - from) / ROW_H) }
    if (y < top) above.push(pill)
    else if (y > bottom) below.push(pill)
  }
  above.sort((a, b) => a.rows - b.rows)
  below.sort((a, b) => a.rows - b.rows)
  return {
    above: above.slice(0, MAX_PILLS),
    below: below.slice(0, MAX_PILLS),
    moreAbove: Math.max(0, above.length - MAX_PILLS),
    moreBelow: Math.max(0, below.length - MAX_PILLS),
  }
}
