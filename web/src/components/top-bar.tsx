import { Download, GitBranch, Monitor, Moon, Network, Search, Sun, Trash2, Waypoints, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import type { Kind } from '@/lib/model'
import type { ThemeChoice } from '@/lib/theme'
import type { ViewState } from '@/lib/url-state'
import { cn } from '@/lib/utils'

const KINDS: { key: Kind | 'retired'; label: string; dot?: string }[] = [
  { key: 'claim', label: 'Claims', dot: 'bg-claim' },
  { key: 'decision', label: 'Decisions', dot: 'bg-decision' },
  { key: 'question', label: 'Questions', dot: 'bg-question' },
  { key: 'retired', label: 'Retired' },
]

export interface TopBarProps {
  title: string
  state: ViewState
  lineageSize: number
  live: boolean
  count: number
  filter: string
  theme: ThemeChoice
  onState(patch: Partial<ViewState>): void
  onExitLineage(): void
  onFilter(text: string): void
  onSearch(): void
  onTheme(t: ThemeChoice): void
  onExport(format: 'png' | 'svg'): void
}

export function TopBar(p: TopBarProps) {
  const toggleKind = (k: Kind | 'retired') => {
    const hidden = new Set(p.state.hidden)
    if (hidden.has(k)) hidden.delete(k)
    else hidden.add(k)
    p.onState({ hidden })
  }
  return (
    <header className="flex h-[52px] shrink-0 items-center gap-3 border-b px-4">
      <div className="flex items-center gap-2 font-semibold">
        <Waypoints className="size-4" />
        docket <span className="font-normal text-muted-foreground">/ {p.title}</span>
      </div>
      <ToggleGroup
        type="single" variant="outline" size="sm" value={p.state.view}
        onValueChange={v => v && p.onState({ view: v as ViewState['view'], lineage: null })}
      >
        <ToggleGroupItem value="timeline" className="gap-1.5 px-3"><GitBranch className="size-4" />Timeline</ToggleGroupItem>
        <ToggleGroupItem value="graph" className="gap-1.5 px-3"><Network className="size-4" />Graph</ToggleGroupItem>
      </ToggleGroup>
      <label className="flex h-8 w-72 items-center gap-2 rounded-md border px-2.5 text-muted-foreground">
        <Search className="size-4" />
        <input
          id="filter" value={p.filter} onChange={e => p.onFilter(e.target.value)} placeholder="Filter records"
          className="min-w-0 flex-1 bg-transparent text-foreground outline-none"
        />
        <button onClick={p.onSearch} className="rounded border bg-muted px-1 font-mono text-[11px]" title="Search all records">⌘K</button>
      </label>
      <div className="flex gap-1">
        {KINDS.map(k => (
          <Button
            key={k.key} variant="outline" size="sm" className={cn('gap-1.5', p.state.hidden.has(k.key) && 'opacity-45')}
            aria-pressed={!p.state.hidden.has(k.key)} onClick={() => toggleKind(k.key)}
          >
            {k.dot ? <span className={cn('size-2 rounded-full', k.dot)} /> : <Trash2 className="size-3.5" />}
            {k.label}
          </Button>
        ))}
      </div>
      {p.state.lineage && (
        <span className="inline-flex h-7 items-center gap-2 rounded-full bg-link/12 pl-3 pr-1 text-xs font-medium text-link">
          Lineage of {p.state.lineage} · {p.lineageSize} records
          <button className="grid size-5 place-items-center rounded-full hover:bg-link/20" title="Show all (Esc)" onClick={p.onExitLineage}>
            <X className="size-3.5" />
          </button>
        </span>
      )}
      <div className="flex-1" />
      <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground" title="Watching .docket/ledger.jsonl">
        <i className={cn('size-1.5 rounded-full', p.live ? 'bg-green-500 ring-3 ring-green-500/20' : 'bg-muted-foreground')} />
        {p.live ? `live · ${p.count} records` : 'disconnected'}
      </span>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" title="Export" disabled={p.state.view !== 'graph'}><Download /></Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => p.onExport('png')}>Export graph as PNG</DropdownMenuItem>
          <DropdownMenuItem onClick={() => p.onExport('svg')}>Export graph as SVG</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" title="Theme">{p.theme === 'dark' ? <Moon /> : p.theme === 'light' ? <Sun /> : <Monitor />}</Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => p.onTheme('light')}><Sun />Light</DropdownMenuItem>
          <DropdownMenuItem onClick={() => p.onTheme('dark')}><Moon />Dark</DropdownMenuItem>
          <DropdownMenuItem onClick={() => p.onTheme('system')}><Monitor />System</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  )
}
