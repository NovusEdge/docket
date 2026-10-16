import type { Hidden, Kind, LedgerIndex } from './model'

export interface ViewState {
  view: 'timeline' | 'graph'
  lineage: string | null
  dir: 'RIGHT' | 'DOWN'
  selected: string | null
  hidden: Hidden
}

const HIDEABLE = ['claim', 'decision', 'question', 'retired'] as const
export const DEFAULT_STATE: ViewState = { view: 'timeline', lineage: null, dir: 'RIGHT', selected: null, hidden: new Set(['retired']) }

const sameSet = (a: Set<string>, b: Set<string>) => a.size === b.size && [...a].every(x => b.has(x))

export function parseState(search: string): ViewState {
  const p = new URLSearchParams(search)
  const hide = p.get('hide')
  return {
    view: p.get('view') === 'graph' ? 'graph' : 'timeline',
    lineage: p.get('lineage') || null,
    dir: p.get('dir') === 'DOWN' ? 'DOWN' : 'RIGHT',
    selected: p.get('selected') || null,
    hidden: hide === null
      ? new Set(DEFAULT_STATE.hidden)
      : new Set(hide.split(',').filter((k): k is Kind | 'retired' => (HIDEABLE as readonly string[]).includes(k))),
  }
}

export function writeState(s: ViewState): string {
  const p = new URLSearchParams()
  if (s.view !== 'timeline') p.set('view', s.view)
  if (s.lineage) p.set('lineage', s.lineage)
  if (s.dir !== 'RIGHT') p.set('dir', s.dir)
  if (s.selected) p.set('selected', s.selected)
  if (!sameSet(s.hidden, DEFAULT_STATE.hidden)) p.set('hide', s.hidden.size ? HIDEABLE.filter(k => s.hidden.has(k)).join(',') : 'none')
  const q = p.toString()
  return q ? `?${q}` : ''
}

// A shared link can name a record that a later migration or prune removed.
// Returns s itself when nothing is missing, so callers can skip a re-render.
export function dropMissing(s: ViewState, ix: LedgerIndex): ViewState {
  const lineage = s.lineage && ix.byId.has(s.lineage) ? s.lineage : null
  const selected = s.selected && ix.byId.has(s.selected) ? s.selected : null
  return lineage === s.lineage && selected === s.selected ? s : { ...s, lineage, selected }
}
