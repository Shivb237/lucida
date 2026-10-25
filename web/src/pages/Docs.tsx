// The "How it works" page (route #/docs): the journey of one recorded request through the six steps, the decisions with their reasons,
// then folded reference sections (two ways to use it, the machines, every code file, limits, how to run it).
// #/docs/<section> (or #/docs/<step id>) opens at that part: it scrolls there, opens its fold and moves focus to its heading.
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import mapData from '../content/map.json'
import { buildDecisions, buildLimits, buildOtherDecisions, buildSteps, RUN_IT, type DecisionCard, type StepDoc } from '../content/docs'
import { journey, narrate } from '../content/story'
import { bestRun, HOSTED_PHOTO_IDS, PHOTO_BASE, RECORDED, withPhotos, type RecordedRun } from '../recorded'
import { Picture } from '../components/Sheet'
import { JourneyCanvas } from '../components/JourneyCanvas'
import { Exact } from '../components/Plain'
import { SOURCE_LABEL, type ComposePayload, type ExpandPayload, type Hit, type OutfitPayload, type RequestPayload, type SearchPayload, type StageId, type StepEvent, type UnderstandPayload } from '../trace'
import '../story.css'

const calm = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
const MARK: Record<StepDoc['helped'], { cls: string; label: string }> = {
  helped: { cls: 'solid', label: 'Helped' },
  'no clear effect': { cls: 'hatch', label: 'No clear effect' },
  'did not help': { cls: 'cross', label: 'Did not help' },
  safety: { cls: 'dotted', label: 'A safety gate' },
  plumbing: { cls: 'dotted', label: 'Presentation' },
}
const sec = (x: number | null) => (x == null ? '—' : x < 0.01 ? '<0.01' : x.toFixed(2))
const STEP_IDS: StageId[] = ['request', 'understand', 'expand', 'search', 'compose', 'outfit']
const FOLDS = ['modes', 'machines', 'map', 'limits', 'run']

function payloadOf<T>(run: RecordedRun, stage: StageId): T | undefined {
  return run.events.find((e): e is StepEvent => e.kind === 'step' && e.stage === stage && e.status !== 'started')?.payload as T | undefined
}

/** A small labelled value, the record's own grammar: an Archivo label, then the value. */
function Tag({ label, children }: { label: string; children: ReactNode }) {
  return <div className="jr-tag"><span className="lg">{label}</span><span>{children}</span></div>
}

function Frame({ hit, picked, note, source = true }: { hit: Hit; picked: boolean; note?: string; source?: boolean }) {
  return (
    <figure className={`jr-frame${picked ? ' picked' : ''}`}>
      <div className="jr-photo"><Picture hit={hit} /></div>
      <figcaption>
        <span className="mono">{hit.score.toFixed(3)}</span>
        {picked ? <span>picked</span> : source ? <span>{SOURCE_LABEL[hit.source] ?? hit.source}</span> : null}
      </figcaption>
      {note && <div className="jr-frame-note">{note}</div>}
    </figure>
  )
}

/** The one real thing each step made in this run. */
function Artefact({ id, run }: { id: StageId; run: RecordedRun }) {
  const out = payloadOf<OutfitPayload>(run, 'outfit')
  const picked = new Set((out?.items ?? []).map((i) => i.pick.id))
  if (id === 'request') {
    const r = payloadOf<RequestPayload>(run, 'request')
    return <div className="jr-tags"><Tag label="Safety check">{r?.guard === 'allow' || !r?.guard ? 'allowed' : r.guard.replace(/_/g, ' ')}</Tag></div>
  }
  if (id === 'understand') {
    const u = payloadOf<UnderstandPayload>(run, 'understand')
    const pl = u?.plan
    if (!pl) return null
    return (
      <>
        <div className="jr-tags">
          <Tag label="For">{pl.gender}</Tag>
          {pl.occasion && <Tag label="Occasion">{pl.occasion}</Tag>}
          {pl.season && <Tag label="Season">{pl.season}</Tag>}
        </div>
        <ul className="jr-pieces" aria-label="The plan's pieces">
          {pl.pieces.map((p, i) => <li key={i}><span className="lg">{p.kind}</span><span>{p.search_text}</span></li>)}
        </ul>
      </>
    )
  }
  if (id === 'expand') {
    const x = payloadOf<ExpandPayload>(run, 'expand')
    return (
      <div className="jr-tags">
        <Tag label="Occasion read as">{x?.usages?.length ? x.usages.join(', ') : 'none'}</Tag>
        <Tag label="Added">{x?.notes?.length ? x.notes.join(' ') : 'nothing'}</Tag>
      </div>
    )
  }
  if (id === 'search') {
    const s = payloadOf<SearchPayload>(run, 'search')
    if (!s?.pieces?.length) return null
    return (
      <div className="jr-rows">
        {s.pieces.map((p) => (
          <div key={p.text} className="jr-row">
            <div className="lg jr-row-h">{p.kind} · {p.hits.length} found · {[...new Set(p.hits.map((h) => SOURCE_LABEL[h.source] ?? h.source))].join(', ')}</div>
            <div className="jr-frames">{p.hits.slice(0, 3).map((h) => <Frame key={h.id} hit={h} picked={picked.has(h.id)} source={false} />)}</div>
          </div>
        ))}
        <p className="jr-key">Number = closeness to the piece, higher is closer. First 3 shown.</p>
      </div>
    )
  }
  if (id === 'compose') {
    const c = payloadOf<ComposePayload>(run, 'compose')
    const j = journey(run)
    if (!c || !j.picks.length) return <div className="jr-tags"><Tag label="Skipped">{c?.reason ?? 'nothing to match'}</Tag></div>
    return (
      <div className="jr-tags">
        {j.picks.map((p) => <Tag key={p.id} label={p.kind}>{p.colour ?? 'unknown'}</Tag>)}
        <Tag label="Swapped">{`${c.changed ?? 0} of ${c.pieces ?? 0}`}</Tag>
      </div>
    )
  }
  const items = out?.items ?? []
  if (!items.length) return null
  return (
    <div className="jr-frames outfit">
      {items.map((it) => <Frame key={it.pick.id} hit={it.pick} picked note={`${it.kind}: ${it.reasons[0] ?? ''}`} />)}
    </div>
  )
}

function Journey({ onStep }: { onStep: (id: string) => void }) {
  const docs = useMemo(() => new Map(buildSteps().map((s) => [s.id, s])), [])
  const first = useMemo(() => bestRun(), [])
  const [runId, setRunId] = useState(first.id)
  const run = useMemo(() => withPhotos(RECORDED.runs.find((r) => r.id === runId) ?? first, PHOTO_BASE ? HOSTED_PHOTO_IDS : {}), [runId, first])
  const told = useMemo(() => narrate(run), [run])
  const path = useMemo(() => journey(run), [run])
  const [active, setActive] = useState(0)
  const [phone, setPhone] = useState(() => window.matchMedia('(max-width: 900px)').matches)
  const list = useRef<HTMLOListElement>(null)

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 900px)')
    const on = () => setPhone(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  // the step crossing the reading line (a band just above the middle of the screen) is the one the rail and the drawing show
  useEffect(() => {
    const els = [...(list.current?.querySelectorAll<HTMLElement>('[data-step]') ?? [])]
    const io = new IntersectionObserver((entries) => {
      const hit = entries.filter((e) => e.isIntersecting).map((e) => Number((e.target as HTMLElement).dataset.step))
      if (hit.length) setActive(Math.max(...hit))
    }, { rootMargin: phone ? '-50% 0px -45% 0px' : '-40% 0px -55% 0px' })
    els.forEach((e) => io.observe(e))
    return () => io.disconnect()
  }, [phone, run])

  return (
    <section id="story" aria-labelledby="story-h" className="st-chapter">
      <h2 id="story-h" tabIndex={-1} className="st-h2">One recorded request</h2>
      <p className="jr-prompt">“{run.prompt}”</p>
      <p className="jr-meta"><span className="mono">{run.wall_seconds.toFixed(2)} s</span> in all, recorded <span className="mono">{RECORDED.recorded_at}</span>.</p>
      <details className="jr-choose">
        <summary>Follow another recorded request</summary>
        <div className="chip-row" role="group" aria-label="Recorded request">
          {RECORDED.runs.map((r) => <button key={r.id} type="button" className="chip" aria-pressed={r.id === run.id} onClick={() => setRunId(r.id)}>{r.prompt.length > 46 ? `${r.prompt.slice(0, 44)}…` : r.prompt}</button>)}
        </div>
      </details>

      <div className="jr-grid">
        <aside className="jr-aside" aria-label="The six steps">
          <ol className="jr-rail">
            {STEP_IDS.map((id, i) => (
              <li key={id}>
                <button type="button" aria-current={active === i ? 'step' : undefined} onClick={() => onStep(id)}>
                  <span className="mono">{i + 1}</span><span>{docs.get(id)?.title}</span><span className="mono jr-rail-s">{sec(told[id].seconds)} s</span>
                </button>
              </li>
            ))}
          </ol>
          <JourneyCanvas step={active} journey={path} height={phone ? 240 : 320} />
        </aside>
        <ol className="jr-steps" ref={list}>
          {STEP_IDS.map((id, i) => {
            const d = docs.get(id)!
            const t = told[id]
            const m = MARK[d.helped]
            return (
              <li key={id} id={`step-${id}`} data-step={i} className={`jr-step${active === i ? ' on' : ''}`}>
                <div className="jr-step-head">
                  <h3 tabIndex={-1}><span className="mono">{i + 1}</span> {d.title}</h3>
                  <span className="mono jr-sec">{sec(t.seconds)} s</span>
                </div>
                <p className="jr-say">{d.short} {t.headline}</p>
                <div className="jr-art"><Artefact id={id} run={run} /></div>
                <Exact label="What we measured, and how it fails">
                  <p className="jr-mark"><span className={`st-mark ${m.cls}`} aria-hidden="true" /> <strong>{m.label}.</strong> {d.helpedWhy}</p>
                  <div className="jr-more">
                    <div><div className="lg dim">In this run</div>{t.lines.map((l, k) => <p key={k}>{l}</p>)}</div>
                    <div><div className="lg dim">What we measured</div>{d.measured.length ? d.measured.map((f, k) => <p key={k}>{f.text} <span className="mono dim jr-src">{f.source}</span></p>) : <p>Nothing measured for this step.</p>}</div>
                    <div><div className="lg dim">How it fails</div>{d.fails.map((f, k) => <p key={k}>{f}</p>)}</div>
                    <div><div className="lg dim">Where the code is</div><p className="mono jr-src">{d.code.join(' · ')}</p></div>
                  </div>
                  <p className="jr-key">Marks here say whether a step earned its place: solid helped, hatched no clear effect, dotted a gate or presentation.</p>
                </Exact>
              </li>
            )
          })}
        </ol>
      </div>
    </section>
  )
}

function Card({ d }: { d: DecisionCard }) {
  const mark = d.verdict === 'helped' ? 'solid' : d.verdict === 'hurt' ? 'cross' : d.verdict ? 'hatch' : null
  return (
    <li className="dc-card">
      <p className="dc-what">{d.decision}</p>
      <p className="dc-why">{d.reason}</p>
      {d.href && (
        <a className="dc-link" href={d.href}>
          {mark && <span className={`st-mark ${mark}`} aria-hidden="true" />}
          {d.claim ? <>Evidence{d.verdictLabel ? `: ${d.verdictLabel.toLowerCase()}` : ''}</> : 'See the System page'} <span aria-hidden="true">→</span>
        </a>
      )}
    </li>
  )
}

function Decisions() {
  const cards = useMemo(() => buildDecisions(), [])
  const more = useMemo(() => buildOtherDecisions(), [])
  return (
    <section id="decisions" aria-labelledby="decisions-h" className="st-chapter">
      <h2 id="decisions-h" tabIndex={-1} className="st-h2">Decisions, and why</h2>
      {/* the four choices the project exists to test stay in view; the rest wait in one fold, so the page breathes */}
      <ul className="dc-grid" aria-label="The main choices, with the measured reason behind each">{cards.slice(0, 4).map((d) => <Card key={d.decision} d={d} />)}</ul>
      <details className="exact">
        <summary>{cards.length - 4 + more.length} more choices: the clothes map, colours, checks, likes, rules, licences and hosting</summary>
        <ul className="dc-grid">{[...cards.slice(4), ...more].map((d) => <Card key={d.decision} d={d} />)}</ul>
      </details>
    </section>
  )
}

function Machines() {
  const items = [
    ['Encoder', 'Turns words into numbers. One process; the busiest part, so the limit on how many searches run at once.'],
    ['Shards', 'Four processes each hold a quarter of the products, two copies of each in two zones.'],
    ['Router', 'Asks the encoder, then every shard at once; uses a second copy on failure or when the first is slow; merges; refuses past 12 in flight.'],
    ['Ingestion', 'New products arrive through a queue with a dead-letter queue; a write goes to both copies, repeats are ignored.'],
    ['Monitoring', 'One JSON log line per request with a ticket number that travels to every process; metric filters, a dashboard and alarms.'],
  ]
  return (
    <>
      {items.map(([a, b]) => <div key={a} className="st-row"><div className="st-row-h">{a}</div><p>{b}</p></div>)}
      <p className="st-p">Every measured failure is on the <a href="#/system">System page</a>.</p>
    </>
  )
}

type MapFile = { path: string; does: string; lines: number; uses: string[] }
type MapArea = { id: string; title: string; what: string; files: MapFile[] }

function ProjectMap() {
  const areas = mapData.areas as MapArea[]
  const [area, setArea] = useState(areas[0].id)
  const [q, setQ] = useState('')
  const usedBy = useMemo(() => {
    const m = new Map<string, string[]>()
    for (const a of areas) for (const f of a.files) for (const u of f.uses) m.set(u, [...(m.get(u) ?? []), f.path])
    return m
  }, [areas])
  const cur = areas.find((a) => a.id === area) ?? areas[0]
  const shown = q.trim() ? areas.flatMap((a) => a.files).filter((f) => `${f.path} ${f.does}`.toLowerCase().includes(q.trim().toLowerCase())) : cur.files
  const total = areas.reduce((n, a) => n + a.files.length, 0)
  return (
    <>
      <p className="st-p">{total} files. Each description is the file's own first line. "Uses" comes from its import lines ({mapData.graph.links.toLocaleString('en')} links between {mapData.graph.nodes.toLocaleString('en')} files).</p>
      <div className="chip-row st-gap" role="group" aria-label="Area">
        {areas.map((a) => <button key={a.id} type="button" className="chip" aria-pressed={!q.trim() && a.id === area} onClick={() => { setQ(''); setArea(a.id) }}>{a.title} · {a.files.length}</button>)}
      </div>
      <div className="st-gap">
        <label htmlFor="mapq" className="lg dim">Find a file or a word</label>
        <input id="mapq" className="map-q" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="for example: queue" autoComplete="off" />
      </div>
      {!q.trim() && <p className="st-p dim">{cur.what}</p>}
      <div>
        {shown.length === 0 && <p className="st-p">No file matches.</p>}
        {shown.map((f) => (
          <div key={f.path} className="st-row map">
            <div className="mono st-path">{f.path}<div className="dim">{f.lines} lines</div></div>
            <div>
              <p>{f.does}</p>
              {(f.uses.length > 0 || usedBy.has(f.path)) && (
                <p className="mono dim st-uses">
                  {f.uses.length > 0 && <>uses {f.uses.map((u) => u.split('/').pop()).join(', ')}</>}
                  {f.uses.length > 0 && usedBy.has(f.path) && ' · '}
                  {usedBy.has(f.path) && <>used by {usedBy.get(f.path)!.map((u) => u.split('/').pop()).join(', ')}</>}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </>
  )
}

const START = [
  { cmd: 'scripts/setup_env.sh', what: 'Once: set up Python and the libraries.' },
  { cmd: 'ollama pull qwen3:4b-instruct', what: 'Once: download the AI model (skip it if you will use your own key).' },
  { cmd: '.venv/bin/uvicorn genkart.server:app --app-dir src --port 8000', what: 'Start the server and keep it running.' },
  { cmd: 'cd web && npm ci && npm run dev', what: 'Start this site. It finds the server by itself.' },
]

function Modes() {
  return (
    <>
      <div className="st-two">
        <div className="st-card">
          <h3>Replay</h3>
          <p>Real runs, recorded on {RECORDED.recorded_at}, play back in the page. Nothing is searched, installed or sent.</p>
          <p>No key is needed. You miss nothing needed to judge the work.</p>
        </div>
        <div className="st-card">
          <h3>Try it live</h3>
          <p>{PHOTO_BASE ? 'A hosted Lab searches your own words. It sleeps when unused, so the first visit takes about 45 seconds.' : 'Search your own words on your own computer, with the commands below.'}</p>
          <p>To have an AI read your words, choose one under <strong>AI model</strong> at the top right. A key stays in the tab's memory only.</p>
          {PHOTO_BASE && <p>Each photo costs the author a little cloud money, so please do not reload in a loop.</p>}
        </div>
      </div>
      <div className="lg dim st-gap">Start it on your own computer</div>
      {START.map((r) => <div key={r.cmd} className="st-row cmd"><code className="mono">{r.cmd}</code><p>{r.what}</p></div>)}
      <p className="st-p">Then open <code className="mono">http://localhost:5173</code> and choose <strong>Try it live</strong>.</p>
    </>
  )
}

/** A folded reference section: its heading and one plain line are the summary; the rest opens on request. */
function Fold({ id, title, summary, children }: { id: string; title: string; summary: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="st-fold">
      <details>
        <summary><span className="st-fold-t"><h2 id={`${id}-h`} tabIndex={-1} className="st-fold-h">{title}</h2><span className="st-fold-s">{summary}</span></span></summary>
        <div className="st-fold-body">{children}</div>
      </details>
    </section>
  )
}

export function DocsPage({ sub = '' }: { sub?: string }) {
  const limits = useMemo(() => buildLimits(), [])
  /** Scroll to a part of the page, open its fold, and move focus to its heading (without a second scroll). */
  const go = useCallback((target: string, share = true) => {
    const id = (STEP_IDS as string[]).includes(target) ? `step-${target}` : target
    const el = document.getElementById(id)
    if (!el) return
    const fold = el.querySelector('details')
    if (fold && FOLDS.includes(id)) fold.open = true
    el.scrollIntoView({ behavior: calm() ? 'auto' : 'smooth', block: 'start' })
    el.querySelector<HTMLElement>('h2, h3')?.focus({ preventScroll: true })
    if (share) history.replaceState(history.state, '', `#/docs/${target}`)
  }, [])
  // #/docs/<part>: go there once the page has drawn, and again when the address changes; a pending jump is cancelled on the next one
  useEffect(() => {
    if (!sub) return
    const t = window.setTimeout(() => go(sub, false), 0)
    return () => window.clearTimeout(t)
  }, [sub, go])
  const toc: [string, string][] = [['story', 'The journey'], ['decisions', 'Decisions'], ['modes', 'Two ways to use it'], ['machines', 'The machines'], ['map', 'Code files'], ['limits', 'Limits'], ['run', 'Run it yourself']]
  return (
    <main id="main" tabIndex={-1} className="wrap st-page">
      <h1 className="voice st-h1">The journey of one request.</h1>
      <p className="plain st-lead">Follow one real request through six steps. Each step shows what it made.</p>
      <nav aria-label="On this page" className="chip-row st-toc">
        {toc.map(([id, label]) => <button key={id} type="button" className="chip" aria-current={sub === id ? 'location' : undefined} onClick={() => go(id)}>{label}</button>)}
      </nav>
      <Journey onStep={(id) => go(id)} />
      <Decisions />
      <div className="st-folds">
        <h2 className="st-h2">Reference</h2>
        <Fold id="modes" title="Two ways to use it" summary="Replay shows recorded runs. Try it live searches your own words."><Modes /></Fold>
        <Fold id="machines" title="The machines" summary="Five parts, and what each does when another fails."><Machines /></Fold>
        <Fold id="map" title="Every code file" summary="A searchable list of the project's files, one line each."><ProjectMap /></Fold>
        <Fold id="limits" title="What we cannot say" summary="The limits of these results, in plain words."><ul className="st-list">{limits.map((l, i) => <li key={i}>{l}</li>)}</ul></Fold>
        <Fold id="run" title="Run it yourself" summary={`${RUN_IT.length} commands. A key, if you add one, stays on your computer.`}>
          <p className="st-p">The data, photos and indexes are not in the repository, because of their licences. Commands that need them say so.</p>
          {RUN_IT.map((r) => <div key={r.cmd} className="st-row cmd"><code className="mono">{r.cmd}</code><p>{r.what}</p></div>)}
          <p className="st-p">Then choose <strong>Try it live</strong> at the top right. Pick your own model under <strong>AI model</strong>.</p>
        </Fold>
      </div>
    </main>
  )
}
