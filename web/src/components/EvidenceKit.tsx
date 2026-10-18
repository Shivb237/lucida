// The building blocks of the Evidence page: one card per research question (title, sample sizes, the answer, what it means), a small visible bar
// comparison on that question's own scale, a few big numbers, and the contents list that follows you down the page. Every number shown comes from
// the logged runs (virtual:evidence); these components only lay it out.
import { useEffect, useState, type ReactNode } from 'react'

export function Card({ id, num, title, meta, answer, means, meansLabel = 'What this means', children }: {
  id: string; num: string; title: string; meta: string[]; answer: ReactNode; means?: ReactNode; meansLabel?: string; children?: ReactNode
}) {
  return (
    <section className="ev-card" id={id} aria-labelledby={`${id}-t`}>
      <div className="ev-head">
        <div className="ev-num mono" aria-hidden="true">{num}</div>
        <div>
          <h2 id={`${id}-t`} className="ev-title">{title}</h2>
          <div className="ev-meta">{meta.map((m) => <span key={m}><i aria-hidden="true" /> {m}</span>)}</div>
        </div>
      </div>
      <div className="ev-body">
        <div className="ev-answer-row">
          <p className="ev-answer">{answer}</p>
          {means && <div className="ev-means"><div className="ev-means-label">{meansLabel}</div><p>{means}</p></div>}
        </div>
        {children}
      </div>
    </section>
  )
}

export type Bar = { name: string; sub?: string; value: number | null | undefined; primary?: boolean }

/** Bars on one question's own scale. The value is always printed next to the bar, so nothing depends on reading lengths or colour. */
export function Bars({ title, scale, rows, max, ticks, unit = '', digits = 3, caption }: {
  title: string; scale: string; rows: Bar[]; max: number; ticks: number[]; unit?: string; digits?: number; caption?: ReactNode
}) {
  return (
    <div className="ev-compare" role="group" aria-label={title}>
      <div className="ev-compare-head"><h3>{title}</h3><span>{scale}</span></div>
      {rows.map((r) => (
        <div key={r.name} className="ev-bar-row">
          <div className="ev-bar-name">{r.name}{r.sub && <small>{r.sub}</small>}</div>
          <div className="ev-bar-track" aria-hidden="true">
            {r.value != null && <div className={`ev-bar-fill${r.primary ? ' primary' : ''}`} style={{ width: `${Math.max(0, Math.min(1, r.value / max)) * 100}%` }} />}
          </div>
          <div className="ev-bar-value mono">{r.value != null ? `${r.value.toFixed(digits)}${unit}` : 'not run'}</div>
        </div>
      ))}
      <div className="ev-axis mono" aria-hidden="true">{ticks.map((t) => <span key={t}>{t}</span>)}</div>
      {caption && <p className="ev-caption">{caption}</p>}
    </div>
  )
}

export function MiniStats({ items }: { items: { value: string; label: string }[] }) {
  return <div className="ev-mini">{items.map((s) => <div key={s.label}><strong className="mono">{s.value}</strong><span>{s.label}</span></div>)}</div>
}

/** The contents list: follows you down the page on a wide screen (a scrolling strip on a phone), marks the section you are reading, and can open
 *  every "exact numbers" panel at once. Buttons, not links: the page's own address uses # for its routes. */
export function Toc({ items }: { items: [string, string][] }) {
  const [active, setActive] = useState(items[0]?.[0] ?? '')
  const [all, setAll] = useState(false)
  useEffect(() => {
    if (!('IntersectionObserver' in window)) return
    const obs = new IntersectionObserver((entries) => {
      const seen = entries.filter((e) => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
      if (seen) setActive(seen.target.id)
    }, { rootMargin: '-15% 0px -65% 0px', threshold: [0, 0.15, 0.4] })
    items.forEach(([id]) => { const el = document.getElementById(id); if (el) obs.observe(el) })
    return () => obs.disconnect()
  }, [items])
  const go = (id: string) => {
    setActive(id)
    const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    document.getElementById(id)?.scrollIntoView({ behavior: calm ? 'auto' : 'smooth', block: 'start' })
  }
  const toggleAll = () => {
    const next = !all
    document.querySelectorAll<HTMLDetailsElement>('main details.exact').forEach((d) => { d.open = next })
    setAll(next)
  }
  return (
    <aside className="ev-toc" aria-label="Evidence sections">
      <div className="ev-toc-h lg">Explore the evidence</div>
      <nav className="ev-toc-list">
        {items.map(([id, label], i) => (
          <button key={id} type="button" className={active === id ? 'active' : ''} aria-current={active === id ? 'true' : undefined} onClick={() => go(id)}>
            <span className="mono">{String(i + 1).padStart(2, '0')}</span><span>{label}</span>
          </button>
        ))}
      </nav>
      <div className="ev-toc-foot">
        Want every table open at once?
        <button type="button" aria-pressed={all} onClick={toggleAll}>{all ? 'Close every detailed section −' : 'Open every detailed section +'}</button>
      </div>
    </aside>
  )
}
