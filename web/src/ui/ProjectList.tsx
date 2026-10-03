import type { Project } from '../data/types'
import { money } from '../measures/registry'
import { TIER_LABEL, themeColor } from '../map/themes'

interface Props {
  title: string
  projects: Project[]
  selectedId: string | null
  onSelect(id: string): void
  isLit?(p: Project): boolean
  limit?: number
  empty: string
}

export default function ProjectList({ title, projects, selectedId, onSelect, isLit, limit = 60, empty }: Props) {
  const shown = [...projects].sort((a, b) => b.budget - a.budget).slice(0, limit)
  return (
    <section className="plist" aria-label={title}>
      <h2>
        {title} <span className="count">{projects.length.toLocaleString()}</span>
      </h2>
      {shown.length === 0 ? (
        <p className="empty">{empty}</p>
      ) : (
        <ol>
          {shown.map((p) => (
            <li key={p.id}>
              <button type="button" className="prow" aria-current={p.id === selectedId} onClick={() => onSelect(p.id)}>
                <span className={`mark tier-${p.tier}`} style={{ '--tint': themeColor(p.theme) } as React.CSSProperties} />
                <span className="prow-title">
                  {p.title}
                  {isLit?.(p) && <span className="lit" title="Budget changed in the latest report">changed</span>}
                </span>
                <span className="prow-meta">
                  {money(p.budget)} · {p.phaseGroup} · {TIER_LABEL[p.tier]}
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
      {projects.length > limit && <p className="more">Showing the {limit} largest. Zoom in or filter to see the rest.</p>}
    </section>
  )
}
