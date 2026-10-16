import { useEffect, useRef, useState } from 'react'
import type { Payload } from './model'

export function useLedger(intervalMs = 2000) {
  const [data, setData] = useState<Payload | null>(null)
  const [live, setLive] = useState(false)
  const etag = useRef<string | null>(null)

  useEffect(() => {
    let stopped = false
    let busy = false
    const poll = async () => {
      if (busy) return
      busy = true
      try {
        const res = await fetch('/api/graph', {
          headers: etag.current ? { 'If-None-Match': etag.current } : {},
          signal: AbortSignal.timeout(5000),
        })
        if (res.status === 200) {
          const body = (await res.json()) as Payload
          if (!stopped) {
            etag.current = res.headers.get('ETag')
            setData(body)
          }
        } else if (res.status !== 304) throw new Error(`HTTP ${res.status}`)
        if (!stopped) setLive(true)
      } catch {
        if (!stopped) setLive(false)
      } finally {
        busy = false
      }
    }
    poll()
    const timer = setInterval(poll, intervalMs)
    return () => {
      stopped = true
      clearInterval(timer)
    }
  }, [intervalMs])

  return { data, live }
}
