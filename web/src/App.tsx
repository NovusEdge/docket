import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { DetailPanel } from '@/components/detail-panel'
import { SearchPalette } from '@/components/search-palette'
import { TopBar } from '@/components/top-bar'
import { GraphView } from '@/graph/graph-view'
import { buildIndex, lineageOf, visibleRecords, type DocketRecord, type LedgerIndex } from '@/lib/model'
import { useTheme } from '@/lib/theme'
import { dropMissing, parseState, writeState, type ViewState } from '@/lib/url-state'
import { useLedger } from '@/lib/use-ledger'
import { TimelineView } from '@/timeline/timeline-view'

export interface ViewProps {
  ix: LedgerIndex
  rows: DocketRecord[]
  state: ViewState
  fresh: Set<string>
  filter: string
  onSelect(id: string): void
  onLineage(id: string): void
}

export type ExportFn = (format: 'png' | 'svg') => void

export default function App() {
  const { data, live } = useLedger()
  const [raw, setState] = useState<ViewState>(() => parseState(location.search))
  const [from, setFrom] = useState<ViewState['view']>('timeline')
  const [filter, setFilter] = useState('')
  const [palette, setPalette] = useState(false)
  const [theme, setTheme] = useTheme()
  const [fresh, setFresh] = useState<Set<string>>(new Set())
  const seen = useRef<Set<string> | null>(null)
  const freshTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const exportRef = useRef<ExportFn | null>(null)

  const ix = useMemo(() => buildIndex(data?.records ?? []), [data])
  // Derived during render: a stale ?lineage= or ?selected= must never reach a view.
  const state = data ? dropMissing(raw, ix) : raw
  const rows = useMemo(() => (data ? visibleRecords(data, state.hidden) : []), [data, state.hidden])
  const lineageSize = useMemo(() => (state.lineage ? lineageOf(ix, state.lineage).size : 0), [ix, state.lineage])

  const patch = useCallback((p: Partial<ViewState>) => setState(s => ({ ...s, ...p })), [])
  const query = writeState(state)
  useEffect(() => { history.replaceState(null, '', location.pathname + query) }, [query])

  // A record that appears after the first load gets a short highlight. The
  // timer lives in a ref so a second poll inside 2.5 s cannot cancel the reset.
  useEffect(() => {
    if (!data) return
    const ids = new Set(data.records.map(r => r.id))
    const before = seen.current
    seen.current = ids
    if (!before) return
    const added = [...ids].filter(id => !before.has(id))
    if (!added.length) return
    setFresh(new Set(added))
    clearTimeout(freshTimer.current)
    freshTimer.current = setTimeout(() => setFresh(new Set()), 2500)
  }, [data])
  useEffect(() => () => clearTimeout(freshTimer.current), [])

  const select = useCallback((id: string) => {
    const r = ix.byId.get(id)
    if (!r) return
    setState(s => {
      // Jumping to a record a filter hides turns that filter off.
      const hidden = new Set(s.hidden)
      hidden.delete(r.kind)
      if (r.retired_by) hidden.delete('retired')
      return { ...s, selected: id, hidden }
    })
  }, [ix])
  const openLineage = useCallback((id: string) => {
    setState(s => {
      if (!s.lineage) setFrom(s.view)
      return { ...s, view: 'graph', lineage: id, selected: id }
    })
  }, [])
  const exitLineage = useCallback(() => setState(s => ({ ...s, lineage: null, view: from })), [from])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLInputElement
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPalette(true)
      } else if (e.key === '/' && !typing) {
        e.preventDefault()
        document.getElementById('filter')?.focus()
      } else if (e.key === 'Escape' && !palette) {
        if (state.lineage) exitLineage()
        else patch({ selected: null })
      }
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [state.lineage, palette, exitLineage, patch])

  const props: ViewProps = { ix, rows, state, fresh, filter, onSelect: select, onLineage: openLineage }
  return (
    <div className="flex h-full flex-col">
      <TopBar
        title={data?.title ?? ''} state={state} lineageSize={lineageSize} live={live} count={data?.records.length ?? 0}
        filter={filter} theme={theme} onState={patch} onExitLineage={exitLineage} onFilter={setFilter}
        onSearch={() => setPalette(true)} onTheme={setTheme} onExport={f => exportRef.current?.(f)}
      />
      <main className="flex min-h-0 flex-1">
        <div className="relative min-w-0 flex-1">
          {!data ? <Empty title="Connecting" body="Waiting for docket graph --web." />
            : rows.length === 0 && !state.lineage ? <Empty title="Nothing to show" body="No record matches the filters." />
            : state.view === 'timeline' ? <TimelineView {...props} />
            : <GraphView {...props} exportRef={exportRef} onDir={dir => patch({ dir })} />}
        </div>
        {state.selected && <DetailPanel ix={ix} id={state.selected} onClose={() => patch({ selected: null })} onJump={select} onLineage={openLineage} />}
      </main>
      <SearchPalette open={palette} onOpenChange={setPalette} records={data?.records ?? []} onPick={select} />
    </div>
  )
}

function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="grid h-full place-content-center text-center text-muted-foreground">
      <b className="mb-1 font-medium text-foreground">{title}</b>
      {body}
    </div>
  )
}
