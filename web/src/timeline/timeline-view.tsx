import { ArrowDown, ArrowUp } from 'lucide-react'
import { memo, useEffect, useMemo, useRef, useState } from 'react'
import type { ViewProps } from '@/App'
import { IdBadge, LinkChips, ProblemBadges } from '@/components/record-bits'
import { assignLanes } from '@/lib/lanes'
import { branchOf, isRetired, neighbours, otherEnd, type DocketRecord, type LedgerIndex } from '@/lib/model'
import { cn } from '@/lib/utils'
import { DAY_H, layoutRows, offscreenPills, ROW_H, type Pill } from './geometry'
import { gutterWidth, LaneGutter } from './lane-gutter'

const KIND_LABEL = { sup: 'supersession', ans: 'answer', supp: 'support', dep: 'dependency' } as const
const fmtDay = (d: string) => new Date(`${d}T00:00:00Z`).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' })
const matches = (r: DocketRecord, t: string) => r.id.includes(t) || r.text.toLowerCase().includes(t)

export function TimelineView({ ix, rows, state, fresh, filter, onSelect, onLineage }: ViewProps) {
  const scroller = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<string | null>(null)
  const [view, setView] = useState({ top: 0, bottom: 0 })
  const { items, centre, height } = useMemo(() => layoutRows(rows), [rows])
  const lanes = useMemo(() => assignLanes(rows), [rows])
  const gutter = gutterWidth(lanes)
  const focus = hover ?? state.selected
  const related = useMemo(() => new Set(focus ? neighbours(ix, focus).map(l => otherEnd(l, focus)) : []), [ix, focus])
  const pills = focus ? offscreenPills(ix, focus, centre, view.top + 10, view.bottom - 10) : null
  const t = filter.trim().toLowerCase()
  const centreRef = useRef(centre)
  centreRef.current = centre

  // The viewport only matters for pills, so scrolling re-renders nothing
  // until a row is hovered or selected.
  useEffect(() => {
    const el = scroller.current
    if (!el || !focus) return
    let frame = 0
    const update = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => setView({ top: el.scrollTop, bottom: el.scrollTop + el.clientHeight }))
    }
    update()
    el.addEventListener('scroll', update, { passive: true })
    addEventListener('resize', update)
    return () => {
      cancelAnimationFrame(frame)
      el.removeEventListener('scroll', update)
      removeEventListener('resize', update)
    }
  }, [focus])

  // Only a change of selection scrolls; a poll that rebuilds the layout must
  // leave the reader where they are.
  useEffect(() => {
    const el = scroller.current
    const y = state.selected ? centreRef.current.get(state.selected) : undefined
    if (el && y !== undefined && (y < el.scrollTop + ROW_H || y > el.scrollTop + el.clientHeight - ROW_H)) {
      el.scrollTo({ top: y - el.clientHeight / 2, behavior: 'smooth' })
    }
  }, [state.selected])

  return (
    <div className="absolute inset-0">
      <div ref={scroller} className="absolute inset-0 overflow-auto">
        <div className="relative" style={{ height: height + 60 }}>
          <LaneGutter rows={rows} lanes={lanes} centre={centre} height={height} />
          {items.map(item => item.type === 'day' ? (
            <div
              key={`day-${item.day}`}
              className="absolute inset-x-0 flex items-end border-t bg-background px-4 pb-1.5 text-xs font-semibold text-muted-foreground"
              style={{ top: item.y, height: DAY_H }}
            >
              {fmtDay(item.day)}
              <small className="ml-2 font-normal">· {item.count} records</small>
            </div>
          ) : (
            <Row
              key={item.record.id} ix={ix} record={item.record} y={item.y} gutter={gutter}
              selected={state.selected === item.record.id} related={related.has(item.record.id)}
              fresh={fresh.has(item.record.id)} dim={!!t && !matches(item.record, t)}
              onSelect={onSelect} onLineage={onLineage} onHover={setHover}
            />
          ))}
        </div>
      </div>
      {pills && <Pills list={pills.above} more={pills.moreAbove} up onJump={onSelect} />}
      {pills && <Pills list={pills.below} more={pills.moreBelow} up={false} onJump={onSelect} />}
    </div>
  )
}

const Row = memo(function Row({ ix, record: r, y, gutter, selected, related, fresh, dim, onSelect, onLineage, onHover }: {
  ix: LedgerIndex
  record: DocketRecord
  y: number
  gutter: number
  selected: boolean
  related: boolean
  fresh: boolean
  dim: boolean
  onSelect(id: string): void
  onLineage(id: string): void
  onHover(id: string | null): void
}) {
  return (
    <div
      className={cn(
        'absolute inset-x-0 flex cursor-pointer items-center gap-2 pr-4 transition-opacity hover:bg-muted/50',
        selected && 'bg-link/9 hover:bg-link/9',
        related && 'bg-link/4',
        fresh && 'ring-2 ring-inset ring-link',
        dim && 'opacity-35',
      )}
      style={{ top: y, height: ROW_H, paddingLeft: gutter }}
      onClick={() => onSelect(r.id)}
      onMouseEnter={() => onHover(r.id)}
      onMouseLeave={() => onHover(null)}
    >
      <span className="w-10 shrink-0 font-mono text-[11px] text-muted-foreground">{r.ts.slice(11, 16)}</span>
      <IdBadge record={r} />
      <span className={cn('min-w-0 truncate', isRetired(r) && 'text-muted-foreground line-through')}>{r.text}</span>
      {branchOf(r) !== 'main' && <span className="shrink-0 rounded-full border px-1.5 font-mono text-[11px] text-muted-foreground">{branchOf(r)}</span>}
      <LinkChips ix={ix} id={r.id} onJump={onSelect} onLineage={onLineage} />
      <ProblemBadges record={r} />
    </div>
  )
})

function Pills({ list, more, up, onJump }: { list: Pill[]; more: number; up: boolean; onJump(id: string): void }) {
  if (!list.length) return null
  const Arrow = up ? ArrowUp : ArrowDown
  return (
    <div className={cn('pointer-events-none absolute left-1/2 z-10 flex -translate-x-1/2 gap-1.5', up ? 'top-2.5' : 'bottom-2.5')}>
      {list.map(p => (
        <button
          key={p.id} onClick={() => onJump(p.id)}
          className="pointer-events-auto inline-flex h-7 items-center gap-1.5 rounded-full border bg-background px-2.5 text-xs text-muted-foreground shadow-md hover:border-ring hover:text-foreground"
        >
          <Arrow className="size-3" />
          <b className="font-mono font-medium">{p.id}</b>
          {KIND_LABEL[p.kind]} · {p.rows} rows
        </button>
      ))}
      {more > 0 && <span className="inline-flex h-7 items-center rounded-full border bg-background px-2.5 text-xs text-muted-foreground shadow-md">+{more} more</span>}
    </div>
  )
}
