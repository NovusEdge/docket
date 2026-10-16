import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import { memo } from 'react'
import { IdBadge, ProblemBadges } from '@/components/record-bits'
import { isRetired, type DocketRecord } from '@/lib/model'
import { cn } from '@/lib/utils'
import { CARD } from './elk-input'

export type RecordNode = Node<{ record: DocketRecord; dim: boolean; selected: boolean; fresh: boolean }, 'record'>

const BORDER = { claim: 'border-l-claim', decision: 'border-l-decision', question: 'border-l-question' } as const

export const RecordNodeView = memo(function RecordNodeView({ data }: NodeProps<RecordNode>) {
  const r = data.record
  return (
    <div
      className={cn(
        'flex cursor-pointer flex-col gap-1 rounded-[10px] border border-l-[3px] bg-card px-2.5 py-2 shadow-sm transition-opacity hover:border-ring',
        BORDER[r.kind],
        isRetired(r) && 'bg-muted/50',
        data.dim && 'opacity-15',
        data.selected && 'border-link ring-3 ring-link/20',
        data.fresh && 'ring-3 ring-link',
      )}
      style={{ width: CARD.w, height: CARD.h }}
    >
      {/* React Flow drops edges between nodes that have no handles; these stay invisible. */}
      <Handle type="target" position={Position.Left} className="!opacity-0" isConnectable={false} />
      <Handle type="source" position={Position.Right} className="!opacity-0" isConnectable={false} />
      <div className="flex items-center gap-1.5">
        <IdBadge record={r} />
        <span className="font-mono text-[11px] text-muted-foreground">{r.ts.slice(5, 10)}</span>
        <div className="flex-1" />
        <ProblemBadges record={r} />
      </div>
      <div className={cn('line-clamp-2 text-[12.5px] leading-snug', isRetired(r) && 'text-muted-foreground line-through')}>{r.text}</div>
    </div>
  )
})
