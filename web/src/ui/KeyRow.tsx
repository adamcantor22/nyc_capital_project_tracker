import KeyButton from './KeyButton'

interface Props {
  label: string
  swatch: React.ReactNode
  num: string
  pressed: boolean | 'mixed'
  disabled?: boolean
  /** Rows with children (a theme's subthemes) get a disclosure button. */
  expanded?: boolean
  onExpand?(): void
  indent?: boolean
  title?: string
  onPick(add: boolean): void
  onHover?(on: boolean): void
}

/** One legend row: the key itself (tap = only this, hold = add) and a ＋ button that adds it. */
export default function KeyRow({ label, swatch, num, pressed, disabled, indent, title, expanded, onExpand, onPick, onHover }: Props) {
  return (
    <div className={`key-row${indent ? ' indent' : ''}${expanded !== undefined ? ' has-kids' : ''}`}
      onMouseEnter={() => onHover?.(true)} onMouseLeave={() => onHover?.(false)}>
      <KeyButton className="key" aria-pressed={pressed} disabled={disabled} title={title} onPick={onPick}
        onFocus={() => onHover?.(true)} onBlur={() => onHover?.(false)}>
        {swatch}
        <span className="key-label">{label}</span>
        <span className="key-num">{num}</span>
      </KeyButton>
      {expanded !== undefined && (
        <button type="button" className="expand" aria-expanded={expanded} onClick={onExpand}
          aria-label={`${expanded ? 'Hide' : 'Show'} ${label} subthemes`} title={expanded ? 'Hide subthemes' : 'Show subthemes'}>
          <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><path d="M3 4.5l3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </button>
      )}
      <button type="button" className="add" disabled={disabled} onClick={() => onPick(true)}
        aria-label={pressed === true ? `Remove ${label} from the selection` : `Add ${label} to the selection`}
        title={pressed === true ? 'Remove from selection' : 'Add to selection'}>
        <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
          {pressed === true ? <path d="M2.5 6h7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            : <path d="M6 2.5v7M2.5 6h7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />}
        </svg>
      </button>
    </div>
  )
}
