// The System page: live cluster state, the recorded AWS tour, and the laptop measurements.
import type { CSSProperties, ReactNode } from 'react'
import evidence, { type Latency, type ReplicaRun } from 'virtual:evidence'
import type { Health } from '../api'
import { AwsTour } from './AwsTour'
import { Exact, Plain } from '../components/Plain'

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
      <span className="mono" style={{ fontSize: 13, width: 40, textAlign: 'right' }}>{pc(v)}</span>
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

function Block({ title, plain, lead, children, source }: { title: string; plain: ReactNode; lead: ReactNode; children: ReactNode; source: string }) {
  return (
    <section style={{ marginTop: 72 }}>
      <h2 className="h-record" style={{ fontSize: 28, borderBottom: '2px solid var(--ink)', paddingBottom: 10 }}>{title}</h2>
      <Plain>{plain}</Plain>
      <Exact label="Show the table, the chart and the fine print">
        <p style={{ margin: '14px 0 0', fontSize: 16, lineHeight: '24px', color: '#33333A', maxWidth: '76ch' }}>{lead}</p>
        {children}
        <p style={{ margin: '14px 0 0', fontSize: 13, color: 'var(--z4)' }}>Source: {source}</p>
      </Exact>
    </section>
  )
}

function Node({ label, up, sub }: { label: string; up: boolean; sub?: string }) {
  return (
    <div>
      <div className={`node ${up ? 'up' : 'down'}`}><span className="lg">{label}</span></div>
      <div className="lg" style={{ fontSize: 12, marginTop: 4, textAlign: 'center', color: 'var(--z7)' }}>{sub ?? (up ? 'up' : 'down')}</div>
    </div>
  )
}

export function SystemPage({ health, viewer }: { health: Health | null | undefined; viewer: boolean }) {
  const { e2e, chaos, replicas, ingest, equivalence } = evidence.system
  const r = health?.router ?? null
  const shards = r?.replicas ?? [[false, false], [false, false], [false, false], [false, false]]
  const slow = chaos ? Object.entries(chaos.slow_shard) : []
  const deadKeys = chaos ? Object.entries(chaos.quality_by_dead_shards).map(([k, v]) => ({ dead: JSON.parse(k) as number[], v })) : []
  const avg = (n: number) => { const g = deadKeys.filter((d) => d.dead.length === n); return g.length ? g.reduce((a, d) => a + d.v.ndcg10_marqo_labelled, 0) / g.length : null }
  const refMs = equivalence && 'reference_seconds' in equivalence ? (equivalence as unknown as { reference_seconds: number; queries: number; genders: number }) : null
  const maxOf = (xs: number[]) => Math.max(...xs, 1)
  return (
    <main id="main" tabIndex={-1} className="wrap" style={{ paddingTop: 56, paddingBottom: 110 }}>
      <h1 className="voice" style={{ margin: 0, fontSize: 'clamp(52px, 7vw, 96px)', lineHeight: 1, letterSpacing: '-.015em', maxWidth: '15ch' }}>What happens when machines fail.</h1>
      <p style={{ margin: '22px 0 0', fontSize: 19, lineHeight: '29px', color: '#33333A', maxWidth: '64ch' }}>
        To search fast, the work is split. One program turns your words into numbers. Four others (slices) each hold a quarter of the products, with two copies of every quarter. A coordinator (the router) asks all the slices at once and combines the answers. First comes a recording from AWS, then tests on one laptop.</p>

      {!viewer && (
      <section className="film film-nodes" style={{ marginTop: 56 }} aria-label="Live cluster state">
        <h2 className="h-record" style={{ fontSize: 28 }}>Live now <span className="lg dim" style={{ fontSize: 13, letterSpacing: '.08em' }}>· read from this server just now</span></h2>
        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 20, alignItems: 'flex-start' }}>
          <Node label="Ollama" up={!!health?.ollama} sub={health === undefined ? 'checking' : undefined} />
          <Node label="Encoder" up={!!r?.encoder} />
          <Node label="Router" up={!!r} />
          <div style={{ width: 24 }} />
          {shards.map((g, i) => (
            <div key={i}>
              <div style={{ display: 'flex', gap: 6 }}>{g.map((up, j) => <Node key={j} label={`${i}${j ? 'b' : 'a'}`} up={up} />)}</div>
              <div className="lg" style={{ fontSize: 12, marginTop: 4, textAlign: 'center', color: 'var(--z7)' }}>shard {i}</div>
            </div>
          ))}
        </div>
        <p style={{ margin: '16px 0 0', fontSize: 15, lineHeight: '22px', color: 'var(--z7)', maxWidth: '70ch' }}>
          {health?.hosted ? 'This hosted Lab searches inside one program, with all four collections in its memory. The split system (router, encoder and slices) is not running here, so its parts show as off; what follows is how it behaved when it was running, on a laptop and on AWS.' : health === null ? 'The web server is off, so nothing can be read.' : r ? 'The cluster is running, so searches go through it.' : <>The cluster is off, so searches run inside the web server. To start it: <code className="mono" style={{ fontSize: 13 }}>scripts/cluster.sh start</code>.</>}
        </p>
      </section>
      )}


      <AwsTour />

      {viewer && <p className="live-off">Live cluster status needs your own server. Switch to Lab in Settings, top right, or see the recorded runs above.</p>}

      {e2e && (
        <Block title="Splitting the work changes nothing in the answers" plain={<>{e2e.identical.toLocaleString('en')} of {e2e.requests.toLocaleString('en')} test searches gave exactly the same top 4 as the single-program version. Splitting into 2, 4 or 8 slices matched every time too. It is not faster at this size; splitting pays off when the product list outgrows one machine.</>} lead={<>{e2e.identical.toLocaleString('en')} of {e2e.requests.toLocaleString('en')} requests through the live cluster returned exactly the same top 4 products, sources and ids as the single-process search; {e2e.partial} were partial.
          {equivalence && <> Splitting into 2, 4 or 8 shards in one process gave the same result on every one of {Object.values(equivalence.by_shards)[0].identical.toLocaleString('en')} cases.</>}</>}
          source="runs/router-e2e.summary.json, runs/sharding-equivalence.summary.json">
          {(() => {
            const rows = Object.entries(e2e.router_ms)
            const max = maxOf(rows.map(([, v]) => v[2]))
            return (
              <>
              <Table cols="minmax(190px, 1.2fr) minmax(160px, 2fr) 64px 64px 64px" head={['milliseconds, inside the router', 'spread', 'p50', 'p95', 'p99']}
                rows={rows.map(([k, v]) => [k === 'total' ? 'whole request' : k === 'shards' ? 'asking the shards (parallel)' : 'turning words into numbers',
                  <LatencyBar key="b" p50={v[0]} p95={v[1]} p99={v[2]} max={max} />, f(v[0]), f(v[1]), f(v[2])])} />
              <BarKey max={max} />
              </>
            )
          })()}
          <p style={{ margin: '14px 0 0', fontSize: 15, lineHeight: '22px', maxWidth: '76ch' }}>
            <strong>Honest note:</strong> at this size one process is not slower. {refMs ? <>The single-process search took about {f((refMs.reference_seconds / (refMs.queries * refMs.genders)) * 1000)} ms per search (compute only), against {f(e2e.router_ms.shards[0])} ms to ask the shards over the network.</> : null} Splitting pays off when the catalogue outgrows one machine; here it is a way to measure how the design behaves.
          </p>
        </Block>
      )}

      {chaos && (
        <Block title="When many people search at once" plain={<>About {f(Math.min(...Object.values(chaos.load).map((v) => v.throughput_rps ?? 0)), 0)} to {f(Math.max(...Object.values(chaos.load).map((v) => v.throughput_rps ?? 0)), 0)} searches per second on this laptop, however many people ask at once. They all wait on one shared step (turning words into numbers), so more people means longer waits, not more searches.</>} lead="Throughput does not grow with more simultaneous requests, because every request needs the single encoder. Waiting time grows roughly as the number of people waiting divided by throughput."
          source="runs/chaos.summary.json">
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
          <p style={{ margin: '12px 0 0', fontSize: 13, color: 'var(--z4)', maxWidth: '80ch' }}>Milliseconds. One run per row, 400 requests each, 0 errors. Timings drift between runs as other programs use the laptop, so compare rows within this table only.</p>
        </Block>
      )}

      {chaos && (
        <Block title="When one slice is slow, or dead" plain={<>If one slice is slow, every search waits for it (up to an 800 ms limit), then answers without it. If one slice is dead, answers come back fast but incomplete. Match score dropped about {avg(0) != null && avg(1) != null ? Math.round(((avg(0)! - avg(1)!) / avg(0)!) * 100) : '—'}% with one slice down and about {avg(0) != null && avg(2) != null ? Math.round(((avg(0)! - avg(2)!) / avg(0)!) * 100) : '—'}% with two. A restarted slice rejoined in {f(chaos.recovery.seconds_until_healthy)} s.</>} lead="A slow shard makes the whole request as slow as that shard, until the router's 800 ms deadline cuts it off and answers without it. A dead shard fails fast, so the answer comes quickly but is partial."
          source="runs/chaos.summary.json">
          {(() => {
            const rows: [string, Latency][] = [...(slow as [string, Latency][]).map(([ms, v]) => [`shard 2 slowed by +${ms} ms`, v] as [string, Latency]), ['one shard killed', chaos.dead_shard]]
            const max = maxOf(rows.map(([, v]) => v.p99))
            return (
              <>
              <Table cols="minmax(170px, 1.3fr) minmax(150px, 1.6fr) 64px 110px minmax(130px, 1.2fr) minmax(130px, 1.2fr)" head={['scenario', 'spread', 'p50 ms', 'partial answers', 'same top 4 as full', 'overlap with full']}
                rows={rows.map(([label, v]) => [label, <LatencyBar key="b" p50={v.p50} p95={v.p95} p99={v.p99} max={max} />, f(v.p50, 0), `${v.partial ?? 0} of ${v.n}`,
                  <PctBar key="s" v={v.identical_to_full} cross={(v.partial ?? 0) > 0} />, <PctBar key="o" v={v.mean_overlap_with_full_top4} cross={(v.partial ?? 0) > 0} />])} />
              <BarKey max={max} />
              </>
            )
          })()}
          <p style={{ margin: '14px 0 0', fontSize: 15, lineHeight: '22px', maxWidth: '76ch' }}>
            After a restart the shard was healthy again in {f(chaos.recovery.seconds_until_healthy)} s and answers were full again. Cross-hatched bars are partial answers.
            {avg(0) != null && avg(1) != null && avg(2) != null && <> On the 852 labelled Marqo searches, ranking quality (NDCG@10) was <span className="mono">{f(avg(0)!, 3)}</span> with every shard, <span className="mono">{f(avg(1)!, 3)}</span> with one dead and <span className="mono">{f(avg(2)!, 3)}</span> with two dead (averaged over which shards).</>}
          </p>
        </Block>
      )}

      {replicas && (
        <Block title="A backup copy of every slice" plain={<>Every slice has a backup copy. If the first copy fails, or is just slow, the router asks the other. A dead copy costs nothing you would notice. If both copies of a slice are gone, answers are incomplete again.</>} lead="With replicas the router asks a second copy at once when the first fails (failover), and asks a second copy too when the first is merely slow (hedging). The price: hedged requests do their shard's work twice."
          source="runs/chaos-replicas.summary.json">
          {(() => {
            const rows = Object.entries(replicas).filter(([, v]) => !Array.isArray(v)) as [string, ReplicaRun][]
            const max = maxOf(rows.map(([, v]) => v.p99))
            return (
              <>
              <Table cols="minmax(210px, 1.6fr) minmax(150px, 1.6fr) 64px 64px 80px 80px 70px" head={['scenario, 200 requests', 'spread', 'p50 ms', 'p99 ms', 'partial', 'failovers', 'hedged']}
                rows={rows.map(([k, x]) => [k.replace(/^S\d /, ''), <LatencyBar key="b" p50={x.p50} p95={x.p95} p99={x.p99} max={max} />, f(x.p50), f(x.p99), String(x.partial), String(x.failovers), String(x.hedged)])} />
              <BarKey max={max} />
              </>
            )
          })()}
          <p style={{ margin: '14px 0 0', fontSize: 15, lineHeight: '22px', maxWidth: '76ch' }}>A dead copy costs nothing visible. A slow copy is tamed by hedging (without copies the same delay gave a p50 of about 349 ms). Replication is not magic: with both copies of a shard dead, the answer is partial again.</p>
        </Block>
      )}

      {ingest && (
        <Block title="Adding products while things break" plain={<>{ingest.held_out} products were added through a queue while a worker and one copy were switched off. All copies ended up the same ({ingest.counts_ok ? 'counts match' : 'COUNTS DO NOT MATCH'}), one bad photo was set aside, repeats were ignored, and search still matched the full list on {ingest.search_identical.toLocaleString('en')} of {ingest.search_total.toLocaleString('en')} requests.</>} lead={<>{ingest.held_out} products were added through a queue while the ingest worker and one replica were killed. All eight workers converged ({ingest.counts_ok ? 'counts match' : 'COUNTS DO NOT MATCH'}); the one bad photo is parked in the dead-letter queue ({ingest.dead_letters}); the producer sent {ingest.producer.sent} messages and {ingest.producer.duplicates_ignored} repeats were ignored; it was told to wait {ingest.producer.times_told_to_wait} times; and search still matched the full catalogue on {ingest.search_identical.toLocaleString('en')} of {ingest.search_total.toLocaleString('en')} requests.</>}
          source="runs/ingest.summary.json (a first run, in runs/ingest.run1-fixed-3-retries.summary.json, failed with diverged replicas; it is kept on the record)">
          <div style={{ marginTop: 16, maxWidth: 520 }}>
            <div className="lg dim" style={{ marginBottom: 6 }}>Search still matching the full product list</div>
            <PctBar v={ingest.search_identical / ingest.search_total} />
          </div>
          <p style={{ margin: '12px 0 0', fontSize: 14, color: 'var(--z4)', maxWidth: '80ch' }}>Limits: replica equality was checked by counts, not id by id; the queue is one SQLite file on one machine.</p>
        </Block>
      )}
    </main>
  )
}
