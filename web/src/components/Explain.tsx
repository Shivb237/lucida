// Plain-language notes about time. While a step is slow: what is happening right now. After a run: why a step took long, with a dashed arrow at its band.
// Every cause stated here is a fact the server measured and put in the step (for example what the first use of the clothes map cost); where no cause was
// recorded the note says so instead of guessing.
import { STEPS, type StageId, type StepState } from '../trace'

export type Steps = Record<StageId, StepState>
const f = (n: number, d = 1) => n.toFixed(d)

const LIVE: Partial<Record<StageId, (who: string) => { title: string; body: string }>> = {
  understand: (who) => ({ title: 'Waiting for your AI provider', body: `${who} is reading your sentence. Providers usually answer within a few seconds. I wait up to about a minute, then search your sentence as typed. You can stop waiting any time.` }),
  expand: () => ({ title: 'Opening the clothes map', body: 'This step opens the map of how clothes and occasions go together. The first search after the server wakes up can take much longer than later ones.' }),
  search: () => ({ title: 'Matching products', body: 'Your words are being matched against about 100,000 product photos. The first search after the server wakes up also loads the search model.' }),
}

/** What is happening NOW, once a step has run for 2 seconds. Shows nothing for the steps that are always fast. */
export function LiveWhy({ steps, startedAt, now, who, onStop }: { steps: Steps; startedAt: Partial<Record<StageId, number>>; now: number; who: string; onStop: () => void }) {
  const cur = STEPS.find((s) => steps[s.id].status === 'started')
  const seconds = cur && startedAt[cur.id] != null ? Math.max(0, (now - startedAt[cur.id]!) / 1000) : 0
  const make = cur && LIVE[cur.id]
  if (!cur || !make || seconds < 2) return null
  const t = make(who)
  return (
    <div className="why-live">
      <svg className="why-arrow" aria-hidden="true" viewBox="0 0 60 44" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="4 5">
        <path d="M10 40 C 10 22, 30 14, 50 6" /><path d="M41 4 L51 5.5 L48 15" strokeDasharray="0" />
      </svg>
      <div role="status">
        <strong>{t.title}</strong> <span className="mono why-secs" aria-hidden="true">step {STEPS.findIndex((s) => s.id === cur.id) + 1} · {f(seconds)} s</span>
        <p>{t.body}</p>
        <button type="button" className="btn-line" onClick={onStop}>Stop waiting</button>
      </div>
    </div>
  )
}

export type Why = { stage: StageId; seconds: number; text: string }

/** After a run: the steps that took 3 seconds or more, each with the reason the server recorded (or the plain admission that none was). Longest first. */
export function whyNotes(steps: Steps): Why[] {
  const out: Why[] = []
  for (const s of STEPS) {
    const v = steps[s.id]
    if ((v.status !== 'done' && v.status !== 'failed') || v.seconds == null || v.seconds < 3) continue
    const secs = f(v.seconds)
    if (s.id === 'expand') {
      const g = (v.payload as { graph_first_use?: { import_seconds: number; read_seconds: number; build_seconds: number } }).graph_first_use
      const waited = (v.payload as { waited_for_startup_seconds?: number }).waited_for_startup_seconds
      out.push({ stage: s.id, seconds: v.seconds, text: waited
        ? `This step waited ${f(waited)} s for the server to finish starting up: it had just woken from sleep and was still loading the search model, the product collections and the clothes map. Searches after that skip the wait.`
        : g
        ? `This step set up the clothes map for the first time since the server woke up: ${f(g.import_seconds)} s loading its libraries, ${f(g.read_seconds)} s reading the data, ${f(g.build_seconds)} s building the map. That happens once per wake-up; the next search takes well under a second.`
        : `This step took ${secs} s, longer than usual. The server did not record a reason.` })
    } else if (s.id === 'understand') {
      out.push({ stage: s.id, seconds: v.seconds, text: `Your AI provider took ${secs} s to ${v.status === 'failed' ? 'answer with a refusal' : 'answer'}. That wait is on the provider's side, not this server's.${v.status === 'failed' ? ' Nothing was read by the AI, so your whole sentence was searched as typed.' : ''}` })
    } else if (s.id === 'search') {
      out.push({ stage: s.id, seconds: v.seconds, text: `Matching took ${secs} s, longer than usual. The server did not record a reason.` })
    } else {
      out.push({ stage: s.id, seconds: v.seconds, text: `This step took ${secs} s, longer than usual. The server did not record a reason.` })
    }
  }
  return out.sort((a, b) => b.seconds - a.seconds)
}

/** Under the time bar: the notes, with a dashed arrow pointing up at the band of the slowest step (`at` = where that band's middle is, in percent of the bar). */
export function WhyBlock({ notes, at }: { notes: Why[]; at: number | null }) {
  if (notes.length === 0) return null
  return (
    <div className="why-block">
      {at != null && (
        <svg className="why-up" aria-hidden="true" style={{ left: `calc(${Math.min(Math.max(at, 4), 96)}% - 12px)` }} viewBox="0 0 24 34" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 32 V8" strokeDasharray="4 5" /><path d="M6 14 L12 6 L18 14" />
        </svg>
      )}
      {notes.slice(0, 2).map((n) => (
        <p key={n.stage}><strong>Step {STEPS.findIndex((s) => s.id === n.stage) + 1}, {STEPS.find((s) => s.id === n.stage)?.name.toLowerCase()}: {f(n.seconds)} s.</strong> {n.text}</p>
      ))}
    </div>
  )
}
