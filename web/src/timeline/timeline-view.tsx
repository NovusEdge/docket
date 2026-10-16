import type { ViewProps } from '@/App'

export function TimelineView({ rows }: ViewProps) {
  return <div className="p-4">{rows.length} records</div>
}
