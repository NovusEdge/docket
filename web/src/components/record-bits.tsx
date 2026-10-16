import { ArrowDown, ArrowUp } from 'lucide-react'
import { chipsFor, isRetired, problemsOf, type DocketRecord, type LedgerIndex } from '@/lib/model'
import { cn } from '@/lib/utils'

const KIND_BADGE = {
  claim: 'text-claim bg-claim-bg',
  decision: 'text-decision bg-decision-bg',
  question: 'text-question bg-question-bg',
} as const

export function IdBadge({ record, className }: { record: DocketRecord; className?: string }) {
  return (
    <span className={cn('shrink-0 rounded-[5px] px-1.5 py-px font-mono text-xs font-medium', KIND_BADGE[record.kind], isRetired(record) && 'opacity-55', className)}>
      {record.id}
    </span>
  )
}

export function ProblemBadges({ record }: { record: DocketRecord }) {
  return problemsOf(record).map(p => (
    <span key={p} className="shrink-0 whitespace-nowrap rounded-full border border-destructive/35 px-1.5 text-[11px] text-destructive">{p}</span>
  ))
}

const CHIP = 'inline-flex shrink-0 cursor-pointer items-center gap-1 whitespace-nowrap rounded-md border border-transparent px-1.5 py-px font-mono text-[11px] hover:border-ring'

export function LinkChips({ ix, id, onJump, onLineage }: { ix: LedgerIndex; id: string; onJump(id: string): void; onLineage(id: string): void }) {
  return chipsFor(ix, id).map(c => {
    if (c.kind === 'count') {
      return (
        <button key={c.label} className={cn(CHIP, 'bg-muted text-muted-foreground')} onClick={e => { e.stopPropagation(); onLineage(id) }}>
          {c.label}
        </button>
      )
    }
    const Arrow = c.dir === 'up' ? ArrowUp : ArrowDown
    return (
      <button key={c.label} className={cn(CHIP, c.kind === 'sup' ? 'bg-link/10 text-link' : 'bg-question-bg text-question')} onClick={e => { e.stopPropagation(); onJump(c.target) }}>
        <Arrow className="size-3" />
        {c.label}
      </button>
    )
  })
}
