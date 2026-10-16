import { toPng, toSvg } from 'html-to-image'
import type { Layout } from './elk-layout'

const PAD = 24

// Renders the React Flow viewport at a transform that frames the whole
// layout, not just the part on screen, as the React Flow docs recommend.
export async function exportGraph(format: 'png' | 'svg', layout: Layout) {
  const viewport = document.querySelector<HTMLElement>('.react-flow__viewport')
  if (!viewport) return
  const width = layout.width + PAD * 2
  const height = layout.height + PAD * 2
  const options = {
    backgroundColor: getComputedStyle(document.body).backgroundColor,
    width,
    height,
    style: { width: `${width}px`, height: `${height}px`, transform: `translate(${PAD}px, ${PAD}px) scale(1)` },
    pixelRatio: 2,
  }
  const url = format === 'png' ? await toPng(viewport, options) : await toSvg(viewport, options)
  const a = document.createElement('a')
  a.href = url
  a.download = `docket-graph.${format}`
  a.click()
}
