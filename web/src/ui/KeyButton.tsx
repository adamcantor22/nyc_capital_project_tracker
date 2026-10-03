import { useRef } from 'react'

const HOLD_MS = 450

interface Props extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'onClick'> {
  /** add: long-press, Shift-click or Ctrl/Cmd-click (add to the selection instead of showing only this). */
  onPick(add: boolean): void
}

/** A legend key: tap shows only this, hold or modifier-click adds it. Keyboard: Enter solos, Shift+Enter adds. */
export default function KeyButton({ onPick, children, ...rest }: Props) {
  const timer = useRef<number | null>(null)
  const held = useRef(false)
  const clear = () => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = null
  }
  return (
    <button
      type="button"
      {...rest}
      onPointerDown={() => {
        held.current = false
        clear()
        timer.current = window.setTimeout(() => {
          held.current = true
          navigator.vibrate?.(15)
          onPick(true)
        }, HOLD_MS)
      }}
      onPointerUp={clear}
      onPointerLeave={clear}
      onPointerCancel={clear}
      onContextMenu={(e) => e.preventDefault()}
      onClick={(e) => {
        if (held.current) {
          held.current = false
          return
        }
        onPick(e.shiftKey || e.ctrlKey || e.metaKey)
      }}
    >
      {children}
    </button>
  )
}
