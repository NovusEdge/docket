import { describe, expect, test } from 'vitest'
import { buildIndex, chipsFor, inLinks, lineageOf, outLinks, problemsOf, visibleRecords, type DocketRecord } from './model'

const rec = (id: string, extra: Partial<DocketRecord> = {}): DocketRecord => ({
  id, kind: id.startsWith('c') ? 'claim' : id.startsWith('q') ? 'question' : 'decision',
  state: 'adopted', text: id, ts: `2026-09-0${id.length}T10:00:00+00:00`, branch: 'main', ...extra,
})

describe('buildIndex', () => {
  test('indexes every relation both ways and dedupes support across OR sets', () => {
    const ix = buildIndex([
      rec('c1'), rec('c2'), rec('q1'), rec('d1'),
      rec('d2', { supersedes: ['d1'], answers: ['q1'], supports: [['c1', 'c2'], ['c1']], depends_on: ['d1'] }),
    ])
    expect(outLinks(ix, 'd2').map(l => `${l.kind}:${l.to}`)).toEqual(['sup:d1', 'ans:q1', 'supp:c1', 'supp:c2', 'dep:d1'])
    expect(inLinks(ix, 'c1')).toEqual([{ from: 'd2', to: 'c1', kind: 'supp' }])
  })

  test('drops links to ids that are not in the payload', () => {
    const ix = buildIndex([rec('d2', { supersedes: ['d1'], supports: [['c9']] })])
    expect(outLinks(ix, 'd2')).toEqual([])
  })
})

describe('visibleRecords', () => {
  const records = [rec('d1', { retired_by: 'd2' }), rec('d2', { ts: '2026-09-09T00:00:00+00:00' }), rec('c1', { ts: '2026-09-01T00:00:00+00:00' })]
  test('hides retired records when asked and sorts oldest first', () => {
    expect(visibleRecords({ records, shown: null, title: '' }, new Set(['retired'])).map(r => r.id)).toEqual(['c1', 'd2'])
  })
  test('restricts to shown ids when the server filtered', () => {
    expect(visibleRecords({ records, shown: ['d2'], title: '' }, new Set()).map(r => r.id)).toEqual(['d2'])
  })
  test('an empty ledger gives no rows', () => {
    expect(visibleRecords({ records: [], shown: null, title: '' }, new Set())).toEqual([])
  })
})

describe('lineageOf', () => {
  test("follows the whole supersession chain both ways and the record's direct links", () => {
    const ix = buildIndex([
      rec('c1'), rec('c2'), rec('q1'),
      rec('d1', { supports: [['c1']] }),
      rec('d2', { supersedes: ['d1'], answers: ['q1'] }),
      rec('d3', { supersedes: ['d2'], supports: [['c2']] }),
      rec('d4', { supports: [['d2']] }),
      rec('d5'),
    ])
    expect([...lineageOf(ix, 'd2')].sort()).toEqual(['d1', 'd2', 'd3', 'd4', 'q1'])
  })

  test('an unknown id has an empty lineage', () => {
    expect(lineageOf(buildIndex([rec('d1')]), 'd99').size).toBe(0)
  })
})

describe('chipsFor', () => {
  test('names supersede and answer targets and counts the rest', () => {
    const ix = buildIndex([
      rec('c1'), rec('q1'), rec('d1'),
      rec('d2', { supersedes: ['d1'], answers: ['q1'], supports: [['c1']] }),
      rec('d3', { supersedes: ['d2'], depends_on: ['d2'] }),
    ])
    expect(chipsFor(ix, 'd2')).toEqual([
      { kind: 'sup', dir: 'up', label: 'replaces d1', target: 'd1' },
      { kind: 'sup', dir: 'down', label: 'replaced by d3', target: 'd3' },
      { kind: 'ans', dir: 'up', label: 'answers q1', target: 'q1' },
      { kind: 'count', label: 'supported by 1', n: 1 },
      { kind: 'count', label: 'needed by 1', n: 1 },
    ])
  })
})

test('problemsOf names unsupported, owed review and disputed', () => {
  expect(problemsOf(rec('c1', { support: 'unsupported', review_owed: [{}], state: 'disputed' }))).toEqual(['unsupported', 'review owed', 'disputed'])
  expect(problemsOf(rec('c2'))).toEqual([])
})
