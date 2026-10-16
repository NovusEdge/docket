import { GitFork, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { branchOf, inLinks, outLinks, type LedgerIndex, type Link, type LinkKind } from '@/lib/model'
import { IdBadge, ProblemBadges } from './record-bits'

const ends = (links: Link[], kind: LinkKind, end: 'to' | 'from') => links.filter(l => l.kind === kind).map(l => l[end])

export function DetailPanel({ ix, id, onClose, onJump, onLineage }: {
  ix: LedgerIndex
  id: string
  onClose(): void
  onJump(id: string): void
  onLineage(id: string): void
}) {
  const r = ix.byId.get(id)
  if (!r) return null
  const out = outLinks(ix, id)
  const inc = inLinks(ix, id)
  const relations: [string, string[]][] = [
    ['Replaces', ends(out, 'sup', 'to')],
    ['Replaced by', ends(inc, 'sup', 'from')],
    ['Answers', ends(out, 'ans', 'to')],
    ['Answered by', ends(inc, 'ans', 'from')],
    ['Supported by', ends(out, 'supp', 'to')],
    ['Depends on', ends(out, 'dep', 'to')],
    ['Supports', ends(inc, 'supp', 'from')],
    ['Needed by', ends(inc, 'dep', 'from')],
  ]
  const field = (label: string, value?: string | null) => value ? (
    <div className="my-3.5">
      <div className="mb-1 text-xs font-medium text-muted-foreground">{label}</div>
      <p>{value}</p>
    </div>
  ) : null
  return (
    <aside className="flex w-[400px] shrink-0 flex-col border-l">
      <ScrollArea className="min-h-0 flex-1">
        <div className="p-5">
          <div className="flex items-center gap-1.5">
            <IdBadge record={r} />
            <Badge variant="outline">{r.kind}</Badge>
            <Badge variant="outline">{r.state}</Badge>
            <Badge variant="outline" className="font-mono">{branchOf(r)}</Badge>
            <div className="flex-1" />
            <Button variant="ghost" size="icon" onClick={onClose} title="Close (Esc)"><X /></Button>
          </div>
          <h2 className="mb-3.5 mt-2.5 text-base font-semibold leading-snug">{r.text}</h2>
          <div className="flex flex-wrap gap-1.5"><ProblemBadges record={r} /></div>
          <Button variant="outline" size="sm" className="my-2 gap-1.5" onClick={() => onLineage(id)}><GitFork />Show lineage</Button>
          {field('Choice', r.choice)}
          {field('Rationale', r.rationale)}
          {field('Cost if wrong', r.cost_if_wrong)}
          {relations.filter(([, list]) => list.length).map(([label, list]) => (
            <div key={label} className="my-3.5">
              <div className="mb-1 text-xs font-medium text-muted-foreground">{label}</div>
              <div className="flex flex-wrap gap-1.5">
                {list.map(t => (
                  <button key={t} className="rounded-md bg-muted px-1.5 py-px font-mono text-xs hover:ring-1 hover:ring-ring" onClick={() => onJump(t)}>{t}</button>
                ))}
              </div>
            </div>
          ))}
          {r.scope?.length ? (
            <div className="my-3.5">
              <div className="mb-1 text-xs font-medium text-muted-foreground">Scope</div>
              <div className="flex flex-wrap gap-1.5">
                {r.scope.map(s => <span key={s} className="rounded-md bg-muted px-1.5 py-px font-mono text-xs">{s}</span>)}
              </div>
            </div>
          ) : null}
          <div className="mt-4 border-t pt-3 text-xs text-muted-foreground">
            {r.author} · {r.ts.slice(0, 16).replace('T', ' ')} · {branchOf(r)}
          </div>
        </div>
      </ScrollArea>
    </aside>
  )
}
