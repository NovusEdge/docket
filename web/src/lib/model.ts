export type Kind = 'claim' | 'decision' | 'question'

export interface DocketRecord {
  id: string
  kind: Kind
  state: string
  text: string
  ts: string
  branch?: string | null
  author?: string | null
  choice?: string | null
  rationale?: string | null
  cost_if_wrong?: string | null
  scope?: string[] | null
  pinned?: boolean
  supersedes?: string[] | null
  answers?: string[] | null
  supports?: string[][] | null
  depends_on?: string[] | null
  retired_by?: string | null
  support?: string | null
  review_owed?: unknown[] | null
}

export interface Payload { records: DocketRecord[]; shown: string[] | null; title: string }

export type LinkKind = 'sup' | 'ans' | 'supp' | 'dep'
/** `from` cites `to`, so `from` is the newer record. */
export interface Link { from: string; to: string; kind: LinkKind }
export interface LedgerIndex { byId: Map<string, DocketRecord>; out: Map<string, Link[]>; in: Map<string, Link[]> }

export const isRetired = (r: DocketRecord) => !!r.retired_by
// Records written before branch provenance existed carry no branch.
export const branchOf = (r: DocketRecord) => r.branch || 'main'
export const dayOf = (r: DocketRecord) => r.ts.slice(0, 10)

export function buildIndex(records: DocketRecord[]): LedgerIndex {
  const byId = new Map(records.map(r => [r.id, r]))
  const out = new Map<string, Link[]>()
  const inc = new Map<string, Link[]>()
  const add = (from: string, to: string, kind: LinkKind) => {
    // A filtered selection or a pruned ledger can cite ids the payload lacks.
    if (!byId.has(to) || from === to) return
    const list = out.get(from) ?? []
    if (list.some(l => l.to === to && l.kind === kind)) return
    const link = { from, to, kind }
    list.push(link)
    out.set(from, list)
    inc.set(to, [...(inc.get(to) ?? []), link])
  }
  for (const r of records) {
    for (const t of r.supersedes ?? []) add(r.id, t, 'sup')
    for (const t of r.answers ?? []) add(r.id, t, 'ans')
    for (const set of r.supports ?? []) for (const t of set) add(r.id, t, 'supp')
    for (const t of r.depends_on ?? []) add(r.id, t, 'dep')
  }
  return { byId, out, in: inc }
}

export const outLinks = (ix: LedgerIndex, id: string) => ix.out.get(id) ?? []
export const inLinks = (ix: LedgerIndex, id: string) => ix.in.get(id) ?? []
export const neighbours = (ix: LedgerIndex, id: string) => [...outLinks(ix, id), ...inLinks(ix, id)]
export const otherEnd = (l: Link, id: string) => (l.from === id ? l.to : l.from)

export type Hidden = Set<Kind | 'retired'>

export function visibleRecords(p: Payload, hidden: Hidden): DocketRecord[] {
  const shown = p.shown ? new Set(p.shown) : null
  return p.records
    .filter(r => (!shown || shown.has(r.id)) && !hidden.has(r.kind) && !(hidden.has('retired') && isRetired(r)))
    .sort((a, b) => a.ts.localeCompare(b.ts) || a.id.localeCompare(b.id))
}

// The record, its supersession chain in both directions, the record's own
// links, and every non-support link of the chain. Support links of other
// chain members are left out: hubs would pull in half the ledger.
export function lineageOf(ix: LedgerIndex, id: string): Set<string> {
  if (!ix.byId.has(id)) return new Set()
  const set = new Set([id])
  const stack = [id]
  while (stack.length) {
    const x = stack.pop()!
    for (const l of neighbours(ix, x)) {
      const y = otherEnd(l, x)
      if (l.kind === 'sup' && !set.has(y)) {
        set.add(y)
        stack.push(y)
      }
    }
  }
  for (const x of [...set]) for (const l of neighbours(ix, x)) if (x === id || l.kind !== 'supp') set.add(otherEnd(l, x))
  return set
}

export type Chip =
  | { kind: 'sup' | 'ans'; dir: 'up' | 'down'; label: string; target: string }
  | { kind: 'count'; label: string; n: number }

export function chipsFor(ix: LedgerIndex, id: string): Chip[] {
  const out = outLinks(ix, id)
  const inc = inLinks(ix, id)
  const chips: Chip[] = []
  for (const l of out) if (l.kind === 'sup') chips.push({ kind: 'sup', dir: 'up', label: `replaces ${l.to}`, target: l.to })
  for (const l of inc) if (l.kind === 'sup') chips.push({ kind: 'sup', dir: 'down', label: `replaced by ${l.from}`, target: l.from })
  for (const l of out) if (l.kind === 'ans') chips.push({ kind: 'ans', dir: 'up', label: `answers ${l.to}`, target: l.to })
  for (const l of inc) if (l.kind === 'ans') chips.push({ kind: 'ans', dir: 'down', label: `answered by ${l.from}`, target: l.from })
  const counts: [Link[], LinkKind, string][] = [
    [out, 'supp', 'supported by'], [out, 'dep', 'depends on'], [inc, 'supp', 'supports'], [inc, 'dep', 'needed by'],
  ]
  for (const [links, kind, label] of counts) {
    const n = links.filter(l => l.kind === kind).length
    if (n) chips.push({ kind: 'count', label: `${label} ${n}`, n })
  }
  return chips
}

export function problemsOf(r: DocketRecord): string[] {
  const p: string[] = []
  if (r.support === 'unsupported') p.push('unsupported')
  if (r.review_owed?.length) p.push('review owed')
  if (r.state === 'disputed') p.push('disputed')
  return p
}
