import { expect, test } from 'vitest'
import { assignLanes, laneColor } from './lanes'
import type { DocketRecord } from './model'

const row = (id: string, branch: string | null): DocketRecord => ({ id, kind: 'decision', state: 'adopted', text: id, ts: id, branch })

test('main is lane 0 and a finished branch frees its lane', () => {
  const rows = [row('1', 'main'), row('2', 'a'), row('3', 'a'), row('4', 'b'), row('5', 'c'), row('6', 'b'), row('7', 'main')]
  const { lane, count } = assignLanes(rows)
  expect(lane.get('main')).toBe(0)
  expect(lane.get('a')).toBe(1)
  expect(lane.get('b')).toBe(1)
  expect(lane.get('c')).toBe(2)
  expect(count).toBe(3)
})

test('records with no branch sit on main and give one lane', () => {
  const { lane, count } = assignLanes([row('1', null), row('2', ''), row('3', 'main')])
  expect([...lane.keys()]).toEqual(['main'])
  expect(count).toBe(1)
})

test('no rows gives no lanes', () => {
  expect(assignLanes([]).count).toBe(0)
})

test('only main uses the main colour', () => {
  for (let l = 1; l < 20; l++) expect(laneColor(l)).not.toBe(laneColor(0))
})
