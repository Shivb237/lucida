// The Search page: live runs, the demo replay, and in the Viewer the recorded runs.
import { useEffect, useRef, useState } from 'react'
import { getExamples, streamSearch, type Health } from '../api'
import { describe, type BrainSetting } from '../brain'
import { NAME } from '../brand'
import { ComposePanel, GraphSheet, LiveStrip, PlanCard, RecordTable, SearchPanel, TimeStrip, fmt, type Clock } from '../components/Panels'
import { CostPanel, type Resources } from '../components/CostPanel'
import { CompareCard, type Plain } from '../components/CompareCard'
import { FrontDoor } from '../components/FrontDoor'
import { RefinePanel } from '../components/Refine'
import { ContactSheet, Glance, Print, type Mode } from '../components/Sheet'
import { Sentence } from '../components/Sentence'
import { DEMO_QUERY, playDemo } from '../demo'
import { bestRun, HOSTED_PHOTO_IDS, PHOTO_BASE, playRecorded, RECORDED, wakeHostedLab, withPhotos, type Pace, type RecordedRun } from '../recorded'
import {
  emptySteps, STEPS, type OutfitPayload, type RequestPayload, type SearchPayload, type StageId, type StepState, type TraceEvent, type UnderstandPayload,
} from '../trace'


const dismissed = new Set<string>()   // notes a visitor closed: kept while the page is open, so changing page does not bring them back
/** The tape-coloured note, now with a way out: a 44px close button. */
function Notice({ id, style, children }: { id: string; style?: React.CSSProperties; children: React.ReactNode }) {
  const [, again] = useState(0)
  if (dismissed.has(id)) return null
  return (
    <div className="notice" style={style}>
      {children}
      <button type="button" className="notice-x" aria-label="Dismiss this note" onClick={() => { dismissed.add(id); again((n) => n + 1) }}>
        <svg aria-hidden="true" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M2 2l10 10M12 2L2 12" /></svg>
      </button>
    </div>
  )
}

export function SearchPage({ health, viewer, brain }: { health: Health | null | undefined; viewer: boolean; brain: BrainSetting }) {
  const [query, setQuery] = useState(DEMO_QUERY)
  const [shown, setShown] = useState(DEMO_QUERY)
  const [mode, setMode] = useState<Mode>('idle')
  const [steps, setSteps] = useState<Record<StageId, StepState>>(emptySteps)
  const [running, setRunning] = useState(false)
  const [liked, setLiked] = useState<Set<string>>(new Set())   // products the visitor tapped 👍 on in a live run; forgotten with the next run
  const [slow, setSlow] = useState(false)               // a live run has taken more than 2 seconds: say why (a sleeping host loading its model)
  const [photoWait, setPhotoWait] = useState(false)     // the Viewer asked the hosted Lab for photos and none has arrived yet
  const [error, setError] = useState<string | null>(null)
  const [announce, setAnnounce] = useState('')
  const [rid, setRid] = useState('')
  const [t0, setT0] = useState<number | null>(null)       // the stopwatch: starts when a run starts, ticks while it runs, stops at its end
  const [endAt, setEndAt] = useState<number | null>(null)
  const [now, setNow] = useState(0)
  const [startedAt, setStartedAt] = useState<Partial<Record<StageId, number>>>({})
  useEffect(() => {
    if (!running) return
    const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches   // a stopwatch is motion: once a second for people who asked for less
    const t = window.setInterval(() => setNow(performance.now()), calm ? 1000 : 100)
    return () => window.clearInterval(t)
  }, [running])
  const [examples, setExamples] = useState<string[]>([])
  const [pace, setPace] = useState<Pace>('recorded')
  const [picked_run, setPickedRun] = useState<RecordedRun | null>(null)
  const stop = useRef<(() => void) | null>(null)

  useEffect(() => { if (health) getExamples().then(setExamples) }, [health])
  const photos = useRef<Record<string, string>>({})
  const [plainLive, setPlainLive] = useState<{ q: string; value: Plain | null } | null>(null)   // plain search of the same sentence, for the comparison
  const [resources, setResources] = useState<Resources | null>(null)   // what this computer is holding in memory, read after a live run
  const [photosReady, setPhotosReady] = useState(false)
  useEffect(() => { if (import.meta.env.VITE_VIEWER === '1') { photos.current = HOSTED_PHOTO_IDS; setPhotosReady(true); return }   // a public Viewer build asks no server; Marqo photos come from the hosted Lab when its address is set
    fetch('/api/recorded-photos').then((r) => (r.ok ? r.json() : {})).then((m) => { photos.current = m }).catch(() => {}).finally(() => setPhotosReady(true)) }, [])   // only a computer that has the photos answers
  useEffect(() => {
    if (mode !== 'live' || !running) return
    const t = window.setTimeout(() => setSlow(true), 2000)
    return () => window.clearTimeout(t)
  }, [mode, running])
  useEffect(() => {
    if (!photoWait) return
    const done = () => setPhotoWait(false)
    window.addEventListener('genkart-photo', done, { once: true })
    const t = window.setTimeout(done, 90000)       // never stay up for ever: after 90 s the tiles are sketches and that is that
    return () => { window.removeEventListener('genkart-photo', done); window.clearTimeout(t) }
  }, [photoWait])
  const auto = useRef(false)
  // on a real unmount (and on React's development-mode test unmount) stop the replay and allow a link-started run to start again
  useEffect(() => () => { stop.current?.(); auto.current = false }, [])

  // a link can start a run: /?demo=1 plays the demo replay, /?q=some+request runs that request once the server answers
  useEffect(() => {
    if (auto.current || health === undefined || !photosReady) return
    const params = new URLSearchParams(window.location.search)
    const wanted = RECORDED.runs.find((r) => r.id === params.get('run'))
    if (params.has('demo')) { auto.current = true; runDemo() }
    else if (wanted && viewer) { auto.current = true; runRecorded(wanted) }
    else if (params.get('q') && health) { auto.current = true; setQuery(params.get('q')!); runLive(params.get('q')!) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [health, photosReady])

  useEffect(() => {
    if (mode !== 'live' || running || steps.request.status === 'waiting') return
    if (!health?.hosted) fetch('/api/resources').then((r) => (r.ok ? r.json() : null)).then(setResources).catch(() => setResources(null))
    if (steps.request.status === 'done') {
      const asked = shown
      fetch(`/api/plain?${new URLSearchParams({ q: asked })}`).then((r) => (r.ok ? r.json() : null)).then((v) => setPlainLive({ q: asked, value: v })).catch(() => setPlainLive({ q: asked, value: null }))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, running])

  const apply = (e: TraceEvent) => {
    setRid(e.request_id)
    if (e.kind === 'end') { setEndAt(performance.now()); setRunning(false); return }
    if (e.status === 'started') setStartedAt((s) => ({ ...s, [e.stage]: performance.now() }))
    setSteps((s) => ({ ...s, [e.stage]: { status: e.status, seconds: e.seconds, payload: e.payload } }))
    const name = STEPS.find((s) => s.id === e.stage)?.name
    if (e.status === 'done') setAnnounce(`${name} finished in ${fmt(e.seconds, 2)} seconds`)
    if (e.status === 'failed') setAnnounce(`${name} failed`)
  }

  const stopRun = () => { stop.current?.(); setRunning(false); setEndAt(performance.now()) }   // a way out of any run, however long it is taking
  const skipToResult = () => {                                                                  // a replay at its recorded pace takes seconds: show the end now
    if (!picked_run) return
    stop.current?.()
    withPhotos(picked_run, photos.current).events.forEach(apply)
  }

  const start = (m: Mode, q: string) => {
    stop.current?.()
    const t = performance.now()
    // a run starts below the form: on a phone (or for a replay) bring it into view, so the clock and the first step are on screen
    if (m === 'recorded' || window.innerWidth <= 900) {
      const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches
      window.setTimeout(() => document.getElementById('step1')?.scrollIntoView({ behavior: calm ? 'auto' : 'smooth', block: 'start' }), 120)
    }
    setPlainLive(null); setSlow(false); setLiked(new Set())
    setMode(m); setShown(q); setSteps(emptySteps()); setRunning(true); setError(null); setT0(t); setNow(t); setEndAt(null); setStartedAt({})
  }
  const runLive = (q: string) => {
    if (!q.trim()) return
    if (!health) { setError('The server is not running, so nothing was searched. Start it, or play the demo replay.'); return }
    start('live', q.trim())
    stop.current = streamSearch(q.trim(), apply, (msg) => { setError(msg); setRunning(false) }, brain)
  }
  const runRecorded = (run: RecordedRun) => {
    setPickedRun(run); setQuery(run.prompt)
    if (wakeHostedLab()) setPhotoWait(true)
    start('recorded', run.prompt)
    stop.current = playRecorded(withPhotos(run, photos.current), pace, apply, () => setRunning(false))

  }
  const runDemo = () => {
    setQuery(DEMO_QUERY)
    start('demo', DEMO_QUERY)
    stop.current = playDemo(apply, () => setRunning(false))
  }

  const clock: Clock = { t0, endAt: endAt ?? (running ? null : now || null), now, startedAt }
  const demo = mode === 'demo'
  const live = mode === 'live'
  const recorded = mode === 'recorded'
  const under = steps.understand.status === 'done' || steps.understand.status === 'failed' ? (steps.understand.payload as unknown as UnderstandPayload) : null
  const search = steps.search.status === 'done' ? (steps.search.payload as unknown as SearchPayload) : null
  const outfit = steps.outfit.status === 'done' ? (steps.outfit.payload as OutfitPayload) : null
  const picked = new Set<string>(outfit?.items?.map((i) => i.pick.id) ?? [])
  const plan = under && !under.fell_back ? under.plan : null
  const req = steps.request.payload as RequestPayload
  const refused = steps.request.status === 'failed' && req.refused === true

  return (
    <main id="main" tabIndex={-1} className="wrap" style={{ paddingTop: 40, paddingBottom: 110 }}>
      <h1 className="sr-only">{NAME}: fashion search you can see inside</h1>
      {mode !== 'idle' && <LiveStrip steps={steps} mode={mode} clock={clock} running={running} onStop={stopRun} />}
      <p className="sr-only" aria-live="polite">{announce}</p>

      {viewer && mode === 'idle' && <FrontDoor viewer onWatch={() => runRecorded(bestRun())} />}
      {demo && (
        <Notice id="demo"><span className="lg">Demo data</span><span style={{ marginLeft: 10 }}>A made-up replay, drawn as flat sketches. No search was run and no number here is a result. Real numbers are on the Evidence page.</span></Notice>
      )}
      {viewer && (
        <Notice id="viewer" style={{ transform: 'rotate(.6deg)', marginTop: 36 }}>
          <span className="lg">Viewer</span>
          <span style={{ marginLeft: 10 }}>Real runs recorded on {RECORDED.recorded_at}, replayed. Nothing is searched now. To search your own words, open the mode menu at the top right.</span>
          {PHOTO_BASE ? (
            <span style={{ display: 'block', marginTop: 8 }}>Photos load live from the author's hosted Lab (credits and how to ask for a removal are at the bottom of the page). A sketch means a photo could not be loaded; the product shown is still the real search result. The hosted Lab sleeps when nobody uses it, so the first photos can take about 50 seconds (measured once: 47.5 s) and then arrive quickly. Each photo costs the author a small amount of cloud money (not measured), so please do not reload in a loop.</span>
          ) : (
            <span style={{ display: 'block', marginTop: 8 }}>This copy of the site has no hosted Lab linked, so product photos are not shown: those tiles stay as sketches.</span>
          )}
        </Notice>
      )}
      {photoWait && (
        <div className="notice" role="status"><span className="lg">Waking up</span><span style={{ marginLeft: 10 }}>Waking up the hosted Lab to fetch the photos. The first load can take about 45 seconds; until then the tiles show sketches.</span></div>
      )}
      {mode === 'live' && running && slow && steps.search.status !== 'done' && (
        <div className="notice" role="status"><span className="lg">Still working</span><span style={{ marginLeft: 10 }}>If this server was asleep, the first search after a quiet spell takes about 45 seconds while it loads the search model. After that a search takes about a second.</span></div>
      )}
      {health?.hosted && brain.kind === 'local' && (
        <Notice id="hosted" style={{ transform: 'rotate(.4deg)' }}>
          <span className="lg">Hosted Lab</span>
          <span style={{ marginLeft: 10 }}>This public Lab has no built-in AI model. Your whole sentence is searched as typed. To have an AI read it first, add your own API key in the mode menu (top right); the key is used for that one request and never saved.</span>
        </Notice>
      )}
      {health && !health.hosted && !health.ollama && (
        <Notice id="ollama" style={{ transform: 'rotate(.4deg)' }}>
          <span className="lg">Ollama off</span>
          <span style={{ marginLeft: 10 }}>Step 2 needs the local AI model. Start Ollama and install <code>qwen3:4b-instruct</code>. Until then your whole sentence is searched as typed.</span>
        </Notice>
      )}

      {viewer && (
        <section aria-label="Recorded runs" style={{ marginTop: 32 }}>
          <h2 style={{ margin: 0, fontSize: 20, lineHeight: '26px' }}>Pick a recorded run to watch</h2>
          <div className="run-list">
            {RECORDED.runs.map((r) => (
              <button key={r.id} type="button" className="run-item" aria-pressed={picked_run?.id === r.id} onClick={() => runRecorded(r)}>
                <span className="run-prompt">{r.prompt}</span>
                <span className="mono dim" style={{ fontSize: 12 }}>plain search rated {r.author_rating_of_raw_search ?? 'not rated'} by the author · {r.wall_seconds.toFixed(1)} s</span>
              </button>
            ))}
          </div>
          <div className="chip-row" style={{ marginTop: 14 }} role="group" aria-label="Replay speed">
            <span className="lg dim" style={{ marginRight: 4 }}>Replay at</span>
            <button type="button" className="chip" aria-pressed={pace === 'recorded'} onClick={() => setPace('recorded')}>the recorded pace</button>
            <button type="button" className="chip" aria-pressed={pace === 'fast'} onClick={() => setPace('fast')}>fast</button>
          </div>
        </section>
      )}
      {recorded && picked_run && (
        <p className="dim" style={{ margin: '14px 0 0', maxWidth: '78ch', fontSize: 14, lineHeight: '21px' }}>
          Recorded on {RECORDED.where} with model <span className="mono">{RECORDED.understand_model}</span>.
          The author's blind score ({picked_run.author_rating_of_raw_search ?? 'none'}) is for <em>plain search</em> of this request, so the outfit below may differ from the one scored.
        </p>
      )}
      {!viewer && <form className="req" style={{ marginTop: 32 }} onSubmit={(e) => { e.preventDefault(); runLive(query) }}>
        <label htmlFor="req" className="lg dim" style={{ width: '100%', marginBottom: 10 }}>What do you need to wear?</label>
        <input id="req" type="text" value={query} maxLength={300} onChange={(e) => setQuery(e.target.value)} autoComplete="off" />
        <button type="submit" className="btn-expose">{running && live ? 'Run again' : 'Search'}</button>
      </form>}
      {running && (
        <div className="run-controls" role="group" aria-label="Control this run">
          <button type="button" className="btn-line" onClick={stopRun}>Stop</button>
          {recorded && <button type="button" className="btn-line" onClick={skipToResult}>Skip to the result</button>}
        </div>
      )}
      {error && <p role="alert" style={{ margin: '12px 0 0', fontSize: 15, fontWeight: 600, display: 'flex', gap: 10, alignItems: 'center' }}><span className="tile cross" style={{ width: 16, height: 16, flex: 'none' }} aria-hidden="true" />{error}</p>}
      {!viewer && <div className="chip-row" style={{ marginTop: 14 }}>
        {examples.length > 0 && <span className="lg dim" style={{ marginRight: 4 }}>Try</span>}
        {examples.map((s) => <button key={s} type="button" className="chip" onClick={() => { setQuery(s); runLive(s) }}>{s}</button>)}
        <button type="button" className="chip" style={{ borderStyle: 'dashed' }} onClick={runDemo}>Play the demo replay</button>
      </div>}
      {health && !viewer && (
        <p className="lg dim" style={{ marginTop: 14 }}>
          Searching {health.backend === 'router' ? 'with the split system' : 'inside this program'} · the model {health.catalogue_loaded ? 'is loaded' : 'loads on your first search'}
        </p>
      )}
      {health && !viewer && (
        <p className="dim" style={{ margin: '8px 0 0', fontSize: 14, lineHeight: '21px' }}>
          The AI that reads your sentence: {describe(brain)}. Change it in the mode menu, top right.
        </p>
      )}

      {refused && (
        <div role="alert" className="notice" style={{ marginTop: 28, transform: 'none' }}>
          <span className="lg">Not searched</span>
          <span style={{ marginLeft: 10 }}>{req.message}</span>
          <span className="mono" style={{ display: 'block', marginTop: 6, fontSize: 12 }}>reason: {req.category}</span>
        </div>
      )}
      {!refused && req.note && <p className="lg dim" style={{ marginTop: 14 }}>{req.note}</p>}

      {outfit?.items && outfit.items.length > 0 && <Glance items={outfit.items} mode={mode} />}

      {mode !== 'idle' && (
        <>
          {!refused && (
            <section id="step1" aria-label="Your request" style={{ marginTop: 56, scrollMarginTop: 76 }}>
              <h2 className="lg dim step-h" style={{ marginBottom: 6 }}>Step 1 · your request</h2>
              <Sentence text={shown} plan={plan} animate={steps.understand.status === 'done'} />
              <PlanCard step={steps.understand} demo={demo} />
              <GraphSheet step={steps.expand} />
            </section>
          )}

          <section style={{ marginTop: 64, display: 'flex', flexWrap: 'wrap', gap: 48, alignItems: 'flex-start' }}>
            <RecordTable steps={steps} mode={mode} rid={rid} clock={clock} />
            <div style={{ flex: '1 1 440px', minWidth: 0 }}>
              <TimeStrip steps={steps} mode={mode} clock={clock} />
              <SearchPanel step={steps.search} />
            </div>
          </section>

          {search && search.pieces.length > 0 && <ContactSheet pieces={search.pieces} picked={picked} mode={mode} liked={liked} onLike={mode === 'live' && !running ? (id) => setLiked((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n }) : undefined} />}
          {mode === 'live' && !running && search && search.pieces.length > 0 && <RefinePanel query={shown} liked={liked} gender={((steps.understand.payload as { plan?: { gender?: string } } | undefined)?.plan?.gender) ?? null} />}
          <ComposePanel step={steps.compose} />
          {outfit?.items && outfit.items.length > 0 && <Print items={outfit.items} alreadyHas={outfit.already_has ?? []} mode={mode} />}
          {(live || recorded) && !running && outfit?.items && outfit.items.length > 0 && (
            <CompareCard
              plain={recorded ? withPhotos(picked_run!, photos.current).plain ?? null : plainLive && plainLive.q === shown ? plainLive.value : 'loading'}
              outfit={outfit.items} planSeconds={STEPS.reduce((n, s) => n + (steps[s.id].status === 'done' ? steps[s.id].seconds ?? 0 : 0), 0)}
              ratings={recorded && picked_run ? { plain: picked_run.author_rating_of_raw_search, plan: picked_run.author_rating_of_plan } : undefined} />
          )}
          {(live || recorded) && !running && steps.search.status === 'done' && (live || RECORDED.resources) && (
            <CostPanel steps={steps} mode={live ? 'live' : 'recorded'} brain={brain} live={resources} recorded={RECORDED.resources} />
          )}
          {(live || recorded) && steps.outfit.status === 'skipped' && <p style={{ marginTop: 48, fontSize: 16 }}>No outfit could be built: {(steps.outfit.payload as OutfitPayload).reason}.</p>}
        </>
      )}
      {mode === 'idle' && !viewer && <FrontDoor viewer={false} onWatch={() => {}} />}
    </main>
  )
}
