import { CommandDialog, CommandEmpty, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import type { DocketRecord } from '@/lib/model'
import { IdBadge } from './record-bits'

export function SearchPalette({ open, onOpenChange, records, onPick }: {
  open: boolean
  onOpenChange(open: boolean): void
  records: DocketRecord[]
  onPick(id: string): void
}) {
  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="Search by id or text" />
      <CommandList>
        <CommandEmpty>No record matches.</CommandEmpty>
        {records.map(r => (
          <CommandItem key={r.id} value={`${r.id} ${r.text}`} onSelect={() => { onPick(r.id); onOpenChange(false) }}>
            <IdBadge record={r} />
            <span className="truncate">{r.text}</span>
          </CommandItem>
        ))}
      </CommandList>
    </CommandDialog>
  )
}
