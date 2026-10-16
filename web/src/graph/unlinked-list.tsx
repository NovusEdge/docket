import { ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { IdBadge } from '@/components/record-bits'
import type { DocketRecord } from '@/lib/model'
import { cn } from '@/lib/utils'

export function UnlinkedList({ records, onSelect }: { records: DocketRecord[]; onSelect(id: string): void }) {
  const [open, setOpen] = useState(false)
  if (!records.length) return null
  return (
    <div className="absolute right-4 top-4 z-10 max-h-[calc(100%-2rem)] w-72 overflow-auto rounded-[10px] border bg-background py-1 shadow-md">
      <button className="flex w-full items-center gap-2 px-3 py-2 font-medium" onClick={() => setOpen(!open)}>
        <ChevronRight className={cn('size-4 transition-transform', open && 'rotate-90')} />
        Unlinked records
        <span className="ml-auto font-normal text-muted-foreground">{records.length}</span>
      </button>
      {open && records.map(r => (
        <button key={r.id} className="flex w-full items-baseline gap-2 px-3 py-1 text-left hover:bg-muted" onClick={() => onSelect(r.id)}>
          <IdBadge record={r} />
          <span className="truncate text-xs text-muted-foreground">{r.text}</span>
        </button>
      ))}
    </div>
  )
}
