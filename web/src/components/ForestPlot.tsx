// The scorecard: every paired difference on the page as one forest plot (each effect an interval against zero), in two panels because the
// two scales cannot be compared: search-score differences (0 to 1) and a person's rating differences (0 to 2). Each row names its question,
// draws the interval, gives the verdict as a mark and a word, the number of requests, and a button to that question's card. Checks that are
// shares or counts (not differences) are listed below, each against its own stated reference. The plot scrolls sideways on a phone so its
// 12px text never shrinks.
import type { Claim, Effect } from 'virtual:evidence'
import { Axis, Interval, fmt } from './Interval'
import { VERDICT_WORD, VerdictMark, effectDomain, effectText, isDiff } from './EvidenceKit'

type Row = { claim: Claim; e: Effect | null }

function Panel({ title, note, rows, onChoose }: { title: string; note: string; rows: Row[]; onChoose: (id: string) => void }) {
  const effects = rows.flatMap((r) => (r.e ? [r.e] : []))
  if (!rows.length) return null
  const { domain, ticks, digits } = effectDomain(effects.length ? effects : [])
  return (
    <div className="evd-forest-panel" role="group" aria-label={title}>
      <div className="evd-chart-head"><h3>{title}</h3><span>{note}</span></div>
      <p className="evd-scroll-hint">Swipe sideways to see the ranges.</p>
      <div className="evd-scroll" tabIndex={0} aria-label={`${title}, scrolls sideways`}>
        <div className="evd-forest">
          <div className="evd-frow head" aria-hidden="true">
            <span className="lg">Question and comparison</span><span className="lg">Difference, with its 95% range</span><span className="lg">Verdict</span><span className="lg num">n</span><span />
          </div>
          {rows.map(({ claim: c, e }, i) => {
            const first = i === 0 || rows[i - 1].claim.id !== c.id
            return (
              <div key={e?.key ?? c.id} className={`evd-frow${first ? ' first' : ''}`}>
                <div className="evd-frow-name">
                  {first && <span className="evd-frow-q"><span className="mono">{c.num}</span> {c.short}</span>}
                  <span>{e ? e.label : 'Not computed yet'}{e?.sub && <small>{e.sub}</small>}</span>
                </div>
                <div className="evd-frow-iv">
                  {e ? <Interval domain={domain} ticks={ticks} mean={e.mean} ci={e.ci95} refAt={e.ref} label={effectText(e)} height={22} />
                    : <div className="evd-none lg">not computed yet</div>}
                </div>
                <div className="evd-frow-v">{e?.verdict ? <><VerdictMark verdict={e.verdict} /><span>{VERDICT_WORD[e.verdict]}</span></> : <><VerdictMark verdict={null} /><span>not yet</span></>}
                  {e && <small className="mono">{fmt(e.mean, e.digits, true)}</small>}</div>
                <div className="evd-frow-n mono">{e?.n != null ? e.n.toLocaleString('en') : '—'}</div>
                <div>{first && <button type="button" className="evd-go" onClick={() => onChoose(c.id)} aria-label={`Go to question ${c.num}: ${c.question}`}>See card</button>}</div>
              </div>
            )
          })}
          <div className="evd-frow axis" aria-hidden="true"><span /><Axis domain={domain} ticks={ticks} digits={digits} signed /><span /><span /><span /></div>
        </div>
      </div>
    </div>
  )
}

export function ForestPlot({ claims, onChoose }: { claims: Claim[]; onChoose: (id: string) => void }) {
  const rowsFor = (scale: 'retrieval' | 'rating') => claims.filter((c) => c.scale === 'retrieval' || c.scale === 'rating').flatMap((c): Row[] => {
    const es = c.effects.filter((e) => e.forest && e.scale === scale)
    if (es.length) return es.map((e) => ({ claim: c, e }))
    return c.scale === scale && !c.effects.some((e) => e.forest) ? [{ claim: c, e: null }] : []
  })
  const others = claims.filter((c) => c.scale === 'rate' || c.scale === 'count')
  return (
    <div className="evd-forest-wrap">
      <Panel title="Search-score differences" note="match score, 0 to 1 · right of zero: the change helped" rows={rowsFor('retrieval')} onChoose={onChoose} />
      <Panel title="Human-rating differences" note="a person’s rating, 0 to 2 · right of zero: the change helped" rows={rowsFor('rating')} onChoose={onChoose} />
      {others.length > 0 && (
        <div className="evd-forest-panel" role="group" aria-label="Checks measured as shares or counts">
          <div className="evd-chart-head"><h3>Checks measured as shares or counts</h3><span>each against its own reference, explained on its card</span></div>
          <ul className="evd-others">
            {others.map((c) => (
              <li key={c.id}>
                <span className="evd-frow-q"><span className="mono">{c.num}</span> {c.question}</span>
                <span className="evd-frow-v"><VerdictMark verdict={c.verdict} /><span>{c.verdictLabel ?? 'Not computed yet'}</span></span>
                <span className="evd-others-n">{c.effect ? <><span className="mono">{fmt(c.effect.mean, c.effect.digits, isDiff(c.effect))}</span> {c.effect.label.toLowerCase()}{c.effect.n != null && <>, n = <span className="mono">{c.effect.n.toLocaleString('en')}</span></>}</> : 'not computed yet'}</span>
                <button type="button" className="evd-go" onClick={() => onChoose(c.id)} aria-label={`Go to question ${c.num}: ${c.question}`}>See card</button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
