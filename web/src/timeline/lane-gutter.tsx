import { memo, type ReactNode } from 'react'
import { laneColor, type LaneLayout } from '@/lib/lanes'
import { branchOf, isRetired, type DocketRecord } from '@/lib/model'
import { LANE_W } from './geometry'

const x = (l: number) => 16 + l * LANE_W + LANE_W / 2
export const gutterWidth = (lanes: LaneLayout) => 16 + lanes.count * LANE_W + 8

export const LaneGutter = memo(function LaneGutter({ rows, lanes, centre, height }: {
  rows: DocketRecord[]
  lanes: LaneLayout
  centre: Map<string, number>
  height: number
}) {
  const paths: ReactNode[] = []
  for (const [b, l] of lanes.lane) {
    const ys = rows.filter(r => branchOf(r) === b).map(r => centre.get(r.id)!)
    const y0 = ys[0]
    const y1 = ys[ys.length - 1]
    // The ledger records no merges, so a branch rejoins main just after its last record.
    const d = l === 0
      ? `M${x(0)} ${y0}V${y1}`
      : `M${x(0)} ${y0 - 22} C ${x(0)} ${y0 - 8}, ${x(l)} ${y0 - 14}, ${x(l)} ${y0} V${y1} C ${x(l)} ${y1 + 14}, ${x(0)} ${y1 + 8}, ${x(0)} ${y1 + 22}`
    paths.push(<path key={b} d={d} fill="none" stroke={laneColor(l)} strokeWidth={2} opacity={l === 0 ? 0.45 : 0.75} />)
  }
  return (
    <svg className="pointer-events-none absolute left-0 top-0 z-[1]" width={gutterWidth(lanes)} height={height}>
      {paths}
      {rows.map(r => {
        const l = lanes.lane.get(branchOf(r))!
        const cy = centre.get(r.id)!
        return isRetired(r)
          ? <circle key={r.id} cx={x(l)} cy={cy} r={4} fill="var(--background)" stroke={laneColor(l)} strokeWidth={1.5} />
          : <circle key={r.id} cx={x(l)} cy={cy} r={r.kind === 'decision' ? 5 : 4} fill={laneColor(l)} stroke="var(--background)" strokeWidth={2} />
      })}
    </svg>
  )
})
