// The building blocks of the Evidence page: the claim card (question, computed verdict, chart with its 95% ranges, how it was measured,
// limits, sources, and the exact numbers folded below), the verdict marks, the one legend and the contents list. Every number shown comes
// from the logged runs (virtual:evidence); these components only lay it out.
import { useEffect, useState, type ReactNode } from 'react'
import type { Claim, EScale, Effect, Level, Table, Verdict } from 'virtual:evidence'
import { Exact } from './Plain'
import { Axis, Interval, fmt, niceDomain, niceStep, ticksFor, type Domain } from './Interval'
import { Term } from './Term'

export const REPO = 'https://github.com/Shivb237/lucida'
export const blob = (file: string) => `${REPO}/blob/main/${file}`

// ---- marks and words ---------------------------------------------------------------------------------------------------------------------
const MARK: Record<Verdict, string> = { helped: 'solid', 'no clear effect': 'hatch', hurt: 'cross' }
export const VERDICT_WORD: Record<Verdict, string> = { helped: 'helped', 'no clear effect': 'no clear effect', hurt: 'hurt' }
/** The density mark for a verdict: solid helped, hatched no clear effect, cross-hatched hurt, dotted not computed yet. Always shown with a word. */
export function VerdictMark({ verdict }: { verdict: Verdict | null }) {
  return <i className={`evd-mark ${verdict ? MARK[verdict] : 'dotted'}`} aria-hidden="true" />
}

// ---- prose: numbers in mono, and the first use of a technical word opens its definition ------------------------------------------------
const TERMS: [RegExp, string][] = [[/NDCG@10/, 'NDCG@10'], [/95% range/, '95% range'], [/\bpaired\b/, 'paired'], [/\bblind\b/, 'blind'], [/weighted kappa/, 'weighted kappa'],
  [/\bbootstrap\b/, 'bootstrap'], [/\bWilson\b/, 'Wilson']]
const TERM_RE = new RegExp(`(${TERMS.map(([r]) => r.source).join('|')})`)
const NUM_RE = /(\d{4}-\d{2}-\d{2}|(?<![A-Za-z@\d.])[−+-]?\d(?:[\d,]*\d)?(?:\.\d+)?%?(?![A-Za-z\d]))/
function numbers(text: string, key: string): ReactNode[] {
  return text.split(NUM_RE).map((part, i) => (i % 2 ? <span key={`${key}n${i}`} className="mono evd-n">{part}</span> : part))
}
/** Text from the data layer as React nodes. `seen` keeps glossary buttons to the first use of each word inside one card. */
export function prose(text: string, seen?: Set<string>, key = 'p'): ReactNode[] {
  if (!seen) return numbers(text, key)
  return text.split(TERM_RE).flatMap((part, i): ReactNode[] => {
    if (!(i % 2)) return numbers(part, `${key}${i}`)
    const k = TERMS.find(([r]) => r.test(part))?.[1] ?? part
    if (seen.has(k)) return numbers(part, `${key}${i}`)
    seen.add(k)
    return [<Term key={`${key}t${i}`} k={k}>{part}</Term>]
  })
}

// ---- charts -------------------------------------------------------------------------------------------------------------------------------
const SCALE_TITLE: Record<EScale, string> = { retrieval: 'Match score difference (0 to 1 scale)', rating: 'Rating difference (0 to 2 scale)', rate: 'Shares and agreement (0 to 1)', count: 'Change in counts' }
const range = (e: { ci95: [number, number] | null; digits: number }, signed = true) => (e.ci95 ? `${fmt(e.ci95[0], e.digits, signed)} to ${fmt(e.ci95[1], e.digits, signed)}` : 'no range logged')
/** A difference between two ways (drawn against zero, signed), as opposed to a share or score checked against a reference. */
export const isDiff = (e: Effect) => e.ref === 0 && e.scale !== 'rate'
export const effectText = (e: Effect) => `${e.label}${e.sub ? ` (${e.sub})` : ''}: ${fmt(e.mean, e.digits, isDiff(e))}, 95% range ${range(e, isDiff(e))}`
export function effectDomain(effects: Effect[]): { domain: Domain; ticks: number[]; digits: number } {
  const vals = effects.flatMap((e) => (e.ci95 ? [...e.ci95, e.mean] : [e.mean]))
  const refs = effects.flatMap((e) => (e.ref != null ? [e.ref] : []))
  const d = niceDomain(vals, refs.length ? refs : [0])
  return { domain: d.domain, ticks: d.ticks, digits: decimalsOf(d.step) }
}
const decimalsOf = (step: number) => { const s = String(Number(step.toPrecision(6))); return s.includes('.') ? s.split('.')[1].length : 0 }

/** Effect rows on one shared axis: label, interval against the reference, the value with its range, and the verdict mark with its word. */
export function EffectRows({ effects, title, compact }: { effects: Effect[]; title?: string; compact?: boolean }) {
  if (!effects.length) return null
  const { domain, ticks, digits } = effectDomain(effects)
  const ref = effects[0].ref
  return (
    <div className="evd-chart" role="group" aria-label={title ?? SCALE_TITLE[effects[0].scale]}>
      <div className="evd-chart-head"><h3>{title ?? SCALE_TITLE[effects[0].scale]}</h3>
        <span>{isDiff(effects[0]) ? (effects[0].higherIsBetter ? 'right of the zero line: the change helped' : 'left of the zero line: the change helped') : ref != null ? `line: ${effects[0].refLabel ?? 'reference'} (${fmt(ref, 2)})` : 'measured shares'}</span></div>
      {effects.map((e) => (
        <div key={e.key} className={`evd-erow${compact ? ' compact' : ''}`}>
          <div className="evd-erow-name">{e.label}{e.sub && <small>{e.sub}</small>}</div>
          <div className="evd-erow-iv"><Interval domain={domain} ticks={ticks} mean={e.mean} ci={e.ci95} refAt={e.ref} label={effectText(e)} /></div>
          <div className="evd-erow-val mono">{fmt(e.mean, e.digits, isDiff(e))}<small>{range(e, isDiff(e))}</small></div>
          <div className="evd-erow-verdict">{e.verdict ? <><VerdictMark verdict={e.verdict} /> {VERDICT_WORD[e.verdict]}</> : <span className="dim">no reference</span>}</div>
        </div>
      ))}
      <div className="evd-erow axis" aria-hidden="true"><div /><Axis domain={domain} ticks={ticks} digits={digits} signed={isDiff(effects[0])} /><div /><div /></div>
    </div>
  )
}

/** Each way's own score with its 95% range (or a count bar), on the level's real domain. */
export function Levels({ level }: { level: Level }) {
  const vals = level.rows.flatMap((r) => (r.ci95 ? [...r.ci95, r.mean] : [r.mean]))
  const nd = level.domain ? { domain: level.domain, step: niceStep(level.domain[1] - level.domain[0]) } : niceDomain(vals, [0])
  const ticks = ticksFor(nd.domain, nd.step)
  const digits = decimalsOf(nd.step)
  return (
    <div className="evd-chart" role="group" aria-label={level.title}>
      <div className="evd-chart-head"><h3>{level.title}</h3>{level.note && <span>{level.note}</span>}</div>
      {level.rows.map((r) => (
        <div key={r.name} className={`evd-lrow${r.old ? ' old' : ''}`}>
          <div className="evd-erow-name">{r.name}{r.sub && <small>{r.sub}</small>}</div>
          <div className="evd-erow-iv"><Interval domain={nd.domain} ticks={ticks} mean={r.mean} ci={r.ci95} solid={!level.bars && !!r.ci95} bar={level.bars} inUse={r.inUse} old={r.old}
            label={`${r.name}: ${r.value ?? fmt(r.mean, level.digits)}${r.ci95 ? `, 95% range ${fmt(r.ci95[0], level.digits)} to ${fmt(r.ci95[1], level.digits)}` : ''}`} /></div>
          <div className={`evd-erow-val mono${r.inUse ? ' in-use' : ''}`}>{r.value ?? fmt(r.mean, level.digits)}{r.ci95 && <small>{fmt(r.ci95[0], level.digits)} to {fmt(r.ci95[1], level.digits)}</small>}</div>
          <div className="evd-erow-verdict dim">{r.old ? 'superseded' : r.n != null ? <>n = <span className="mono">{r.n.toLocaleString('en')}</span></> : ''}</div>
        </div>
      ))}
      <div className="evd-lrow axis" aria-hidden="true"><div /><Axis domain={nd.domain} ticks={ticks} digits={digits} /><div /><div /></div>
    </div>
  )
}

export function DataTable({ table }: { table: Table }) {
  return (
    <div className="evd-table-wrap">
      <table className="evd-table">
        <caption>{table.title}</caption>
        <thead><tr>{table.head.map((h, i) => <th key={h} scope="col" className={table.num[i] ? 'num' : ''}>{h}</th>)}</tr></thead>
        <tbody>{table.rows.map((r, j) => <tr key={j}>{r.map((c, i) => (i === 0 ? <th key={i} scope="row">{c}</th> : <td key={i} className={table.num[i] ? 'num mono' : ''}>{table.num[i] ? c : prose(c)}</td>))}</tr>)}</tbody>
      </table>
      {table.note && <p className="evd-caption">{table.note}</p>}
    </div>
  )
}

/** Every effect of a claim with its counts and file: the exact version of the chart. */
function EffectTable({ effects }: { effects: Effect[] }) {
  return (
    <div className="evd-table-wrap">
      <table className="evd-table">
        <caption>Every comparison on this question</caption>
        <thead><tr><th scope="col">Comparison</th><th scope="col" className="num">Value</th><th scope="col" className="num">95% range</th><th scope="col" className="num">Better · same · worse</th><th scope="col" className="num">n</th><th scope="col">Verdict</th><th scope="col">File</th></tr></thead>
        <tbody>
          {effects.map((e) => (
            <tr key={e.key}>
              <th scope="row">{e.label}{e.sub && <small>{e.sub}</small>}</th>
              <td className="num mono">{fmt(e.mean, e.digits + 1, isDiff(e))}</td>
              <td className="num mono">{e.ci95 ? `${fmt(e.ci95[0], e.digits + 1, isDiff(e))} to ${fmt(e.ci95[1], e.digits + 1, isDiff(e))}` : '—'}</td>
              <td className="num mono">{e.better != null && e.worse != null ? `${e.better} · ${e.tied ?? '—'} · ${e.worse}` : '—'}</td>
              <td className="num mono">{e.n != null ? e.n.toLocaleString('en') : '—'}</td>
              <td>{e.verdict ? <span className="evd-inline"><VerdictMark verdict={e.verdict} /> {VERDICT_WORD[e.verdict]}</span> : 'no reference'}</td>
              <td className="evd-file"><a href={blob(e.file)} target="_blank" rel="noreferrer">{e.file.replace('runs/', '')}</a></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ---- the claim card ---------------------------------------------------------------------------------------------------------------------
export function Card({ claim: c, extra, exact }: { claim: Claim; extra?: ReactNode; exact?: ReactNode }) {
  const seen = new Set<string>()
  const meta = [c.test_set, c.date && `Date ${c.date}`].filter(Boolean) as string[]
  const groups = (['retrieval', 'rating', 'rate', 'count'] as EScale[]).map((s) => c.effects.filter((e) => e.scale === s)).filter((g) => g.length)
  const shown = c.levels.filter((l) => !l.fold), folded = c.levels.filter((l) => l.fold)
  return (
    <section className="evd-card" id={c.id} aria-labelledby={`${c.id}-t`}>
      <header className="evd-card-head">
        <span className="evd-num mono" aria-hidden="true">{c.num}</span>
        <div>
          <h2 id={`${c.id}-t`} className="evd-q" tabIndex={-1}>{c.question}</h2>
          {meta.length > 0 && <div className="evd-meta">{meta.map((m) => <span key={m}>{prose(m)}</span>)}</div>}
        </div>
      </header>
      <div className="evd-card-body">
        <p className="evd-verdict"><VerdictMark verdict={c.verdict} /><span className="lg">{c.verdictLabel ?? 'Not computed yet'}</span>
          {c.effect && <span className="evd-verdict-n mono">{fmt(c.effect.mean, c.effect.digits, isDiff(c.effect))} {c.effect.ci95 && <small>({range(c.effect, isDiff(c.effect))})</small>}</span>}</p>
        <p className="evd-answer">{c.answer.map((a, i) => <span key={i}>{prose(a, seen, `a${i}`)} </span>)}</p>
        {c.missing.length > 0 && <ul className="evd-missing">{c.missing.map((m) => <li key={m}><VerdictMark verdict={null} /> {prose(m)}</li>)}</ul>}
        {(shown.length > 0 || groups.length > 0) && (
          <div className="evd-charts">
            {shown.map((l) => <Levels key={l.title} level={l} />)}
            {groups.map((g) => <EffectRows key={g[0].scale} effects={g} />)}
          </div>
        )}
        {extra}
        <div className="evd-facts">
          <div>
            <h3 className="lg">How it was measured</h3>
            <p>{c.method.map((m, i) => <span key={i}>{prose(m, seen, `m${i}`)} </span>)}</p>
            {c.measured.length > 0 && <dl className="evd-dl">{c.measured.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{prose(v)}</dd></div>)}</dl>}
            {c.effect && <p className="evd-rule">{prose(c.effect.rule, seen, 'r')}</p>}
          </div>
          <div>
            <h3 className="lg">Limits</h3>
            <ul>{c.limits.map((l) => <li key={l}>{prose(l, seen, l)}</li>)}</ul>
          </div>
          <div>
            <h3 className="lg">Source</h3>
            <ul className="evd-sources">
              {c.sources.map((s) => (
                <li key={s.file}><a href={blob(s.file)} target="_blank" rel="noreferrer">{s.file}</a>{s.script && <> · made by <a href={blob(s.script)} target="_blank" rel="noreferrer">{s.script}</a></>}</li>
              ))}
            </ul>
          </div>
        </div>
        {(folded.length > 0 || c.tables.length > 0 || c.effects.length > 0 || exact) && (
          <Exact label="Show the exact numbers">
            {c.effects.length > 0 && <EffectTable effects={c.effects} />}
            {folded.map((l) => <Levels key={l.title} level={l} />)}
            {c.tables.map((t) => <DataTable key={t.title} table={t} />)}
            {exact}
          </Exact>
        )}
      </div>
    </section>
  )
}

// ---- the one legend -----------------------------------------------------------------------------------------------------------------------
export function Legend() {
  const d: Domain = [-0.2, 0.2], t = ticksFor(d, 0.1)
  return (
    <section className="evd-legend" aria-labelledby="evd-legend-h">
      <h2 id="evd-legend-h" className="lg">How to read the marks</h2>
      <ul>
        <li><VerdictMark verdict="helped" /><span><strong>Helped</strong> The whole <Term k="95% range">range</Term> is on the good side.</span></li>
        <li><VerdictMark verdict="no clear effect" /><span><strong>No clear effect</strong> The range crosses zero, or the reference.</span></li>
        <li><VerdictMark verdict="hurt" /><span><strong>Hurt</strong> The whole range is on the bad side.</span></li>
        <li><VerdictMark verdict={null} /><span><strong>Not computed yet</strong> No logged file holds this number.</span></li>
      </ul>
      <div className="evd-legend-sample">
        <div className="evd-legend-iv"><Interval domain={d} ticks={t} mean={0.08} ci={[0.03, 0.13]} refAt={0} label="Sample: an average of +0.08 with a 95% range from +0.03 to +0.13, right of zero" /></div>
        <p>The tick is the average. The hatched band is the <Term k="95% range">95% range</Term>. The dashed line is zero. A magenta tick <i className="evd-tick-sample" aria-hidden="true" /> marks the way in use. A small arrow means the range runs past the edge. A struck row was replaced.</p>
      </div>
    </section>
  )
}

// ---- the contents list ------------------------------------------------------------------------------------------------------------------
/** Follows you down the page on a wide screen (a scrolling strip on a phone) and marks the question you are reading. Buttons, not links:
 *  the page's own address uses # for its routes; choosing one updates the address to #/evidence/<id> so it can be shared. */
export function Toc({ items, onChoose }: { items: { id: string; num: string; label: string; verdict: Verdict | null }[]; onChoose: (id: string) => void }) {
  const [active, setActive] = useState(items[0]?.id ?? '')
  const [all, setAll] = useState(false)
  useEffect(() => {
    if (!('IntersectionObserver' in window)) return
    const obs = new IntersectionObserver((entries) => {
      const seen = entries.filter((e) => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
      if (seen) setActive(seen.target.id)
    }, { rootMargin: '-15% 0px -65% 0px', threshold: [0, 0.15, 0.4] })
    items.forEach(({ id }) => { const el = document.getElementById(id); if (el) obs.observe(el) })
    return () => obs.disconnect()
  }, [items])
  const toggleAll = () => {
    const next = !all
    document.querySelectorAll<HTMLDetailsElement>('main details.exact').forEach((d) => { d.open = next })
    setAll(next)
  }
  return (
    <aside className="evd-toc" aria-label="Questions on this page">
      <div className="evd-toc-h lg">The questions</div>
      <nav className="evd-toc-list">
        {items.map((it) => (
          <button key={it.id} type="button" className={active === it.id ? 'active' : ''} aria-current={active === it.id ? 'true' : undefined} onClick={() => { setActive(it.id); onChoose(it.id) }}>
            <span className="mono">{it.num}</span><span>{it.label}</span><VerdictMark verdict={it.verdict} />
          </button>
        ))}
      </nav>
      <div className="evd-toc-foot">
        <button type="button" aria-pressed={all} onClick={toggleAll}>{all ? 'Close every exact-numbers panel' : 'Open every exact-numbers panel'}</button>
      </div>
    </aside>
  )
}

// ---- kept for other pages that may still import them ------------------------------------------------------------------------------------
export type Bar = { name: string; sub?: string; value: number | null | undefined; primary?: boolean }
/** Bars on one question's own scale, drawn on a real domain so the gridlines match the ticks. The value is always printed beside the bar. */
export function Bars({ title, scale, rows, max, ticks, unit = '', digits = 3, caption }: {
  title: string; scale: string; rows: Bar[]; max: number; ticks: number[]; unit?: string; digits?: number; caption?: ReactNode
}) {
  const domain: Domain = [Math.min(0, ...ticks), Math.max(max, ...ticks)]
  return (
    <div className="evd-chart" role="group" aria-label={title}>
      <div className="evd-chart-head"><h3>{title}</h3><span>{scale}</span></div>
      {rows.map((r) => (
        <div key={r.name} className="evd-lrow">
          <div className="evd-erow-name">{r.name}{r.sub && <small>{r.sub}</small>}</div>
          <div className="evd-erow-iv">{r.value != null ? <Interval domain={domain} ticks={ticks} mean={r.value} bar inUse={r.primary} label={`${r.name}: ${r.value.toFixed(digits)}${unit}`} /> : <div className="evd-none lg">not run</div>}</div>
          <div className="evd-erow-val mono">{r.value != null ? `${r.value.toFixed(digits)}${unit}` : '—'}</div><div />
        </div>
      ))}
      <div className="evd-lrow axis" aria-hidden="true"><div /><Axis domain={domain} ticks={ticks} digits={Math.max(0, ...ticks.map((t) => decimalsOf(Math.abs(t) || 1)))} /><div /><div /></div>
      {caption && <p className="evd-caption">{caption}</p>}
    </div>
  )
}

export function MiniStats({ items }: { items: { value: string; label: string }[] }) {
  return <div className="evd-mini">{items.map((s) => <div key={s.label}><strong className="mono">{s.value}</strong><span>{s.label}</span></div>)}</div>
}
