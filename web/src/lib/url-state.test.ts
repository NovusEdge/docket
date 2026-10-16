import { expect, test } from 'vitest'
import { buildIndex } from './model'
import { DEFAULT_STATE, dropMissing, parseState, writeState } from './url-state'

test('the default state writes an empty query', () => {
  expect(writeState(DEFAULT_STATE)).toBe('')
  expect(parseState('')).toEqual(DEFAULT_STATE)
})

test('a state round-trips through the query string', () => {
  const s = { view: 'graph' as const, lineage: 'd8', dir: 'DOWN' as const, selected: 'd9', hidden: new Set(['claim' as const]) }
  expect(parseState(writeState(s))).toEqual(s)
})

test('showing everything writes hide=none', () => {
  expect(writeState({ ...DEFAULT_STATE, hidden: new Set() })).toBe('?hide=none')
  expect(parseState('?hide=none').hidden).toEqual(new Set())
})

test('unknown values fall back to defaults', () => {
  expect(parseState('?view=radial&dir=UP&hide=bogus,claim')).toEqual({ ...DEFAULT_STATE, hidden: new Set(['claim']) })
})

const ix = buildIndex([{ id: 'd1', kind: 'decision', state: 'adopted', text: '', ts: '' }])

test('ids missing from the ledger are dropped', () => {
  const s = dropMissing({ ...DEFAULT_STATE, view: 'graph', lineage: 'd99', selected: 'd98' }, ix)
  expect(s).toEqual({ ...DEFAULT_STATE, view: 'graph' })
})

test('a state with nothing missing comes back unchanged', () => {
  const s = { ...DEFAULT_STATE, selected: 'd1' }
  expect(dropMissing(s, ix)).toBe(s)
})
