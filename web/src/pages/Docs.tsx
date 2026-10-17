// The Docs page: the story of one prompt step by step (from a recorded run), decisions, machines, the project map, limits, how to run it.
import { useMemo, useState } from 'react'
import mapData from '../content/map.json'
import { buildDecisions, buildLimits, buildSteps, RUN_IT, type StepDoc } from '../content/docs'
import { narrate } from '../content/story'
import { NAME } from '../brand'
import { RECORDED } from '../recorded'
import { Exact } from '../components/Plain'

const MARK: Record<StepDoc['helped'], { cls: string; label: string }> = {
  helped: { cls: 'done', label: 'helped' },
  'no clear effect': { cls: 'hatch', label: 'no clear effect' },
  'did not help': { cls: 'cross', label: 'did not help' },
  safety: { cls: 'dots', label: 'a safety gate' },
  plumbing: { cls: 'dots', label: 'presentation' },
}
const sec = (x: number | null) => (x == null ? '—' : x < 0.01 ? '<0.01' : x.toFixed(2))

function Story() {
  const steps = useMemo(() => buildSteps(), [])
  const [runId, setRunId] = useState(RECORDED.runs[2]?.id ?? RECORDED.runs[0].id)
  const run = RECORDED.runs.find((r) => r.id === runId) ?? RECORDED.runs[0]
  const told = useMemo(() => narrate(run), [run])
  return (
    <section id="story" aria-labelledby="story-h" className="doc-sec">
      <h2 id="story-h" className="doc-h">One prompt, step by step</h2>
      <p className="doc-lead">Pick a recorded run. Each step shows what happened in it, what we measured, and a mark for whether it earned its place.</p>
      <div className="chip-row" style={{ marginTop: 14 }} role="group" aria-label="Recorded run">
        {RECORDED.runs.map((r) => <button key={r.id} type="button" className="chip" aria-pressed={r.id === run.id} onClick={() => setRunId(r.id)}>{r.prompt.length > 46 ? `${r.prompt.slice(0, 44)}…` : r.prompt}</button>)}
      </div>
      <p className="mono dim" style={{ margin: '10px 0 0', fontSize: 13 }}>Recorded {RECORDED.recorded_at} · total {run.wall_seconds.toFixed(1)} s · author's blind rating of raw search on this prompt: {run.author_rating_of_raw_search ?? 'none'}</p>
      <p className="doc-p" style={{ marginTop: 14, maxWidth: '90ch' }}>
        <strong>Match score</strong> (technical name NDCG@10) is a 0 to 1 score for how high the right products sit in the top 10. <strong>Ratings</strong> are 0 to 2 (0 bad, 1 okay, 2 good), given by one person who did not know which method made the results.
      </p>
      <div className="legend-row" style={{ marginTop: 10 }}>
        <span><i style={{ background: 'var(--ink)' }} />helped</span>
        <span><i className="hatch" />no clear effect</span>
        <span><i className="cross" />did not help</span>
        <span><i style={{ border: '1.5px dotted var(--z4)' }} />gate or presentation</span>
      </div>
      <ol className="story">
        {steps.map((s, i) => {
          const t = told[s.id]
          const m = MARK[s.helped]
          return (
            <li key={s.id} className="story-step">
              <div className="story-head">
                <div className={`tile ${m.cls === 'dots' ? '' : m.cls}`} style={m.cls === 'dots' ? { border: '1.5px dotted var(--z4)' } : undefined} aria-hidden="true" />
                <h3 style={{ margin: 0, fontSize: 22 }}>{i + 1}. {s.title}</h3>
                <span className="mono" style={{ marginLeft: 'auto', fontSize: 17 }}>{sec(t.seconds)} s</span>
              </div>
              <p className="doc-p" style={{ marginTop: 8, maxWidth: '90ch' }}><strong>{m.label}.</strong> {s.helpedWhy}</p>
              <details className="story-more">
                <summary>What happened in this run, what we measured, how it fails</summary>
                <div className="story-grid two">
                  <div><div className="lg dim">In this run</div>{t.lines.map((l, k) => <p key={k} className="doc-p">{l}</p>)}</div>
                  <div><div className="lg dim">What we measured</div>{s.measured.map((f, k) => <p key={k} className="doc-p">{f.text} <span className="mono dim" style={{ fontSize: 12 }}>{f.source}</span></p>)}</div>
                </div>
                <div className="story-grid two">
                  <div><div className="lg dim">What it does</div><p className="doc-p">{s.what}</p><div className="lg dim" style={{ marginTop: 10 }}>Why it exists</div><p className="doc-p">{s.why}</p></div>
                  <div><div className="lg dim">How it fails</div>{s.fails.map((f, k) => <p key={k} className="doc-p">{f}</p>)}<div className="lg dim" style={{ marginTop: 10 }}>Where the code is</div><p className="doc-p mono" style={{ fontSize: 13 }}>{s.code.join(' · ')}</p></div>
                </div>
              </details>
            </li>
          )
        })}
      </ol>
    </section>
  )
}

function Decisions() {
  const rows = useMemo(() => buildDecisions(), [])
  return (
    <div>
      <div>
        {rows.map((d, i) => (
          <div key={i} className="dec-row">
            <div className="mono dim" style={{ fontSize: 13 }}>{d.date}</div>
            <div><div style={{ fontWeight: 700, fontSize: 16 }}>{d.decision}</div><p className="doc-p">{d.why}{d.source && <> <span className="mono dim" style={{ fontSize: 12 }}>{d.source}</span></>}</p></div>
          </div>
        ))}
      </div>
    </div>
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
    <div>
      <div>{items.map(([a, b]) => <div key={a} className="dec-row"><div style={{ fontWeight: 700 }}>{a}</div><p className="doc-p" style={{ margin: 0 }}>{b}</p></div>)}</div>
      <p className="doc-p" style={{ marginTop: 14 }}>Every measured failure (a dead shard, a slow shard, a dead copy, overload, ingestion with a machine off) is on the <a href="#/system">System page</a>, with the AWS recording first.</p>
    </div>
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
    <div>
      <p className="doc-lead">{total} files. Each description is the first line of the file itself, and "uses" comes from a code graph built on this computer from the files themselves ({mapData.graph.nodes.toLocaleString('en')} nodes, {mapData.graph.links.toLocaleString('en')} links; nothing was sent anywhere).</p>
      <div className="chip-row" style={{ marginTop: 14 }} role="group" aria-label="Area">
        {areas.map((a) => <button key={a.id} type="button" className="chip" aria-pressed={!q.trim() && a.id === area} onClick={() => { setQ(''); setArea(a.id) }}>{a.title} · {a.files.length}</button>)}
      </div>
      <div style={{ marginTop: 14 }}>
        <label htmlFor="mapq" className="lg dim">Find a file or a word</label>
        <input id="mapq" className="map-q" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="for example: queue" autoComplete="off" />
      </div>
      {!q.trim() && <p className="doc-p dim" style={{ marginTop: 10 }}>{cur.what}</p>}
      <div style={{ marginTop: 8 }}>
        {shown.length === 0 && <p className="doc-p">No file matches.</p>}
        {shown.map((f) => (
          <div key={f.path} className="map-row">
            <div className="mono" style={{ fontSize: 13, wordBreak: 'break-all' }}>{f.path}<div className="dim">{f.lines} lines</div></div>
            <div>
              <p className="doc-p" style={{ margin: 0 }}>{f.does}</p>
              {(f.uses.length > 0 || usedBy.has(f.path)) && (
                <p className="mono dim" style={{ margin: '4px 0 0', fontSize: 12, lineHeight: '17px' }}>
                  {f.uses.length > 0 && <>uses {f.uses.map((u) => u.split('/').pop()).join(', ')}</>}
                  {f.uses.length > 0 && usedBy.has(f.path) && ' · '}
                  {usedBy.has(f.path) && <>used by {usedBy.get(f.path)!.map((u) => u.split('/').pop()).join(', ')}</>}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/** A reference section: one plain sentence always visible, the detail one click away. */
function RefSection({ id, title, summary, label, children }: { id: string; title: string; summary: string; label: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="doc-sec" style={{ marginTop: 56 }}>
      <h2 id={`${id}-h`} className="doc-h">{title}</h2>
      <p className="plain" style={{ fontSize: 17, lineHeight: '26px' }}>{summary}</p>
      <Exact label={label}>{children}</Exact>
    </section>
  )
}

export function DocsPage() {
  const limits = useMemo(() => buildLimits(), [])
  const toc = [['story', 'One run, step by step'], ['decisions', 'Decisions'], ['machines', 'The machines'], ['map', 'Code files'], ['limits', 'Limits'], ['run', 'Run it yourself']]
  return (
    <main id="main" tabIndex={-1} className="wrap" style={{ paddingTop: 56, paddingBottom: 110 }}>
      <h1 className="voice" style={{ margin: 0, fontSize: 'clamp(48px, 6.5vw, 88px)', lineHeight: 1, letterSpacing: '-.015em', maxWidth: '16ch' }}>What happens to your words.</h1>
      <p className="doc-lead" style={{ marginTop: 22, fontSize: 19, lineHeight: '29px' }}>
        {NAME} turns a sentence about an outfit into products. This page follows one real run, step by step: what happened, what we measured, and where it can fail. <strong>Viewer</strong> (this page) replays real recorded runs. <strong>Lab</strong> runs on your own computer, with your own model or key.
      </p>
      <nav aria-label="On this page" className="chip-row" style={{ marginTop: 22 }}>
        {toc.map(([id, label]) => <a key={id} href={`#${id}`} className="chip" onClick={(e) => { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' }) }}>{label}</a>)}
      </nav>
      <Story />
      <RefSection id="decisions" title="Decisions, and why" summary="Eleven choices we made, each with its reason." label="Show the eleven decisions"><Decisions /></RefSection>
      <RefSection id="machines" title="The machines, and what happens when they fail" summary="Five parts: a words-to-numbers program, four slices of the product list, a coordinator, a queue for new products, and monitoring." label="Show the five parts"><Machines /></RefSection>
      <RefSection id="map" title="Every code file" summary="A searchable list of all the files in the project, each with a one-line description." label="Show all the files"><ProjectMap /></RefSection>
      <RefSection id="limits" title="What we cannot say" summary="The limits of these results, in plain words." label="Show the limits"><ul className="doc-list">{limits.map((l, i) => <li key={i}>{l}</li>)}</ul></RefSection>
      <RefSection id="run" title="Run it yourself" summary="Five commands. Your key, if you add one, stays on your computer." label="Show the commands">
        <p className="doc-lead">The data, photos and indexes are not in the repository because of their licences. Commands that need them say so.</p>
        <div>{RUN_IT.map((r) => <div key={r.cmd} className="cmd-row"><code className="mono">{r.cmd}</code><p className="doc-p" style={{ margin: 0 }}>{r.what}</p></div>)}</div>
        <p className="doc-p" style={{ marginTop: 14 }}>Then open the mode menu at the top right to switch to Lab and enter your own model key.</p>
      </RefSection>
    </main>
  )
}
