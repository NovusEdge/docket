import { expect, test } from 'vitest'
import { buildIndex, type DocketRecord } from '@/lib/model'
import { DAY_H, layoutRows, offscreenPills, ROW_H } from './geometry'

const rec = (id: string, ts: string, extra: Partial<DocketRecord> = {}): DocketRecord => ({ id, kind: 'decision', state: 'adopted', text: id, ts, ...extra })

test('a day header precedes each day and rows stack under it', () => {
  const { items, centre, height } = layoutRows([rec('d1', '2026-09-06T10:00'), rec('d2', '2026-09-06T11:00'), rec('d3', '2026-09-07T09:00')])
  expect(items.map(i => i.type)).toEqual(['day', 'row', 'row', 'day', 'row'])
  expect(items[0]).toEqual({ type: 'day', day: '2026-09-06', count: 2, y: 0 })
  expect(centre.get('d1')).toBe(DAY_H + ROW_H / 2)
  expect(centre.get('d3')).toBe(2 * DAY_H + 2 * ROW_H + ROW_H / 2)
  expect(height).toBe(2 * DAY_H + 3 * ROW_H)
})

test('no rows lay out to nothing', () => {
  expect(layoutRows([])).toEqual({ items: [], centre: new Map(), height: 0 })
})

test('linked rows out of view split above and below, capped at four', () => {
  const records = [rec('d0', '2026-09-01T00:00')]
  for (let i = 1; i <= 7; i++) records.push(rec(`d${i}`, `2026-09-01T0${i}:00`, { supports: [['d0']] }))
  const ix = buildIndex(records)
  const centre = new Map(records.map((r, i) => [r.id, i * ROW_H + ROW_H / 2]))
  const { above, below, moreAbove, moreBelow } = offscreenPills(ix, 'd0', centre, ROW_H, ROW_H * 2)
  expect(above).toEqual([])
  expect(below.map(p => p.id)).toEqual(['d2', 'd3', 'd4', 'd5'])
  expect(below[0]).toEqual({ id: 'd2', kind: 'supp', rows: 2 })
  expect(moreBelow).toBe(2)
  expect(moreAbove).toBe(0)
})

test('links to rows that are not laid out make no pill', () => {
  const ix = buildIndex([rec('d1', 'a'), rec('d2', 'b', { supersedes: ['d1'] })])
  expect(offscreenPills(ix, 'd2', new Map([['d2', 19]]), 0, 100).below).toEqual([])
})
