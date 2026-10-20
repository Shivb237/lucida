// The System page (route #/system): "We broke it on purpose". One sentence and the AWS drawing, then three experiments, each with
// its question, one measured number, what it means, and the exact tables in a fold. The other tests, the live state and the screenshots are folded below.
// #/system/<part> opens at that part: it scrolls there, opens its fold and moves focus to its heading.
import { useCallback, useEffect, type CSSProperties, type ReactNode } from 'react'
import evidence, { type Latency, type ReplicaRun } from 'virtual:evidence'
import type { Health } from '../api'
import { ArchMap, AwsIngestBody, FailoverBody, HealthyBody, OverloadBody } from './AwsTour'
import { Exact } from '../components/Plain'
import '../story.css'

const calm = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
const f = (n: number, d = 1) => n.toFixed(d)
const pc = (n: number) => `${Math.round(n * 100)}%`

/** p50 solid, p50 to p95 hatched, a tick at p99: the same grammar as the 95% range strips on the Evidence page. */
function LatencyBar({ p50, p95, p99, max }: { p50: number; p95: number; p99: number; max: number }) {
  const w = (v: number) => `${(Math.min(v, max) / max) * 100}%`
  return (
    <div className="lat" role="img" aria-label={`p50 ${f(p50, 0)} ms, p95 ${f(p95, 0)} ms, p99 ${f(p99, 0)} ms`}>
      <div className="p50" style={{ width: w(p50) }} />
      <div className="p95 hatch" style={{ left: w(p50), width: `${((Math.min(p95, max) - Math.min(p50, max)) / max) * 100}%` }} />
      <div className="p99" style={{ left: w(p99), width: 0 }} />
    </div>
  )
}

function PctBar({ v, cross }: { v: number | null | undefined; cross?: boolean }) {
  if (v == null) return <span className="mono dim">—</span>
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
      <div className={`pctbar${cross ? ' cross-fill' : ''}`} style={{ flex: 1 }} role="img" aria-label={pc(v)}><div style={{ width: pc(v) }} /></div>
      <span className="mono" style={{ fontSize: 15, width: 40, textAlign: 'right' }}>{pc(v)}</span>
    </div>
  )
}

function BarKey({ max }: { max: number }) {
  return <p className="bar-key">How to read the bars: all bars in this table share one scale, 0 to {f(max, 0)} ms. Solid = p50 (half of requests were faster), hatched = up to p95, tick = p99. Cross-hatched = partial answers.</p>
}

function Table({ head, rows, cols }: { head: string[]; rows: ReactNode[][]; cols: string }) {
  const style = { '--cols': cols } as CSSProperties
  return (
    <div style={{ marginTop: 16 }}>
      <div className="sys-head" style={style}>
        {head.map((h, i) => <div key={h} className="lg dim" style={{ textAlign: i === 0 || h === 'spread' ? 'left' : 'right' }}>{h}</div>)}
      </div>
      {rows.map((r, i) => (
        <div key={i} className="sys-row" style={style}>
          {r.map((c, j) => (
            <div key={j} className={`sys-cell${j > 1 ? ' num mono' : ''}`} data-label={j === 0 ? undefined : head[j]} style={{ fontSize: j === 0 ? 15 : 14, fontWeight: j === 0 ? 600 : 400 }}>{c}</div>
          ))}
        </div>
      ))}
    </div>
  )
}

function Node({ label, up, sub }: { label: string; up: boolean; sub?: string }) {
  return (
    <div>
      <div className={`node ${up ? 'up' : 'down'}`}><span className="lg">{label}</span></div>
      <div className="lg" style={{ fontSize: 13, marginTop: 4, textAlign: 'center', color: 'var(--z7)' }}>{sub ?? (up ? 'up' : 'down')}</div>
    </div>
  )
}

/** One experiment: the question, one measured number, what it means; the tables and charts one click away. */
function Experiment({ id, question, value, unit, label, means, children }: { id: string; question: string; value: string; unit?: string; label: string; means: ReactNode; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="sy-exp">
      <h2 id={`${id}-h`} tabIndex={-1} className="voice sy-q">{question}</h2>
      <div className="sy-exp-body">
        <p className="sy-num"><span className="mono sy-big">{value}{unit && <span className="sy-unit">{unit}</span>}</span><span className="sy-label">{label}</span></p>
        <p className="sy-means">{means}</p>
      </div>
      <Exact label="Show the exact numbers">{children}</Exact>
    </section>
  )
}

/** A folded section further down: heading and one line are the summary. */
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

const Src = ({ children }: { children: ReactNode }) => <p className="sy-src">Source: {children}</p>

export function SystemPage({ health, viewer }: { health: Health | null | undefined; viewer: boolean }) {
  const { e2e, chaos, replicas, ingest, equivalence } = evidence.system
  const aws = evidence.aws
  const fo = aws.failover
  const ov = aws.overload?.variants
  const r = health?.router ?? null
  const shards = r?.replicas ?? [[false, false], [false, false], [false, false], [false, false]]
  const slow = chaos ? Object.entries(chaos.slow_shard) : []
  const deadKeys = chaos ? Object.entries(chaos.quality_by_dead_shards).map(([k, v]) => ({ dead: JSON.parse(k) as number[], v })) : []
  const avg = (n: number) => { const g = deadKeys.filter((d) => d.dead.length === n); return g.length ? g.reduce((a, d) => a + d.v.ndcg10_marqo_labelled, 0) / g.length : null }
  const refMs = equivalence && 'reference_seconds' in equivalence ? (equivalence as unknown as { reference_seconds: number; queries: number; genders: number }) : null
  const maxOf = (xs: number[]) => Math.max(...xs, 1)
  const awsMs = aws.healthy.flatMap((p) => (p.total_ms == null ? [] : [p.total_ms])).sort((a, b) => a - b)
  const at = (q: number) => (awsMs.length ? awsMs[Math.min(awsMs.length - 1, Math.floor(q * awsMs.length))] : null)
  const awsTimes = { p50: at(0.5), p95: at(0.95) }
  // the backup-copy runs, found by their logged names: a slowed copy (with hedging) and a dead copy
  const repRows = replicas ? (Object.entries(replicas).filter(([, v]) => !Array.isArray(v)) as [string, ReplicaRun][]) : []
  const slowCopy = repRows.find(([k]) => /\+\d+ ms/.test(k))
  const deadCopy = repRows.find(([k]) => /^S1 /.test(k))
  const slowBy = slowCopy?.[0].match(/\+(\d+) ms/)?.[1]
  const noCopy = slowBy && chaos ? chaos.slow_shard[slowBy] : undefined

  const go = useCallback((id: string) => {
    const el = document.getElementById(id)
    if (!el) return
    const fold = el.querySelector(':scope > details')
    if (fold instanceof HTMLDetailsElement) fold.open = true
    el.scrollIntoView({ behavior: calm() ? 'auto' : 'smooth', block: 'start' })
    el.querySelector<HTMLElement>('h2')?.focus({ preventScroll: true })
  }, [])
  // #/system/<part>: App does not pass a sub to this page, so read it from the address (now and on later changes); a pending jump is cancelled
  useEffect(() => {
    let t = 0
    const open = () => {
      const id = decodeURIComponent(window.location.hash.match(/^#\/system\/([^/?]+)/)?.[1] ?? '')
      if (!id) return
      window.clearTimeout(t)
      t = window.setTimeout(() => go(id), 0)
    }
    open()
    window.addEventListener('hashchange', open)
    return () => { window.clearTimeout(t); window.removeEventListener('hashchange', open) }
  }, [go])

  return (
    <main id="main" tabIndex={-1} className="wrap st-page">
      <h1 className="voice st-h1">We broke it on purpose.</h1>
      <p className="plain st-lead">We ran the search on three AWS machines, then broke parts of it.</p>
      <figure className="sy-arch">
        <ArchMap />
        <figcaption>The coordinator (router) asks two machines. Each holds a full copy of the products, in a separate building (zone). This is a recording: the machines were deleted on 2026-10-16.</figcaption>
      </figure>

      <div className="sy-exps">
        {fo && fo.phases.before_stop && fo.phases.B_stopped_router_uses_A && (
          <Experiment id="machine-off" question="What if a whole machine is switched off?" value={String(fo.totals.errors)} label={`errors in ${fo.totals.searches} searches`}
            means={<>The router quietly used the copy on the other machine. A typical search went from <span className="mono">{f(fo.phases.before_stop.median_ms, 0)}</span> to <span className="mono">{f(fo.phases.B_stopped_router_uses_A.median_ms, 0)} ms</span>.</>}>
            <FailoverBody />
          </Experiment>
        )}
        {ov?.baseline && ov.v2 && (
          <Experiment id="overload" question="What if too many people search at once?" value={f(ov.v2.hardest_level.shed_p50_ms ?? 0, 0)} unit=" ms" label='to answer "busy, try again"'
            means={<>Before the fix, <span className="mono">{ov.baseline.hardest_level.errors}</span> of <span className="mono">{ov.baseline.hardest_level.requests}</span> searches failed at {ov.baseline.hardest_level.concurrency} at once. After it, <span className="mono">{ov.v2.hardest_level.errors}</span> failed: the extra ones heard "busy" fast.</>}>
            <OverloadBody />
          </Experiment>
        )}
        {slowCopy && (
          <Experiment id="slow-copy" question="What if one copy is slow, or dead?" value={f(slowCopy[1].p50, 0)} unit=" ms" label={`typical search, one copy ${slowBy} ms slow`}
            means={<>The router also asks the backup copy when the first is slow.{noCopy ? <> Without a backup, the same delay meant <span className="mono">{f(noCopy.p50, 0)} ms</span>.</> : null}{deadCopy ? <> A dead copy left <span className="mono">{deadCopy[1].partial}</span> incomplete answers.</> : null} Measured on one laptop.</>}>
            {(() => {
              const max = maxOf(repRows.map(([, v]) => v.p99))
              return (
                <>
                  <p className="st-p">With backup copies, the router asks a second copy at once when the first fails (failover), and also when the first is merely slow (hedging). The price: hedged requests do their slice's work twice.</p>
                  <Table cols="minmax(210px, 1.6fr) minmax(150px, 1.6fr) 64px 64px 80px 80px 70px" head={['scenario, 200 requests', 'spread', 'p50 ms', 'p99 ms', 'partial', 'failovers', 'hedged']}
                    rows={repRows.map(([k, x]) => [k.replace(/^S\d /, ''), <LatencyBar key="b" p50={x.p50} p95={x.p95} p99={x.p99} max={max} />, f(x.p50), f(x.p99), String(x.partial), String(x.failovers), String(x.hedged)])} />
                  <BarKey max={max} />
                  <Src>runs/chaos-replicas.summary.json</Src>
                </>
              )
            })()}
            {chaos && (() => {
              const rows: [string, Latency][] = [...(slow as [string, Latency][]).map(([ms, v]) => [`slice 2 slowed by +${ms} ms`, v] as [string, Latency]), ['one slice killed', chaos.dead_shard]]
              const max = maxOf(rows.map(([, v]) => v.p99))
              return (
                <>
                  <p className="st-p st-gap2">Without backup copies: a slow slice makes every search wait, up to the router's 800 ms limit. A dead slice fails fast, so the answer is quick but incomplete.{avg(0) != null && avg(1) != null && avg(2) != null && <> Match score (0 to 1, NDCG@10) on 852 labelled searches: <span className="mono">{f(avg(0)!, 3)}</span> with every slice, <span className="mono">{f(avg(1)!, 3)}</span> with one dead, <span className="mono">{f(avg(2)!, 3)}</span> with two dead.</>} A restarted slice rejoined in <span className="mono">{f(chaos.recovery.seconds_until_healthy)} s</span>.</p>
                  <Table cols="minmax(170px, 1.3fr) minmax(150px, 1.6fr) 64px 110px minmax(130px, 1.2fr) minmax(130px, 1.2fr)" head={['scenario', 'spread', 'p50 ms', 'partial answers', 'same top 4 as full', 'overlap with full']}
                    rows={rows.map(([label, v]) => [label, <LatencyBar key="b" p50={v.p50} p95={v.p95} p99={v.p99} max={max} />, f(v.p50, 0), `${v.partial ?? 0} of ${v.n}`,
                      <PctBar key="s" v={v.identical_to_full} cross={(v.partial ?? 0) > 0} />, <PctBar key="o" v={v.mean_overlap_with_full_top4} cross={(v.partial ?? 0) > 0} />])} />
                  <BarKey max={max} />
                  <Src>runs/chaos.summary.json</Src>
                </>
              )
            })()}
          </Experiment>
        )}
      </div>

      <div className="st-folds">
        <h2 className="st-h2">More from the tests</h2>
        {e2e && (
          <Fold id="split" title="Splitting the work changes nothing in the answers" summary={`${e2e.identical.toLocaleString('en')} of ${e2e.requests.toLocaleString('en')} searches gave the same top 4 as one program.`}>
            <p className="st-p">Splitting into 2, 4 or 8 slices matched every time too.{equivalence && Object.values(equivalence.by_shards ?? {}).length > 0 && <> That is {Object.values(equivalence.by_shards)[0].identical.toLocaleString('en')} cases each.</>} {e2e.partial} answers were incomplete.</p>
            {(() => {
              const rows = Object.entries(e2e.router_ms)
              const max = maxOf(rows.map(([, v]) => v[2]))
              return (
                <>
                  <Table cols="minmax(190px, 1.2fr) minmax(160px, 2fr) 64px 64px 64px" head={['milliseconds, inside the router', 'spread', 'p50', 'p95', 'p99']}
                    rows={rows.map(([k, v]) => [k === 'total' ? 'whole request' : k === 'shards' ? 'asking the slices (parallel)' : 'turning words into numbers',
                      <LatencyBar key="b" p50={v[0]} p95={v[1]} p99={v[2]} max={max} />, f(v[0]), f(v[1]), f(v[2])])} />
                  <BarKey max={max} />
                </>
              )
            })()}
            <p className="st-p"><strong>Honest note:</strong> at this size one program is not slower. {refMs && e2e.router_ms?.shards ? <>One program took about <span className="mono">{f((refMs.reference_seconds / (refMs.queries * refMs.genders)) * 1000)} ms</span> per search, against <span className="mono">{f(e2e.router_ms.shards[0])} ms</span> to ask the slices over the network.</> : null} Splitting pays off when the products outgrow one machine.</p>
            <Src>runs/router-e2e.summary.json, runs/sharding-equivalence.summary.json</Src>
          </Fold>
        )}
        {awsTimes.p50 != null && awsTimes.p95 != null && (
          <Fold id="latency" title="How long one search took on AWS" summary={`Typically ${f(awsTimes.p50, 0)} ms; 19 in 20 within ${f(awsTimes.p95, 0)} ms.`}>
            <HealthyBody />
          </Fold>
        )}
        {chaos && Object.keys(chaos.load ?? {}).length > 0 && (
          <Fold id="load" title="Many people at once, on one laptop" summary="More people means longer waits, not more searches.">
            <p className="st-p">Every search waits on one shared step: turning words into numbers. So answers per second stay flat as more people ask.</p>
            {(() => {
              const rows = Object.entries(chaos.load) as [string, Latency][]
              const max = maxOf(rows.map(([, v]) => v.p99))
              return (
                <>
                  <Table cols="minmax(130px, 1fr) minmax(180px, 2.4fr) 70px 64px 64px 64px" head={['requests at once', 'spread', 'per second', 'p50', 'p95', 'p99']}
                    rows={rows.map(([n, v]) => [`${n} at once`, <LatencyBar key="b" p50={v.p50} p95={v.p95} p99={v.p99} max={max} />, f(v.throughput_rps ?? 0), f(v.p50, 0), f(v.p95, 0), f(v.p99, 0)])} />
                  <BarKey max={max} />
                </>
              )
            })()}
            <p className="st-p dim">Milliseconds. One run per row, 400 requests each, 0 errors. Timings drift between runs, so compare rows within this table only.</p>
            <Src>runs/chaos.summary.json</Src>
          </Fold>
        )}
        {ingest && (
          <Fold id="ingest" title="Adding products while things break" summary={`${ingest.held_out} products added through a queue, with a worker and a copy switched off.`}>
            <p className="st-p">All copies ended up the same ({ingest.counts_ok ? 'counts match' : 'COUNTS DO NOT MATCH'}). One bad photo was set aside ({ingest.dead_letters} in the dead-letter queue). The sender sent {ingest.producer.sent} messages; {ingest.producer.duplicates_ignored} repeats were ignored; it was told to wait {ingest.producer.times_told_to_wait} times.</p>
            <div className="st-gap sy-bar">
              <div className="lg dim">Search still matching the full product list</div>
              <PctBar v={ingest.search_identical / ingest.search_total} />
            </div>
            <p className="st-p dim">Limits: copies were compared by counts, not product by product; the queue is one SQLite file on one machine.</p>
            <Src>runs/ingest.summary.json (a first run, in runs/ingest.run1-fixed-3-retries.summary.json, failed with diverged copies; it is kept on the record)</Src>
            {aws.ingest && <div className="st-gap2"><AwsIngestBody /></div>}
          </Fold>
        )}
        {!viewer && (
          <Fold id="live" title="Live now: this server's parts" summary="Read from this server just now.">
            <div className="film film-nodes sy-live" aria-label="Live cluster state">
              <div className="sy-nodes">
                <Node label="Ollama" up={!!health?.ollama} sub={health === undefined ? 'checking' : undefined} />
                <Node label="Encoder" up={!!r?.encoder} />
                <Node label="Router" up={!!r} />
                <div style={{ width: 24 }} />
                {shards.map((g, i) => (
                  <div key={i}>
                    <div style={{ display: 'flex', gap: 6 }}>{g.map((up, j) => <Node key={j} label={`${i}${j ? 'b' : 'a'}`} up={up} />)}</div>
                    <div className="lg" style={{ fontSize: 13, marginTop: 4, textAlign: 'center', color: 'var(--z7)' }}>slice {i}</div>
                  </div>
                ))}
              </div>
            </div>
            <p className="st-p">
              {health?.hosted ? 'This hosted Lab searches inside one program, with all four collections in its memory. The split system is not running here, so its parts show as off.' : health === null ? 'The web server is off, so nothing can be read.' : r ? 'The cluster is running, so searches go through it.' : <>The cluster is off, so searches run inside the web server. To start it: <code className="mono">scripts/cluster.sh start</code>.</>}
            </p>
          </Fold>
        )}
      </div>
    </main>
  )
}
