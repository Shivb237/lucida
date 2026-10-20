// Chapter 1 of the Viewer: the problem in one line, what this is (the headline), why it matters (one line), and an explainer that loops through the
// recorded runs. It is also the "how it works": the six steps sit under the three stages (STAGES). Each run's six steps fill in one by one with a plain caption saying what that step did for THIS request, then the outfit
// holds for a moment, then the next request starts (about 9 s per run). It pauses on hover, on keyboard focus, when scrolled away and when
// the tab is hidden, and has Pause / previous / next buttons (WCAG 2.2.2). Under reduced motion nothing moves by itself: a finished frame,
// with the buttons to step through runs. Every frame is computed once per run from its logged events (no network, nothing re-derived per tick).
import { useEffect, useMemo, useRef, useState } from 'react'
import evidence from 'virtual:evidence-front'
import { HEADLINE, PROBLEM, WHY } from '../brand'
import { narrateSteps } from '../content/story'
import { RECORDED, type RecordedRun } from '../recorded'
import { emptySteps, MARK_CLASS, STAGES, STEPS, type OutfitPayload, type StageId, type StepState } from '../trace'
import { Picture } from './Sheet'

const calm = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
const RUN_MS = 650, GAP_MS = 250, HOLD_MS = 3400      // per step: running, then done; the finished outfit holds; 6 x 0.9 s + 3.4 s = about 8.8 s a run
const LAST = STEPS.length * 2                          // phases 0..LAST-1: step i running (2i) or finished (2i+1); LAST: the outfit holds

type Frame = { steps: Record<StageId, StepState>; caption: string; at: number }

/** Every frame of one run, computed once: the step states after each phase and the sentence that explains that phase. */
function framesOf(run: RecordedRun): Frame[] {
  const final = emptySteps()
  for (const e of run.events) if (e.kind === 'step' && e.status !== 'started') final[e.stage] = { status: e.status, seconds: e.seconds, payload: e.payload }
  const told = narrateSteps(final)
  const frames: Frame[] = []
  for (let ph = 0; ph <= LAST; ph++) {
    const steps = emptySteps()
    STEPS.forEach((st, i) => {
      if (ph > 2 * i) steps[st.id] = final[st.id]
      else if (ph === 2 * i) steps[st.id] = { status: 'started', seconds: null, payload: {} }
    })
    const i = Math.min(Math.floor(ph / 2), STEPS.length - 1)
    const st = STEPS[i]
    const total = STEPS.reduce((n, x) => n + (final[x.id].seconds ?? 0), 0)
    const pieces = ((final.outfit.payload as OutfitPayload)?.items ?? []).length
    const caption = ph === LAST
      ? `Done: ${pieces} piece${pieces === 1 ? '' : 's'}, one outfit, in ${total.toFixed(1)} s as logged.`
      : ph % 2 === 0 ? `${st.name}: ${st.explain}`
      : st.id === 'outfit' && pieces ? `${st.name}: ${((final.outfit.payload as OutfitPayload).items ?? []).map((it) => `a ${it.kind} from ${it.pick.source === 'marqo' ? 'Marqo' : it.pick.source === 'kaggle' ? 'Kaggle' : it.pick.source === 'myntra2' ? 'Myntra' : "the men's set"}`).join(', ')}.`
      : `${st.name}: ${told[st.id].headline}`
    frames.push({ steps, caption, at: ph })
  }
  return frames
}

const picksOf = (run: RecordedRun) => ((framesOf(run)[LAST].steps.outfit.payload as OutfitPayload)?.items ?? []).map((it) => it.pick)

export function Hero({ runs, onWatch }: { runs: RecordedRun[]; onWatch: (run: RecordedRun) => void }) {
  const still = useMemo(() => calm(), [])
  const frames = useMemo(() => runs.map(framesOf), [runs])
  const [idx, setIdx] = useState(0)
  const [phase, setPhase] = useState(still ? LAST : 0)
  const [paused, setPaused] = useState(false)          // the visitor pressed Pause
  const [held, setHeld] = useState(false)              // hover or keyboard focus inside the explainer
  const [seen, setSeen] = useState(true)               // on screen and the tab visible
  const box = useRef<HTMLElement | null>(null)
  const moving = !still && !paused && !held && seen && runs.length > 0

  useEffect(() => {
    const el = box.current
    if (!el) return
    let onScreen = true
    const update = () => setSeen(onScreen && document.visibilityState === 'visible')
    const io = new IntersectionObserver(([e]) => { onScreen = e.isIntersecting; update() }, { threshold: 0.25 })
    io.observe(el)
    document.addEventListener('visibilitychange', update)
    return () => { io.disconnect(); document.removeEventListener('visibilitychange', update) }
  }, [runs.length])

  useEffect(() => {                                    // one timer for the next phase; resumes where it stopped
    if (!moving) return
    const wait = phase === LAST ? HOLD_MS : phase % 2 === 0 ? RUN_MS : GAP_MS
    const t = window.setTimeout(() => {
      if (phase === LAST) { setIdx((i) => (i + 1) % runs.length); setPhase(0) } else setPhase(phase + 1)
    }, wait)
    return () => window.clearTimeout(t)
  }, [moving, phase, runs.length])

  useEffect(() => {                                    // the next run's photos load while this one plays, so its outfit appears at once
    const next = runs[(idx + 1) % Math.max(runs.length, 1)]
    if (next) for (const h of picksOf(next)) if (h.image) { const im = new Image(); im.src = h.image }
  }, [idx, runs])

  const go = (d: number) => { setIdx((i) => (i + d + runs.length) % runs.length); setPhase(still ? LAST : 0) }
  const run = runs[idx]
  const frame = frames[idx]?.[phase]
  const steps = frame?.steps ?? emptySteps()
  const outfit = steps.outfit.status === 'done' ? (steps.outfit.payload as OutfitPayload).items ?? [] : []
  const seconds = STEPS.reduce((n, s) => n + (steps[s.id].status === 'done' ? steps[s.id].seconds ?? 0 : 0), 0)
  return (
    <section className="hero chapter" aria-labelledby="hero-h">
      <div className="hero-copy">
        <p className="hero-kicker">{PROBLEM}</p>
        <h1 id="hero-h" className="voice hero-h">{HEADLINE}</h1>
        <p className="hero-why">{WHY}</p>
        <p className="hero-lineage">Evolved from GenKart, a 2023 hackathon idea. Lucida measures what actually works.</p>
        <div className="hero-actions">
          <button type="button" className="btn-expose" onClick={() => run && onWatch(run)}>Watch it step by step</button>
          <a className="text-link" href="#/evidence">See what was measured <span aria-hidden="true">→</span></a>
        </div>
      </div>
      {run && (
        <figure ref={box} className="hero-run" aria-label="Recorded runs, replayed one after another"
          onMouseEnter={() => setHeld(true)} onMouseLeave={() => setHeld(false)}
          onFocus={() => setHeld(true)} onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setHeld(false) }}>
          <div className="hero-run-top">
            <p className="lg dim hero-run-label">Real request {idx + 1} of {runs.length}, replayed</p>
            <div className="hero-ctl">
              <button type="button" className="hero-btn" onClick={() => go(-1)} aria-label="Previous request"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3 5 8l5 5" fill="none" stroke="currentColor" strokeWidth="1.8" /></svg></button>
              {!still && <button type="button" className="hero-btn" onClick={() => setPaused((p) => !p)} aria-pressed={paused} aria-label={paused ? 'Play the replay' : 'Pause the replay'}>
                {paused ? <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3v10l8-5z" fill="currentColor" /></svg> : <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3v10M11 3v10" stroke="currentColor" strokeWidth="2.2" /></svg>}
              </button>}
              <button type="button" className="hero-btn" onClick={() => go(1)} aria-label="Next request"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="m6 3 5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.8" /></svg></button>
            </div>
          </div>
          <blockquote className="voice hero-q">“{run.prompt}”</blockquote>
          {/* how it works, inside the replay: the three stages, each with its own steps' marks filling in */}
          <ol className="hero-stages" aria-hidden="true">
            {STAGES.map((st, si) => (
              <li key={st.name}>
                <span className="hero-stage-h">{si + 1}. {st.name}</span>
                <ol className="hero-marks">
                  {st.steps.map((id) => {
                    const i = STEPS.findIndex((x) => x.id === id)
                    return <li key={id} data-now={frame && Math.floor(frame.at / 2) === i && frame.at < LAST}><i className={`tile ${MARK_CLASS[steps[id].status]}`} /><span className="lg">{STEPS[i].name}</span></li>
                  })}
                </ol>
              </li>
            ))}
          </ol>
          <p className="hero-caption" aria-hidden="true">{frame?.caption}</p>
          <p className="hero-status" aria-hidden="true">
            <span className="mono">{seconds.toFixed(1)} s</span> <span className="lg dim">{outfit.length ? 'as logged' : 'so far'}</span>
          </p>
          <div className="hero-print" data-ready={outfit.length > 0}>
            {outfit.length > 0
              ? <div className="hero-board">{outfit.map((it) => <figure key={it.pick.id}><div className="positive"><Picture hit={it.pick} /></div><figcaption className="lg">{it.kind}</figcaption></figure>)}</div>
              : <div className="hero-wait"><span className="lg dim">The outfit appears here</span></div>}
          </div>
          <p className="sr-only">{`Request: ${run.prompt}. Three stages: ${STAGES.map((st) => st.name).join(', then ')}. ${frames[idx][LAST].caption} Use Watch it step by step to see every step.`}</p>
        </figure>
      )}
    </section>
  )
}

const med = (xs: number[]) => { const s = [...xs].sort((a, b) => a - b); return s.length ? s[Math.floor(s.length / 2)] : 0 }

/** Chapter 2: the project's three results, strongest first, one sentence pair each. Each card links to its claim on the Evidence page. */
export function Learned() {
  const cards = useMemo(() => {
    const d = evidence.drawing
    // all three drawing variants from runs/m2.summary.json; the card quotes the best one against words alone, so it never picks the weakest
    const drawn = ([['Words plus a drawing', d?.textGen], ['A drawing alone', d?.genFashion], ['The v1 way', d?.genResnet]] as const)
      .flatMap(([name, s]) => (s?.ndcg10 ? [{ name, score: s.ndcg10.mean, hi: s.paired?.ci95[1] ?? null }] : [])).sort((a, b) => b.score - a.score)
    const best = drawn[0]
    const v1 = d?.genResnet?.ndcg10?.mean ?? null
    const b4 = evidence.findings?.blind4
    const b5 = evidence.blind5
    const extra = med(RECORDED.runs.flatMap((r) => r.events.flatMap((e) => (e.kind === 'step' && e.stage === 'understand' && e.status === 'done' ? [e.seconds ?? 0] : []))))
    return [
      b4?.methods?.A && b4.methods.B && {
        id: 'collections', title: 'Adding Indian-wear collections helped most.',
        big: `${b4.methods.A.mean.toFixed(2)} → ${b4.methods.B.mean.toFixed(2)}`,
        scale: 'rating, 0 to 2 (2 is best)',
        body: `The first collection had almost no sarees or kurtas. Rated on ${b4.methods.A.n_prompts} festival and wedding requests.`,
      },
      best && d.text?.ndcg10 && {
        id: 'drawing', title: best.hi != null && best.hi < 0 ? 'Drawing the outfit first made search worse.' : 'Drawing the outfit first did not beat words.',
        big: `${best.score.toFixed(2)} vs ${d.text.ndcg10.mean.toFixed(2)}`,
        scale: 'match score, 0 to 1 (higher is better)',
        body: `${best.name}, the best of ${['no', 'one', 'two', 'three'][drawn.length] ?? drawn.length} drawing variants, ${best.score < d.text.ndcg10.mean ? 'still lost to' : 'did not clearly beat'} words alone${v1 != null && best.name !== 'The v1 way' ? ` (the v1 way: ${v1.toFixed(2)})` : ''}. So that step is off.`,
      },
      b5 && {
        id: 'plan', title: 'The AI reading step did not beat plain search.',
        big: `${b5.mean.C.toFixed(2)} vs ${b5.mean.B.toFixed(2)}`,
        scale: 'rating, 0 to 2 (2 is best)',
        body: `It took about ${extra.toFixed(0)} s longer. On ${b5.n_prompts} requests, the gap could be chance.`,
      },
    ].filter(Boolean) as { id: string; title: string; big: string; scale: string; body: string }[]
  }, [])
  const fine = useMemo(() => {
    const a = evidence.agreement
    const both = ([['test 4', a?.test4], ['test 5', a?.test5]] as const).flatMap(([t, x]) => (x ? [{ t, x }] : []))
    if (!both.length) return 'Rated blind by one person, the author. Small samples: treat these as hints.'
    const k = (x: number) => x.toFixed(2).replace('-', '−')
    return `Rated blind by the author; ${both.map(({ t, x }) => `${t} also by ${x.raters === 2 ? 'a second rater' : `${x.raters - 1} more raters`} (weighted kappa ${k(x.weightedKappa.mean)} [${k(x.weightedKappa.ci95[0])}, ${k(x.weightedKappa.ci95[1])}], ${x.nItems} options)`).join('; ')}. Small samples: treat these as hints.`
  }, [])
  if (cards.length === 0) return null
  return (
    <section className="learned chapter" aria-labelledby="learned-h">
      <h2 id="learned-h" className="sec-h">What we learned</h2>
      <ol className="learned-cards">
        {cards.map((c) => (
          <li key={c.id} className="learned-card">
            <h3>{c.title}</h3>
            <div className="learned-big mono">{c.big}</div>
            <div className="lg dim">{c.scale}</div>
            <p>{c.body}</p>
            <a href={`#/evidence/${c.id}`}>See the evidence <span aria-hidden="true">→</span></a>
          </li>
        ))}
      </ol>
      <p className="learned-fine">{fine}</p>
    </section>
  )
}
