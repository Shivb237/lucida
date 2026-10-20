// Recorded runs for the public Viewer: real pipeline traces made by scripts/record_runs.py, with no photos.
// They replay in the same event shape the live server streams, so one screen renders both.
import data from './recorded/runs.json'
import hostedIds from './recorded/photo-ids.json'
import type { Hit, TraceEvent } from './trace'

export type Rating = 'good' | 'okay' | 'bad' | null
export type RecordedRun = {
  id: string
  prompt: string
  test_set: number
  prompt_no: number
  author_rating_of_raw_search: Rating
  author_rating_of_plan: Rating
  plain?: { seconds: number; hits: Hit[] }       // the same sentence searched as typed, no plan
  wall_seconds: number
  events: TraceEvent[]
}
import type { Resources } from './components/CostPanel'
export type RecordedSet = { recorded_at: string; where: string; resources: Resources; understand_model: string; note: string; runs: RecordedRun[] }

export const RECORDED = data as unknown as RecordedSet
export type Pace = 'recorded' | 'fast'

/** The public Viewer has no photos of its own: with VITE_PHOTO_BASE set (the hosted Lab's address) the Marqo ones load from there, the rest stay placeholders. */
/** A static build (VITE_VIEWER=1) or ?mode=viewer never looks for a server of its own: it replays recorded runs only. */
export const VIEWER_ONLY = import.meta.env.VITE_VIEWER === '1' || new URLSearchParams(window.location.search).get('mode') === 'viewer'
export const PHOTO_BASE = ((import.meta.env.VITE_PHOTO_BASE as string | undefined) ?? '').replace(/\/$/, '')
/** The run the front door plays: one whose every outfit photo can be shown (so the first thing a visitor sees has no sketches); without photos, the old default. */
export function bestRun(): RecordedRun {
  const fallback = RECORDED.runs[2] ?? RECORDED.runs[0]
  if (!PHOTO_BASE) return fallback
  const picks = (r: RecordedRun) => r.events.flatMap((e) => (e.kind === 'step' && e.stage === 'outfit' && e.status === 'done' ? ((e.payload as { items?: { pick: { id: string } }[] }).items ?? []).map((i) => i.pick.id) : []))
  return RECORDED.runs.find((r) => { const p = picks(r); return p.length > 0 && p.every((id) => id in HOSTED_PHOTO_IDS) }) ?? fallback
}

let woken = false
/** Wakes the sleeping hosted Lab (a no-body request, no answer needed); the photos only need the container, not the search model, so /api/health is enough. Once per page. */
export function wakeHostedLab(): boolean {
  if (!PHOTO_BASE) return false
  if (!woken) { woken = true; fetch(`${PHOTO_BASE}/api/health`, { mode: 'no-cors' }).catch(() => {}) }
  return true
}
export const HOSTED_PHOTO_IDS = PHOTO_BASE ? (hostedIds as Record<string, string>) : {}

/** Points each recorded product at the photo on THIS computer, when the local server knows it (map: published id -> real id). Without a map the tiles stay placeholders. */
export function withPhotos(run: RecordedRun, map: Record<string, string>): RecordedRun {
  const pic = <T extends { id: string; image: string }>(h: T): T => (map[h.id] ? { ...h, image: `${PHOTO_BASE}/api/image/${map[h.id]}` } : h)
  const events = run.events.map((e) => {
    if (e.kind !== 'step' || e.status !== 'done') return e
    const p = e.payload as Record<string, unknown>
    if (e.stage === 'search') return { ...e, payload: { ...p, pieces: (p.pieces as { hits: { id: string; image: string }[] }[]).map((x) => ({ ...x, hits: x.hits.map(pic) })) } }
    if (e.stage === 'outfit') return { ...e, payload: { ...p, items: ((p.items ?? []) as { pick: { id: string; image: string } }[]).map((i) => ({ ...i, pick: pic(i.pick) })) } }
    return e
  })
  return { ...run, events, plain: run.plain && { ...run.plain, hits: run.plain.hits.map(pic) } }
}

/** Replays one recorded run. 'recorded' waits the real seconds each step took; 'fast' gives every step a short fixed beat. Returns a function that stops it. */
export function playRecorded(run: RecordedRun, pace: Pace, onEvent: (e: TraceEvent) => void, onDone: () => void): () => void {
  const timers: number[] = []
  let t = 0
  let openStage: string | null = null
  for (const e of run.events) {
    if (e.kind === 'end') { const at = t; timers.push(window.setTimeout(() => { onEvent(e); onDone() }, at)); continue }
    if (e.status === 'started') {
      timers.push(window.setTimeout(() => onEvent(e), t))
      openStage = e.stage
      continue
    }
    t += pace === 'fast' ? (openStage === e.stage ? 380 : 140) : Math.max(openStage === e.stage ? (e.seconds ?? 0) * 1000 : 0, 120)
    timers.push(window.setTimeout(() => onEvent(e), t))
    openStage = null
  }
  return () => timers.forEach((x) => window.clearTimeout(x))
}
