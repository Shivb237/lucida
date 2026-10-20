// The recorded AWS runs (Mumbai, 2026-10-15 to 2026-10-16), as parts the System page lays out: the architecture drawing, the charts and tables
// behind each experiment. Everything is read from runs/aws-*; the AWS machines were deleted afterwards (2026-10-16).
import type { ReactNode } from 'react'
import evidence, { type AwsPoint, type OverloadVariant } from 'virtual:evidence'

const f = (n: number, d = 0) => n.toFixed(d)
const pc = (x: number) => `${Math.round(x * 100)}%`
const sorted = (xs: number[]) => [...xs].sort((a, b) => a - b)
const pct = (xs: number[], p: number) => { const s = sorted(xs); return s[Math.min(s.length - 1, Math.floor(p * s.length))] }

/** Every search as one mark: height = milliseconds, left to right = order sent. A hollow ring = the router used a second copy because the first failed (failover). */
export function Scatter({ points, label }: { points: AwsPoint[]; label: string }) {
  const ok = points.filter((p) => p.total_ms != null)
  const W = 640, H = 190, L = 44, B = 26, T = 8
  const max = Math.max(...ok.map((p) => p.total_ms!), 1)
  const top = Math.ceil(max / 100) * 100
  const x = (i: number) => L + (i / Math.max(points.length - 1, 1)) * (W - L - 8)
  const y = (v: number) => T + (1 - v / top) * (H - T - B)
  return (
    <div className="svg-scroll"><svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} style={{ width: '100%', minWidth: 600, maxWidth: 760, display: 'block' }}>
      {[0, top / 2, top].map((v) => (
        <g key={v}><line x1={L} x2={W - 8} y1={y(v)} y2={y(v)} stroke="var(--z8)" strokeWidth="1" /><text x={L - 6} y={y(v) + 4} textAnchor="end" fontSize="13" fill="var(--z4)" fontFamily="var(--mono)">{f(v)}</text></g>
      ))}
      {points.map((p, i) => p.total_ms == null ? null : p.failovers > 0
        ? <circle key={i} cx={x(i)} cy={y(p.total_ms)} r="3.6" fill="none" stroke="var(--ink)" strokeWidth="1.4" />
        : <circle key={i} cx={x(i)} cy={y(p.total_ms)} r="2.4" fill="var(--ink)" />)}
      <text x={L} y={H - 6} fontSize="13" fill="var(--z4)" fontFamily="var(--mono)">search 1</text>
      <text x={W - 8} y={H - 6} textAnchor="end" fontSize="13" fill="var(--z4)" fontFamily="var(--mono)">search {points.length}</text>
      <text x={L + 4} y={T + 12} fontSize="13" fill="var(--z4)" fontFamily="var(--mono)">ms</text>
    </svg></div>
  )
}

/** Three overload variants at 32 searches at once: answered, answered wrongly late, refused fast. */
function OverloadRow({ name, what, v }: { name: string; what: string; v: OverloadVariant }) {
  const h = v.hardest_level
  const total = h.requests ?? h.ok + (h.shed ?? 0) + (h.errors ?? 0)
  const part = (n: number) => `${(n / total) * 100}%`
  return (
    <div className="aws-row">
      <div><div style={{ fontWeight: 700, fontSize: 17 }}>{name}</div><div style={{ fontSize: 16, lineHeight: '24px', color: 'var(--z4)' }}>{what}</div></div>
      <div>
        <div className="outcome-bar" role="img" aria-label={`${h.ok} answered, ${h.shed ?? 0} refused fast, ${h.errors ?? 0} failed, of ${total}`}>
          <div className="o-ok" style={{ width: part(h.ok) }} />
          <div className="o-shed hatch" style={{ width: part(h.shed ?? 0) }} />
          <div className="o-err cross" style={{ width: part(h.errors ?? 0) }} />
        </div>
        <div className="mono" style={{ fontSize: 15, marginTop: 4 }}>{h.ok} answered · {h.shed ?? 0} refused · {h.errors ?? 0} failed{h.shed_p50_ms ? ` · refusal took ${f(h.shed_p50_ms, 0)} ms` : ''}</div>
      </div>
      <div className="mono" style={{ fontSize: 15 }}>{v.goodput_at_4_8_16.map((g) => f(g, 1)).join(' / ')}<div className="dim" style={{ fontSize: 13 }}>answers/s at 4, 8, 16</div></div>
      <div className="mono" style={{ fontSize: 15 }}>{f(v.recovery_0s.goodput_per_s, 2)}<div className="dim" style={{ fontSize: 13 }}>answers/s right after ({v.recovery_0s.ok} of 20 ok)</div></div>
    </div>
  )
}


/** The request path on AWS, as a drawing: browser, router host, two shard hosts in two zones, the queue. */
export function ArchMap() {
  return (
    <div className="svg-scroll"><svg viewBox="0 0 720 230" role="img" aria-label="Request path: browser to router host (router, encoder), which asks shard host A in zone a and shard host B in zone b; an ingestion queue feeds the ingest worker on the router host" className="aws-map" style={{ minWidth: 600 }}>
      <g fontFamily="var(--sans)" fontSize="15" fill="var(--ink)">
        <rect x="8" y="88" width="104" height="48" fill="none" stroke="var(--z4)" strokeDasharray="2 4" /><text x="60" y="117" textAnchor="middle">browser</text>
        <rect x="190" y="52" width="190" height="120" fill="var(--paper)" stroke="var(--ink)" strokeWidth="1.5" /><text x="285" y="72" textAnchor="middle" fontWeight="700">router host</text>
        <text x="285" y="98" textAnchor="middle">router (TypeScript)</text><text x="285" y="118" textAnchor="middle">encoder (words to numbers)</text><text x="285" y="138" textAnchor="middle">ingest worker</text><text x="285" y="158" textAnchor="middle" fill="var(--z4)" fontSize="13">zone b</text>
        <rect x="500" y="8" width="204" height="86" fill="var(--paper)" stroke="var(--ink)" strokeWidth="1.5" /><text x="602" y="28" textAnchor="middle" fontWeight="700">shard host A · zone a</text><text x="602" y="52" textAnchor="middle">4 shard workers</text><text x="602" y="72" textAnchor="middle" fill="var(--z4)" fontSize="13">a copy of every shard</text>
        <rect x="500" y="136" width="204" height="86" fill="var(--paper)" stroke="var(--ink)" strokeWidth="1.5" /><text x="602" y="156" textAnchor="middle" fontWeight="700">shard host B · zone b</text><text x="602" y="180" textAnchor="middle">4 shard workers</text><text x="602" y="200" textAnchor="middle" fill="var(--z4)" fontSize="13">a second copy of every shard</text>
        <rect x="190" y="196" width="190" height="28" fill="none" stroke="var(--z4)" /><text x="285" y="215" textAnchor="middle" fontSize="13">queue + dead-letter queue (SQS)</text>
      </g>
      <g stroke="var(--ink)" strokeWidth="1.5" fill="none"><path d="M112 112 H190" /><path d="M380 100 C440 100 440 51 500 51" /><path d="M380 124 C440 124 440 179 500 179" /><path d="M285 196 V172" strokeDasharray="4 3" /></g>
    </svg></div>
  )
}

/** Plain numbers the System page's cards and folds quote, all computed from the AWS run files. */
function awsNumbers() {
  const aws = evidence.aws
  const healthy = aws.healthy.filter((p) => p.total_ms != null)
  const hMs = healthy.map((p) => p.total_ms!)
  const shardShare = hMs.length ? pct(healthy.map((p) => p.shards_ms ?? 0), 0.5) / Math.max(pct(hMs, 0.5), 1e-9) : 0
  const lt = aws.loadtest?.levels ?? []
  const plateau = lt.filter((l) => l.concurrency >= 2 && l.concurrency <= 16)
  const plateauRate = plateau.length ? plateau.reduce((n, l) => n + l.req_per_s, 0) / plateau.length : 0
  const cliff = lt.find((l) => l.errors >= l.requests)
  return { aws, healthy, hMs, shardShare, plateauRate, cliff, p50: hMs.length ? pct(hMs, 0.5) : null, p95: hMs.length ? pct(hMs, 0.95) : null }
}

const SRC = ({ children }: { children: ReactNode }) => <p className="sy-src">Source: {children}</p>

export function HealthyBody() {
  const { aws, healthy, hMs, shardShare } = awsNumbers()
  if (!hMs.length) return null
  return (
    <>
      <p className="st-p">{healthy.length} searches, about one per second, with both shard hosts up. Half took under <span className="mono">{f(pct(hMs, 0.5))} ms</span>; 19 in 20 (p95) under <span className="mono">{f(pct(hMs, 0.95))} ms</span>. About {pc(shardShare)} of it is asking the shards; most of the rest is turning words into numbers.</p>
      <div className="st-gap"><Scatter points={aws.healthy} label={`${healthy.length} searches on AWS, milliseconds each`} /></div>
      <SRC>runs/aws-failover.jsonl, first run (machine-logged, one row per search); matches run1_healthy_120s in runs/aws-failover.summary.json</SRC>
    </>
  )
}

export function FailoverBody() {
  const fo = evidence.aws.failover
  if (!fo) return null
  const phaseNames: Record<string, string> = { before_stop: 'both machines up', B_shutting_down: 'shard host B shutting down', B_stopped_router_uses_A: 'B off: router uses A', B_booting: 'B booting', B_back: 'B back' }
  return (
    <>
      <p className="st-p">{fo.totals.searches} searches across three runs; the chart and table show run 3 ({fo.series.length} searches). While B shut down, every search used a second copy from host A (a hollow ring).</p>
      <p className="bar-key">● one search · ○ a search where the router had to use a second copy because the first one failed.</p>
      <div><Scatter points={fo.series} label={`${fo.series.length} searches while a shard host was switched off, milliseconds each; hollow rings mark failovers`} /></div>
      <div className="st-gap">
        <div className="aws-head lg dim"><div>phase of run 3</div><div className="num">searches</div><div className="num">median ms</div><div className="num">slowest ms</div><div className="num">second copy used</div></div>
        {Object.entries(fo.phases).map(([k, v]) => (
          <div className="aws-line" key={k}><div style={{ fontWeight: 600 }}>{phaseNames[k] ?? k}</div><div className="num mono" data-label="searches">{v.n}</div><div className="num mono" data-label="median ms">{f(v.median_ms)}</div><div className="num mono" data-label="slowest ms">{f(v.max_ms)}</div><div className="num mono" data-label="second copy used">{v.requests_with_failover} of {v.n}</div></div>
        ))}
      </div>
      <p className="st-p dim">Limit: the stop and start times were not logged, so the phases are inferred from when failovers appeared.</p>
      <SRC>runs/aws-failover.jsonl and runs/aws-failover.summary.json</SRC>
    </>
  )
}

export function OverloadBody() {
  const { aws, plateauRate, cliff } = awsNumbers()
  const o = aws.overload?.variants
  return (
    <>
      {aws.loadtest && aws.loadtest.levels.length > 0 && (
        <>
          <p className="st-p">First, the limit. Answers per second level off near <span className="mono">{f(plateauRate, 1)}</span>: every search first needs one shared step that uses both processors.{cliff ? <> At {cliff.concurrency} at once, all {cliff.requests} failed after waiting 5 seconds.</> : null}</p>
          <div className="st-gap">
            <div className="aws-head six lg dim"><div>at once</div><div className="num">answers per second</div><div className="num">p50 ms</div><div className="num">p99 ms</div><div className="num">failed</div><div className="num">CPU busy</div></div>
            {aws.loadtest.levels.map((l) => (
              <div className="aws-line six" key={l.concurrency}>
                <div style={{ fontWeight: 600 }}>{l.concurrency} at once</div><div className="num mono" data-label="answers per second">{l.errors >= l.requests ? '—' : f(l.req_per_s, 1)}</div><div className="num mono" data-label="p50 ms">{f(l.p50_ms)}</div><div className="num mono" data-label="p99 ms">{f(l.p99_ms)}</div><div className="num mono" data-label="failed">{l.errors} of {l.requests}</div><div className="num mono" data-label="CPU busy">{f(l.cpu_busy_pct)}%</div>
              </div>
            ))}
          </div>
          <SRC>runs/aws-loadtest.summary.json (table copied by hand from the run output; the raw log is partial)</SRC>
        </>
      )}
      {o?.baseline && o.v1 && o.v2 && (
        <>
          <p className="st-p">Then two fixes, measured the same way: 32 searches at once, 320 requests. Neither adds capacity. The encoder had kept working for callers who had left.</p>
          <div className="st-gap">
            <OverloadRow name="Before" what="Every request goes to the encoder at once, with no limit." v={o.baseline} />
            <OverloadRow name="Fix 1" what="The encoder does 2 at a time and drops work nobody is waiting for." v={o.v1} />
            <OverloadRow name="Fix 2" what="Also refuses new requests past 12 in flight (HTTP 429, with retry-after)." v={o.v2} />
          </div>
          {aws.overload!.rebuilt.length > 0 && (
            <p className="st-p"><strong>Control on rebuilt machines.</strong> All three machines were rebuilt from the repository with no hand-tuning. Answers per second at {aws.overload!.rebuilt.map((l) => `${l.concurrency} at once`).join(', ')}: <span className="mono">{aws.overload!.rebuilt.map((l) => f(l.goodput_per_s, 2)).join(', ')}</span>; failed: <span className="mono">{aws.overload!.rebuilt.reduce((n, l) => n + (l.errors ?? 0), 0)}</span>.</p>
          )}
          <p className="bar-key">Solid = answered, hatched = refused quickly (a clear "busy", the caller can retry), cross-hatched = failed after waiting. Limits: each caller retries at once when refused, so compare answers per second, not counts; one run per variant; the limit of 12 is a guess.</p>
          <SRC>runs/aws-overload-experiment.jsonl and .summary.json (machine-logged; one run per variant); runs/aws-rebuilt-loadtest.jsonl</SRC>
        </>
      )}
    </>
  )
}

export function AwsIngestBody() {
  const ing = evidence.aws.ingest
  if (!ing) return null
  return (
    <>
      <p className="st-p">On AWS, products were sent through a queue; both copies of each slice must end with the same products. {String(ing.totals)}. The first worker crash-looped and sent {ing.replicaOff.dlqWhileDown} messages to the dead-letter queue. The tests found it; the fixes:</p>
      <ul className="st-list">{ing.bugs.map((b) => <li key={b}>{b}</li>)}</ul>
      <SRC>runs/aws-ingest.summary.json (numbers copied by hand from command output, not written by a script)</SRC>
    </>
  )
}
