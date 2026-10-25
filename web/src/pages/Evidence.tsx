// The Evidence page: one plain sentence, the scorecard (every paired difference as an interval against zero, with its computed verdict),
// then one card per question (verdict, chart with its 95% ranges, how it was measured, limits, sources, exact numbers folded below) with a
// contents list that follows you down the page. Every number comes from virtual:evidence; nothing here is typed in.
import { useCallback, useEffect, useRef, useState } from 'react'
import evidence from 'virtual:evidence'
import '../evidence.css'
import { Legend, REPO, Toc } from '../components/EvidenceKit'
import { Findings } from '../components/Findings'
import { ForestPlot } from '../components/ForestPlot'
import { Term } from '../components/Term'
import { GLOSSARY } from '../content/glossary'
import { PHOTO_BASE } from '../recorded'

/** One Stable Diffusion drawing. If it fails to load it is asked for once more (past any bad cached answer); if that fails too, a labelled tile says
 *  which address failed, so the problem can be named instead of showing a bare broken-image icon. */
function Drawing({ src, query }: { src: string; query: string }) {
  const [tries, setTries] = useState(0)
  if (tries >= 2) return <a className="drawing-fail evd-drawing-fail" href={src} target="_blank" rel="noreferrer"><span className="lg">Drawing did not load</span><span>{src}</span></a>
  return (
    <img className="evd-drawing" src={tries ? `${src}?retry=${tries}` : src} alt={`Stable Diffusion drawing for: ${query}`} width={512} height={512} loading="lazy" decoding="async"
      onError={() => window.setTimeout(() => setTries((n) => n + 1), tries ? 0 : 1200)} />
  )
}

// What is visibly missing from a drawing, noted by eye on 2026-10-13 (an observation, not a measurement).
const SEEN: Record<string, string> = { '39544': 'no lights', '39583': 'no garment drawn', '39592': 'no graphic', '42170': 'no garment drawn' }

/** The 20 drawings with their per-search match scores. The mini bars share one domain (the largest score, rounded up), clamped to it. */
function Drawings() {
  const { frames, steps } = evidence.drawing
  const top = Math.max(0, ...frames.flatMap((f) => [f.drawn ?? 0, f.words ?? 0]))
  const max = Math.max(0.1, Math.ceil(top * 10) / 10)
  const w = (v: number | null) => `${Math.max(0, Math.min(1, (v ?? 0) / max)) * 100}%`
  return (
    <div className="film evd-film">
      <div className="edge evd-edge"><span>LUCIDA · STABLE DIFFUSION 1.5{steps.length === 1 ? ` · ${steps[0]} STEPS` : ''}</span><span>{frames.length} DRAWINGS · BARS 0 TO {max.toFixed(1)}</span></div>
      <div className="evd-drawn-grid">
        {frames.map((f) => {
          const won = f.drawn != null && f.words != null && f.drawn > f.words
          return (
            <figure key={f.queryId}>
              <div className="evd-drawn-pic">
                <Drawing src={`${import.meta.env.BASE_URL}${f.image}`} query={f.query} />
                {SEEN[f.queryId] && <div className="evd-tagnote lg">{SEEN[f.queryId]}</div>}
                {won && <svg className="grease" aria-hidden="true" viewBox="0 0 100 100" preserveAspectRatio="none" style={{ left: '-8%', top: '-8%', width: '116%', height: '116%' }}><path pathLength={100} d="M52 3 C82 2 98 22 97 51 C96 81 74 98 46 97 C18 96 2 76 4 47 C6 20 27 5 60 6" fill="none" stroke="var(--mag-film)" strokeWidth="3.4" strokeLinecap="round" vectorEffect="non-scaling-stroke" /></svg>}
              </div>
              <figcaption>
                <div className="evd-drawn-q">{f.query}</div>
                <div className="evd-mini-bars">
                  <span className="lg">Drawn</span><div className="b"><div className="drawn" style={{ width: w(f.drawn) }} /></div><span className="mono">{f.drawn?.toFixed(3) ?? '—'}</span>
                  <span className="lg">Words</span><div className="b"><div className="words" style={{ width: w(f.words) }} /></div><span className="mono">{f.words?.toFixed(3) ?? '—'}</span>
                </div>
              </figcaption>
            </figure>
          )
        })}
      </div>
      <p className="evd-film-note">Match score (0 to 1) per search. <span className="evd-film-mag">Circled</span>: where the drawing won. Tags note what is visibly missing, seen by eye, not scored. These are AI drawings, not product photos.</p>
    </div>
  )
}

/** Old in-page ids (before the claims model) still lead to the right card. */
const LEGACY: Record<string, string> = { 'sec-methods': 'model', 'sec-drawing': 'drawing', 'sec-catalogues': 'collections', 'sec-understanding': 'plan', 'sec-graph': 'graph', 'sec-colour': 'colour', 'sec-feedback': 'likes' }
const calm = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

export function EvidencePage({ sub }: { sub?: string }) {
  const { claims } = evidence
  const chosen = useRef<string | null>(null)
  const go = useCallback((id: string, share = true) => {
    const el = document.getElementById(id)
    if (!el) return
    el.scrollIntoView({ behavior: calm() ? 'auto' : 'smooth', block: 'start' })
    el.querySelector<HTMLElement>('h2')?.focus({ preventScroll: true })
    if (share) { chosen.current = id; history.replaceState(history.state, '', `#/evidence/${id}`) }
  }, [])
  // open the card named in the address: from the router's `sub`, or read from the hash itself (and on later hash changes) when no router passes it
  useEffect(() => {
    let t = 0
    const open = (s: string | undefined) => {
      if (!s) return
      const id = LEGACY[s] ?? s
      if (id === chosen.current) return   // we set this address ourselves; the card is already in view
      window.cancelAnimationFrame(t)
      t = window.requestAnimationFrame(() => go(id, false))
    }
    const fromHash = () => decodeURIComponent(window.location.hash.match(/^#\/evidence\/([^/?]+)/)?.[1] ?? '') || undefined
    open(sub ?? fromHash())
    const onHash = () => { chosen.current = null; open(fromHash()) }
    window.addEventListener('hashchange', onHash)
    return () => { window.cancelAnimationFrame(t); window.removeEventListener('hashchange', onHash) }
  }, [sub, go])
  const drawingStudy = PHOTO_BASE ? <p className="evd-study"><a className="btn-line" href={`${PHOTO_BASE}/#/study`}>Take part in a 5-minute study: does a drawing help you?</a></p> : null
  return (
    <main id="main" tabIndex={-1} className="wrap evd">
      <h1 className="voice evd-h1">What we measured, and how sure we are.</h1>
      <p className="plain evd-lead"><span className="mono">{claims.length}</span> questions, each answered by a logged test. Each answer comes with a <Term k="95% range">95% range</Term>: how far it could move by luck.</p>

      <section className="evd-score" aria-labelledby="evd-score-h">
        <h2 id="evd-score-h" className="evd-h2">The scorecard</h2>
        <p className="evd-score-lead">Each line compares two ways on the same requests (a <Term k="paired">paired</Term> <Term k="difference">difference</Term>). Right of zero means the change helped. Search scores and a person’s ratings use different scales, so they sit in separate panels.</p>
        <ForestPlot claims={claims} onChoose={go} />
        <Legend />
      </section>

      <div className="evd-layout">
        <Toc items={claims.map((c) => ({ id: c.id, num: c.num, label: c.short, verdict: c.verdict }))} onChoose={go} />
        <div className="evd-stack">
          <Findings claims={claims} extras={{ drawing: { extra: drawingStudy, exact: <Drawings /> } }} />
          <footer className="evd-foot">
            <p><a className="evd-link" href={`${REPO}/tree/main/runs`} target="_blank" rel="noreferrer">All raw numbers: the runs folder on GitHub</a></p>
            <p><a className="evd-link" href="#/words">All <span className="mono">{GLOSSARY.length}</span> words in the Glossary</a></p>
          </footer>
        </div>
      </div>
    </main>
  )
}

export const Evidence = EvidencePage
export default EvidencePage
