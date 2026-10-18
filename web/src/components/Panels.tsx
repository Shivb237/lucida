// The step panels: plan card, graph sheet, exposure record, time strip, search and compose panels.
import { WhyBlock, whyNotes } from './Explain'
import type { ReactNode } from 'react'
import {
  STEPS, type ComposePayload, type ExpandPayload, type LocalInfo, type RouterInfo, type SearchPayload, type StageId, type StepState, type UnderstandPayload,
} from '../trace'

export const fmt = (s: number | null | undefined, digits = 2) => (s == null ? '—' : s.toFixed(digits))
const TONES = ['#CFCFD3', '#B4B4B8', '#93939A', '#55555B', '#2B2B2E', '#141416']
type Steps = Record<StageId, StepState>

export function PlanCard({ step, demo }: { step: StepState; demo: boolean }) {
  const p = step.payload as unknown as UnderstandPayload
  const plan = p.plan
  if (step.status === 'waiting' || step.status === 'started') return null
  const rows: [string, ReactNode][] = plan ? [
    ['for', plan.gender], ['occasion', plan.occasion ?? '—'], ['season', plan.season ?? '—'],
    ['budget', plan.budget_inr != null ? `₹${plan.budget_inr.toLocaleString('en-IN')}` : '—'],
    ['you own', plan.already_has.length ? plan.already_has.join(', ') : '—'],
  ] : []
  return (
    <div className="sheet card dev" style={{ marginTop: 34, padding: '22px 26px 20px', transform: 'rotate(.4deg)', maxWidth: 760 }}>
      <h2 className="lg dim step-h">
        Step 2 · Read your sentence · <span className="mono">{fmt(step.seconds, 1)} s</span>{!demo && p.model ? <> · <span className="mono">{p.model}</span></> : ''}
        {demo && <> (demo)</>}
      </h2>
      {step.status === 'failed' && <p role="alert" style={{ margin: '10px 0 0', fontSize: 15, fontWeight: 600 }}>{p.error}</p>}
      {step.status === 'done' && p.fell_back && <p style={{ margin: '10px 0 0', fontSize: 15 }}>The AI gave no usable plan, so your whole sentence is searched as typed.</p>}
      {plan && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(260px, 100%), 1fr))', gap: '14px 28px', marginTop: 14 }}>
          <dl style={{ margin: 0 }}>
            {rows.map(([k, v]) => (
              <div key={k} style={{ display: 'grid', gridTemplateColumns: '92px minmax(0, 1fr)', gap: 10, padding: '6px 0', borderTop: '1px solid var(--z8)' }}>
                <dt className="lg dim">{k}</dt><dd className="mono" style={{ margin: 0, fontSize: 13 }}>{v}</dd>
              </div>
            ))}
          </dl>
          <div>
            <div className="lg dim" style={{ marginBottom: 6 }}>Pieces to find</div>
            {plan.pieces.map((pc, i) => (
              <div key={i} style={{ display: 'flex', flexWrap: 'wrap', gap: '2px 10px', alignItems: 'baseline', padding: '6px 0', borderTop: '1px solid var(--z8)' }}>
                <span className="lg dim" style={{ width: 70 }}>{pc.kind}</span>
                <span style={{ fontSize: 16, fontWeight: 600 }}>{pc.search_text}</span>
                {pc.colours.length > 0 && <span className="mono dim" style={{ fontSize: 12 }}>{pc.colours.join(', ')}</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export function GraphSheet({ step }: { step: StepState }) {
  const p = step.payload as ExpandPayload
  if (step.status === 'waiting' || step.status === 'started') return null
  return (
    <div className="sheet dev" style={{ marginTop: 28, marginLeft: 'auto', maxWidth: 620, padding: '22px 24px 20px', transform: 'rotate(.7deg)' }}>
      <h2 className="lg dim step-h">Step 3 · Add missing ideas <span className="mono" style={{ marginLeft: 6 }}>{step.status === 'done' ? `${fmt(step.seconds, 2)} s` : ''}</span></h2>
      {step.status === 'skipped' && <p style={{ margin: '8px 0 0', fontSize: 15 }}>Skipped: {p.reason}.</p>}
      {step.status === 'failed' && <p role="alert" style={{ margin: '8px 0 0', fontSize: 15, fontWeight: 600 }}>{p.error}</p>}
      {step.status === 'done' && (
        <>
          <p style={{ margin: '8px 0 12px', fontSize: 15, lineHeight: '22px', color: 'var(--z4)', maxWidth: '54ch' }}>
            {p.usages && p.usages.length ? <>Occasion recognised: <span className="mono">{p.usages.join(', ')}</span>.</> : 'No occasion word matched, so nothing was added.'}
          </p>
          {(p.notes ?? []).map((n) => (
            <div key={n} style={{ borderTop: '1px solid var(--z8)', padding: '8px 0', fontSize: 15, lineHeight: '22px' }}>{n.replace(/^graph: /, '')}</div>
          ))}
          {p.usages && p.usages.length > 0 && (p.notes ?? []).length === 0 && <div style={{ borderTop: '1px solid var(--z8)', padding: '8px 0', fontSize: 15 }}>The pieces already fit, so nothing was changed.</div>}
        </>
      )}
    </div>
  )
}

/** The page's own stopwatch: display only, read from the browser clock, never sent anywhere and never part of the search. */
export type Clock = { t0: number | null; endAt: number | null; now: number; startedAt: Partial<Record<StageId, number>> }
const elapsed = (c: Clock) => (c.t0 == null ? 0 : ((c.endAt ?? c.now) - c.t0) / 1000)
const runningFor = (c: Clock, id: StageId) => (c.startedAt[id] == null ? 0 : Math.max(0, (c.now - c.startedAt[id]!) / 1000))

/** The seconds the big number shows: a live run = the wall clock since you pressed Search; a replay = the logged seconds so far (plus the step running now). */
export function wallSeconds(steps: Steps, mode: string, clock: Clock): number {
  const sum = STEPS.reduce((n, s) => n + (steps[s.id].status === 'done' ? steps[s.id].seconds ?? 0 : steps[s.id].status === 'started' ? runningFor(clock, s.id) : 0), 0)
  return mode === 'recorded' || clock.t0 == null ? sum : elapsed(clock)
}

/** Pinned to the top of a phone screen while a run is on: the seconds, the step running, and six marks. On a laptop the big number is already in view, so this is hidden there. */
export function LiveStrip({ steps, mode, clock, running, onStop }: { steps: Steps; mode: string; clock: Clock; running: boolean; onStop: () => void }) {
  const current = STEPS.findIndex((s) => steps[s.id].status === 'started')
  const last = STEPS.reduce((n, s, i) => (steps[s.id].status === 'done' || steps[s.id].status === 'failed' ? i : n), -1)
  const idx = current >= 0 ? current : last
  const complete = steps.outfit.status === 'done' || steps.outfit.status === 'skipped' || steps.request.status === 'failed'
  const label = running ? (current >= 0 ? `${current + 1}. ${STEPS[current].name}` : idx >= 0 ? `${idx + 1}. ${STEPS[idx].name} done` : 'starting') : complete ? 'finished' : 'stopped'
  return (
    <div className="live-strip" id="live-strip" aria-label="Run progress">
      <span className="live-sec mono">{fmt(wallSeconds(steps, mode, clock), 1)}<small>s</small></span>
      <span className="live-step">{label}</span>
      {running && <button type="button" className="live-stop" onClick={onStop}>Stop</button>}
      <span className="live-marks" aria-hidden="true">
        {STEPS.map((s) => {
          const st = steps[s.id].status
          return <i key={s.id} className={`tile ${st === 'started' ? 'hatch started' : st === 'failed' ? 'cross' : st === 'skipped' ? 'not_built' : st}`} />
        })}
      </span>
    </div>
  )
}

export function RecordTable({ steps, mode, rid, clock }: { steps: Steps; mode: string; rid: string; clock: Clock }) {
  return (
    <div className="sheet card" style={{ flex: '1 1 600px', minWidth: 0, padding: '26px 28px 18px', transform: 'rotate(-.35deg)' }}>
      <div className="tapebit" style={{ right: 40, top: -12, transform: 'rotate(4deg)' }} />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 16, flexWrap: 'wrap' }}>
        <h2 className="h-record">Run log</h2>
        <span className="lg dim">{mode === 'idle' ? 'nothing exposed yet' : mode === 'demo' ? 'demo replay' : mode === 'recorded' ? 'recorded run' : <>request <span className="mono">{rid}</span></>}</span>
      </div>
      <div className="record">
        <div className="lg head">Step</div><div className="lg head">What happened</div>
        <div className="lg head" style={{ textAlign: 'right' }}>Seconds</div><div className="lg head built">Status</div>
        {STEPS.map((s, i) => {
          const v = steps[s.id]
          const word = { waiting: 'waiting', started: 'running', done: 'done', failed: 'failed', skipped: 'skipped' }[v.status]
          const tileClass = v.status === 'started' ? 'hatch started' : v.status === 'failed' ? 'cross' : v.status === 'skipped' ? 'not_built' : v.status
          return (
            <div key={s.id} style={{ display: 'contents' }}>
              <div><div className={`tile ${tileClass}`} aria-hidden="true" /></div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 17 }}>{i + 1}. {s.name}</div>
                <div className="step-explain" style={{ fontSize: 14, lineHeight: '20px', color: 'var(--z4)', marginTop: 2, maxWidth: '56ch' }}>{s.explain}</div>
              </div>
              <div className="mono" style={{ textAlign: 'right', fontSize: 17 }}>{v.status === 'done' ? fmt(v.seconds, 2) : v.status === 'started' ? <span className="ticking">{fmt(runningFor(clock, s.id), 1)}</span> : '—'}</div>
              <div className="lg built" style={{ color: 'var(--z4)', paddingTop: 4 }}>{word}</div>
            </div>
          )
        })}
      </div>
      <div className="legend-row">
        <span><i style={{ border: '1.5px dotted var(--z4)' }} />waiting</span>
        <span><i className="hatch" />running</span>
        <span><i style={{ background: 'var(--ink)' }} />done</span>
        <span><i className="cross" />failed</span>
        <span><i style={{ borderTop: '2px solid var(--ink)', marginTop: 6 }} />skipped</span>
      </div>
    </div>
  )
}

export function TimeStrip({ steps, mode, clock }: { steps: Steps; mode: string; clock: Clock }) {
  const search = steps.search.status === 'done' ? (steps.search.payload as unknown as SearchPayload) : null
  const load = search && search.backend === 'in-process' ? (search.info as LocalInfo).load_seconds : undefined
  const bands: { label: string; seconds: number }[] = []
  if (load) bands.push({ label: 'load', seconds: load })
  STEPS.forEach((s, i) => { const v = steps[s.id]; if (v.status === 'done' && v.seconds) bands.push({ label: String(i + 1), seconds: v.seconds }) })
  STEPS.forEach((s, i) => { if (steps[s.id].status === 'started') bands.push({ label: String(i + 1), seconds: Math.max(runningFor(clock, s.id), 0.05) }) })   // the step running now grows as time passes
  const total = bands.reduce((a, b) => a + b.seconds, 0)
  const wall = wallSeconds(steps, mode, clock)
  return (
    <div style={{ flex: '1 1 440px', minWidth: 0 }}>
      <div className="lg dim">Time per step</div>
      <div className="hero-row" style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginTop: 6 }}>
        <span className="big-number">{fmt(wall, 1)}</span>
        <span className="lg dim">seconds{mode === 'demo' ? ', demo' : mode === 'live' ? ', since you pressed Search' : mode === 'recorded' ? ', as logged' : ''}</span>
      </div>
      <div className="strip" aria-label="Time per step">
        {bands.length === 0 && <div style={{ flex: 1, border: 'none', color: 'var(--z4)', fontFamily: 'var(--sans)' }}>Each band is one step, as wide as the time it took.</div>}
        {bands.map((b, i) => (
          <div key={b.label} title={`${b.label}: ${fmt(b.seconds, 2)} s`} style={{ flex: `${(b.seconds / total) * 100} 1 0`, minWidth: 0, overflow: 'hidden', background: TONES[Math.min(i, TONES.length - 1)], color: i >= 3 ? 'var(--paper)' : 'var(--ink)' }}>{b.seconds / total >= 0.06 ? b.label : ''}</div>
        ))}
      </div>
      <div style={{ display: 'flex', marginTop: 6 }}>
        {bands.map((b) => <div key={b.label} className="mono dim" style={{ flex: `${(b.seconds / total) * 100} 1 0`, minWidth: 0, overflow: 'hidden', fontSize: 12 }}>{b.seconds / total >= 0.06 ? fmt(b.seconds, 1) : ''}</div>)}
      </div>
      {bands.some((b) => b.seconds / total < 0.06) && (
        <p className="mono" style={{ margin: '8px 0 0', fontSize: 13, color: 'var(--z4)' }}>
          Too thin to label: {bands.filter((b) => b.seconds / total < 0.06).map((b) => `${b.label} = ${fmt(b.seconds, 2)} s`).join(' · ')}
        </p>
      )}
      {(() => {
        const notes = mode === 'live' ? whyNotes(steps) : []
        if (notes.length === 0) return null
        const label = String(STEPS.findIndex((x) => x.id === notes[0].stage) + 1)       // the band of the slowest step
        let before = 0, at: number | null = null
        for (const b of bands) { if (b.label === label) { at = ((before + b.seconds / 2) / total) * 100; break } before += b.seconds }
        return <WhyBlock notes={notes} at={at} />
      })()}
      {load ? <p style={{ margin: '10px 0 0', fontSize: 14, lineHeight: '21px', color: 'var(--z4)' }}>"load" is the one-off loading of the model and the four collections on this server's first search. Later searches skip it.</p> : null}
    </div>
  )
}

export function SearchPanel({ step }: { step: StepState }) {
  if (step.status !== 'done' && step.status !== 'failed') return null
  const p = step.payload as unknown as SearchPayload
  if (step.status === 'failed') return <p role="alert" style={{ marginTop: 24, fontSize: 15 }}><strong>Search failed:</strong> {p.error}</p>
  const router = p.backend === 'router'
  const local = p.info as LocalInfo
  const reqs = (p.info as RouterInfo).requests ?? []
  return (
    <div className="dev" style={{ marginTop: 30 }}>
      <h2 className="lg dim step-h">Step 4 · Find products · {router ? 'work split across 4 slices' : 'inside this program'}</h2>
      {router ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 10 }}>
          {reqs.map((r, i) => (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: 12, alignItems: 'center' }}>
              <div style={{ display: 'flex', gap: 4 }} aria-label={`${r.shards.ok} of ${r.shards.total} slices answered`}>
                {Array.from({ length: r.shards.total }).map((_, s) => <div key={s} className={s < r.shards.ok ? '' : 'cross'} style={{ flex: 1, height: 22, border: '1px solid var(--ink)', background: s < r.shards.ok ? 'var(--z4)' : undefined }} />)}
              </div>
              <span className="mono" style={{ fontSize: 13 }}>{fmt(r.timings_ms.total, 1)} ms</span>
              <span style={{ gridColumn: '1 / -1', fontSize: 13, color: 'var(--z4)' }}>
                turning words into numbers {fmt(r.timings_ms.encode, 1)} ms · looking up {fmt(r.timings_ms.shards, 1)} ms · combining {fmt(r.timings_ms.merge, 1)} ms
                {r.shards.failovers > 0 && ` · ${r.shards.failovers} switched to a backup copy`}{r.shards.hedged > 0 && ` · ${r.shards.hedged} also asked a backup because the first was slow`}
                {r.partial && <strong style={{ color: 'var(--ink)' }}> · incomplete answer: {r.shards.failed} slice(s) did not reply, so some products may be missing</strong>}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p style={{ margin: '10px 0 0', fontSize: 14, lineHeight: '21px', maxWidth: '58ch' }}>
          All four collections were searched inside this one program. Turning the pieces into numbers took <span className="mono">{fmt(local.encode_seconds, 3)} s</span>; comparing with every photo took <span className="mono">{fmt(step.seconds, 3)} s</span>.
          <span style={{ display: 'block', marginTop: 6, color: 'var(--z4)' }}>To see the split system at work, start it with <code className="mono" style={{ fontSize: 12 }}>scripts/cluster.sh start</code>; this page uses it automatically.</span>
        </p>
      )}
      {p.checks && p.checks.length > 0 && (
        <div className="checks-note">
          <strong>Checks on what was found</strong> (the search compares words with photos, so these keep the results to what you asked for):
          <ul>{p.checks.map((c) => <li key={c}>{c}</li>)}</ul>
        </div>
      )}
    </div>
  )
}

export function ComposePanel({ step }: { step: StepState }) {
  const p = step.payload as ComposePayload
  if (step.status === 'waiting' || step.status === 'started') return null
  return (
    <div className="sheet card dev" style={{ marginTop: 36, padding: '22px 26px', maxWidth: 820, transform: 'rotate(-.3deg)' }}>
      <h2 className="lg dim step-h">Step 5 · Pick an outfit <span className="mono" style={{ marginLeft: 6 }}>{step.status === 'done' ? `${fmt(step.seconds, 2)} s` : ''}</span></h2>
      {step.status === 'skipped' && <p style={{ margin: '8px 0 0', fontSize: 15 }}>Skipped: {p.reason}.</p>}
      {step.status === 'done' && p.harmony && (
        <>
          <p style={{ margin: '10px 0 0', fontSize: 16, lineHeight: '24px' }}>
            Colours go together: <span className="mono" style={{ fontSize: 15 }}>{p.harmony.coherent.toFixed(2)}</span> out of 1. <span className="mono" style={{ fontSize: 15 }}>{p.changed}</span> of {p.pieces} picks were swapped for a better colour match. <strong>A check with no measured benefit.</strong>
          </p>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
            {(p.colours ?? []).map((c, i) => <span key={i} className="chip" style={{ cursor: 'default', minHeight: 0 }}>piece {i + 1}: {c ?? 'unreadable'}</span>)}
          </div>
          <p style={{ margin: '12px 0 0', fontSize: 14, lineHeight: '21px', color: 'var(--z4)', maxWidth: '70ch' }}>
            Colours are read from the photos, so they are approximate. In a test on 30 outfits, picking for matching colours made no difference to the ratings (see Evidence).
          </p>
        </>
      )}
    </div>
  )
}
