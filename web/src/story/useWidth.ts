import { useEffect, useRef, useState } from 'react'

/** A figure's measured width, so charts and maps draw at the size they are shown. */
export function useWidth(initial = 420): [React.RefObject<HTMLElement | null>, number] {
  const ref = useRef<HTMLElement>(null)
  const [w, setW] = useState(initial)
  useEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver(([e]) => setW(Math.max(260, Math.round(e.contentRect.width))))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  return [ref, w]
}
