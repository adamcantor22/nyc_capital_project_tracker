import KeyButton from './KeyButton'

interface Props {
  label: string
  swatch: React.ReactNode
  num: string
  pressed: boolean
  disabled?: boolean
  indent?: boolean
  title?: string
  onPick(add: boolean): void
  onHover?(on: boolean): void
}

/** One legend row: the key itself (tap = only this, hold = add) and a ＋ button that adds it. */
export default function KeyRow({ label, swatch, num, pressed, disabled, indent, title, onPick, onHover }: Props) {
  return (
    <div className={`key-row${indent ? ' indent' : ''}`}
      onMouseEnter={() => onHover?.(true)} onMouseLeave={() => onHover?.(false)}>
      <KeyButton className="key" aria-pressed={pressed} disabled={disabled} title={title} onPick={onPick}
        onFocus={() => onHover?.(true)} onBlur={() => onHover?.(false)}>
        {swatch}
        <span className="key-label">{label}</span>
        <span className="key-num">{num}</span>
      </KeyButton>
      <button type="button" className="add" disabled={disabled} onClick={() => onPick(true)}
        aria-label={pressed ? `Remove ${label} from the selection` : `Add ${label} to the selection`}
        title={pressed ? 'Remove from selection' : 'Add to selection'}>
        <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
          {pressed ? <path d="M2.5 6h7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            : <path d="M6 2.5v7M2.5 6h7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />}
        </svg>
      </button>
    </div>
  )
}
