import { expect, test } from 'vitest'
import { buildIndex, type DocketRecord } from '@/lib/model'
import { edgeId, graphInput, largestComponent, roundedPath, signature, toElk } from './elk-input'

const rec = (id: string, extra: Partial<DocketRecord> = {}): DocketRecord => ({ id, kind: 'decision', state: 'adopted', text: id, ts: id, ...extra })
const records = [
  rec('d1', { retired_by: 'd2' }), rec('d2', { supersedes: ['d1'] }), rec('d3', { supports: [['d2']] }),
  rec('d4'), rec('d5'), rec('d6', { supports: [['d5']] }),
]
const ix = buildIndex(records)
const rows = records.filter(r => !r.retired_by)

test('linked records become nodes, retired ones join when linked, the rest are unlinked', () => {
  const g = graphInput(ix, rows, null)
  expect(g.nodes.map(r => r.id)).toEqual(['d1', 'd2', 'd3', 'd5', 'd6'])
  expect(g.unlinked.map(r => r.id)).toEqual(['d4'])
  expect(g.links.map(edgeId)).toEqual(['d1>d2>sup', 'd2>d3>supp', 'd5>d6>supp'])
})

test('a lineage restricts the graph and has no unlinked list', () => {
  const g = graphInput(ix, rows, 'd2')
  expect(g.nodes.map(r => r.id)).toEqual(['d1', 'd2', 'd3'])
  expect(g.unlinked).toEqual([])
})

test('a lineage of an unknown id is empty', () => {
  expect(graphInput(ix, rows, 'd99')).toEqual({ nodes: [], links: [], unlinked: [] })
})

test('ELK edges run from the cited record to the citing one', () => {
  const elk = toElk(graphInput(ix, rows, null), 'DOWN')
  expect(elk.layoutOptions!['elk.direction']).toBe('DOWN')
  expect(elk.edges![0]).toEqual({ id: 'd1>d2>sup', sources: ['d1'], targets: ['d2'] })
  expect(elk.children![0]).toEqual({ id: 'd1', width: 260, height: 76 })
})

test('the largest component wins', () => {
  expect([...largestComponent(graphInput(ix, rows, null))].sort()).toEqual(['d1', 'd2', 'd3'])
})

test('the signature changes with nodes, links and direction only', () => {
  const a = graphInput(ix, rows, null)
  const edited = buildIndex(records.map(r => ({ ...r, text: 'edited' })))
  expect(signature(a, 'RIGHT')).toBe(signature(graphInput(edited, rows, null), 'RIGHT'))
  expect(signature(a, 'RIGHT')).not.toBe(signature(a, 'DOWN'))
})

test('rounded paths keep straight segments and round each bend', () => {
  expect(roundedPath([{ x: 0, y: 0 }, { x: 100, y: 0 }])).toBe('M0 0 L100 0')
  expect(roundedPath([{ x: 0, y: 0 }, { x: 50, y: 0 }, { x: 50, y: 40 }])).toBe('M0 0 L42 0 Q50 0 50 8 L50 40')
})

test('an empty graph is empty', () => {
  const g = graphInput(buildIndex([]), [], null)
  expect(g).toEqual({ nodes: [], links: [], unlinked: [] })
  expect(largestComponent(g).size).toBe(0)
})
