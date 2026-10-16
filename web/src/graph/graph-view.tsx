import type { RefObject } from 'react'
import type { ExportFn, ViewProps } from '@/App'

export function GraphView({ rows }: ViewProps & { exportRef: RefObject<ExportFn | null>; onDir(dir: 'RIGHT' | 'DOWN'): void }) {
  return <div className="p-4">graph of {rows.length} records</div>
}
