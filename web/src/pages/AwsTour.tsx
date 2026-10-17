// The recorded AWS tour: runs made on AWS (Mumbai, 2026-10-15 to 2026-10-16) while the machines were up. Everything here is read from runs/aws-*; The AWS machines were deleted afterwards.
import evidence, { type AwsPoint, type OverloadVariant } from 'virtual:evidence'
import { Exact, Plain } from '../components/Plain'

const f = (n: number, d = 0) => n.toFixed(d)
const pc = (x: number) => `${Math.round(x * 100)}%`
const sorted = (xs: number[]) => [...xs].sort((a, b) => a - b)
const pct = (xs: number[], p: number) => { const s = sorted(xs); return s[Math.min(s.length - 1, Math.floor(p * s.length))] }

/** Every search as one mark: height = milliseconds, left to right = order sent. A hollow ring = the router used a second copy because the first failed (failover). */
function Scatter({ points, label }: { points: AwsPoint[]; label: string }) {
  const ok = points.filter((p) => p.total_ms != null)
  const W = 640, H = 190, L = 44, B = 26, T = 8
  const max = Math.max(...ok.map((p) => p.total_ms!), 1)
  const top = Math.ceil(max / 100) * 100
  const x = (i: number) => L + (i / Math.max(points.length - 1, 1)) * (W - L - 8)
  const y = (v: number) => T + (1 - v / top) * (H - T - B)
  return (
    <div className="svg-scroll"><svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} style={{ width: '100%', minWidth: 600, maxWidth: 760, display: 'block' }}>
      {[0, top / 2, top].map((v) => (
        <g key={v}><line x1={L} x2={W - 8} y1={y(v)} y2={y(v)} stroke="var(--z8)" strokeWidth="1" /><text x={L - 6} y={y(v) + 4} textAnchor="end" fontSize="12" fill="var(--z4)" fontFamily="var(--mono)">{f(v)}</text></g>
      ))}
      {points.map((p, i) => p.total_ms == null ? null : p.failovers > 0
        ? <circle key={i} cx={x(i)} cy={y(p.total_ms)} r="3.6" fill="none" stroke="var(--ink)" strokeWidth="1.4" />
        : <circle key={i} cx={x(i)} cy={y(p.total_ms)} r="2.4" fill="var(--ink)" />)}
      <text x={L} y={H - 6} fontSize="12" fill="var(--z4)" fontFamily="var(--mono)">search 1</text>
      <text x={W - 8} y={H - 6} textAnchor="end" fontSize="12" fill="var(--z4)" fontFamily="var(--mono)">search {points.length}</text>
      <text x={L + 4} y={T + 12} fontSize="12" fill="var(--z4)" fontFamily="var(--mono)">ms</text>
    </svg></div>
  )
}

function Section({ title, plain, lead, children, source }: { title: string; plain: React.ReactNode; lead: React.ReactNode; children: React.ReactNode; source: string }) {
  return (
    <section style={{ marginTop: 56 }}>
      <h3 className="h-record" style={{ fontSize: 24, borderBottom: '2px solid var(--ink)', paddingBottom: 8 }}>{title}</h3>
      <Plain>{plain}</Plain>
      <Exact label="Show the chart, the table and the fine print">
        <p style={{ margin: '12px 0 0', fontSize: 16, lineHeight: '24px', color: '#33333A', maxWidth: '76ch' }}>{lead}</p>
        {children}
        <p style={{ margin: '12px 0 0', fontSize: 13, color: 'var(--z4)' }}>Source: {source}</p>
      </Exact>
    </section>
  )
}

/** Three overload variants at 32 searches at once: answered, answered wrongly late, refused fast. */
function OverloadRow({ name, what, v }: { name: string; what: string; v: OverloadVariant }) {
  const h = v.hardest_level
  const total = h.requests ?? h.ok + (h.shed ?? 0) + (h.errors ?? 0)
  const part = (n: number) => `${(n / total) * 100}%`
  return (
    <div className="aws-row">
      <div><div style={{ fontWeight: 700, fontSize: 16 }}>{name}</div><div style={{ fontSize: 14, lineHeight: '20px', color: 'var(--z4)' }}>{what}</div></div>
      <div>
        <div className="outcome-bar" role="img" aria-label={`${h.ok} answered, ${h.shed ?? 0} refused fast, ${h.errors ?? 0} failed, of ${total}`}>
          <div className="o-ok" style={{ width: part(h.ok) }} />
          <div className="o-shed hatch" style={{ width: part(h.shed ?? 0) }} />
          <div className="o-err cross" style={{ width: part(h.errors ?? 0) }} />
        </div>
        <div className="mono" style={{ fontSize: 13, marginTop: 4 }}>{h.ok} answered · {h.shed ?? 0} refused · {h.errors ?? 0} failed{h.shed_p50_ms ? ` · refusal took ${f(h.shed_p50_ms, 0)} ms` : ''}</div>
      </div>
      <div className="mono" style={{ fontSize: 13 }}>{v.goodput_at_4_8_16.map((g) => f(g, 1)).join(' / ')}<div className="dim" style={{ fontSize: 12 }}>answers/s at 4, 8, 16</div></div>
      <div className="mono" style={{ fontSize: 13 }}>{f(v.recovery_0s.goodput_per_s, 2)}<div className="dim" style={{ fontSize: 12 }}>answers/s right after ({v.recovery_0s.ok} of 20 ok)</div></div>
    </div>
  )
}


const SHOTS: { file: string; alt: string; caption: string }[] = [
  { file: 'ec2-instances.png', alt: 'AWS console list of EC2 instances', caption: 'The machines in the AWS console: two small shard hosts in two zones and the router host, all running; an older router shows as terminated.' },
  { file: 'fleet-verified.png', alt: 'Terminal output of the fleet check', caption: 'One command checks every service on all three machines: all active, and each shard worker reports its share of the products.' },
  { file: 'cloudformation-stacks.png', alt: 'AWS CloudFormation list of five stacks', caption: 'The system as code: the bootstrap stack plus network, data, compute and observability stacks.' },
  { file: 'cloudwatch-dashboard.png', alt: 'CloudWatch dashboard with alarms and charts', caption: 'The dashboard: nine alarms (all green), search latency, searches per minute, where the time goes, queue depth, CPU, memory and disk. The ingestion panel is empty because nothing was ingested in that hour.' },
  { file: 'logs-recent.png', alt: 'Terminal table of the last five router log lines', caption: 'The last five searches in the router log: total, encoding and shard milliseconds.' },
  { file: 'logs-trace.png', alt: 'Terminal listing one request across router, encoder and shards', caption: 'One request ticket followed across the router, the encoder and the shards.' },
  { file: 'lucida-search.png', alt: 'The Lucida search page during a live search', caption: 'The site running a live search through the router cluster (the seller photo is blurred).' },
  { file: 'exposure-record.png', alt: 'The exposure record for one live search', caption: 'The exposure record of one live search: 2.74 s understanding, 0.34 s search.' },
]

function Shots() {
  return (
    <section style={{ marginTop: 64 }} aria-label="Screenshots">
      <h3 className="h-record" style={{ fontSize: 24, borderBottom: '2px solid var(--ink)', paddingBottom: 8 }}>The console, as it looked</h3>
      <p style={{ margin: '12px 0 0', fontSize: 16, lineHeight: '24px', color: '#33333A', maxWidth: '76ch' }}>Console screenshots from 16 October. Account number, sign-in name, machine ids, addresses and queue names are blurred on purpose.</p>
      <Exact label="Show the 8 console screenshots">
      <div className="shots">
        {SHOTS.map((x) => (
          <figure key={x.file} style={{ margin: 0 }}>
            <a href={`${import.meta.env.BASE_URL}aws/${x.file}`} target="_blank" rel="noopener noreferrer" aria-label={`Open the full-size screenshot: ${x.alt}`}>
              <img src={`${import.meta.env.BASE_URL}aws/${x.file}`} alt={x.alt} loading="lazy" />
            </a>
            <figcaption>{x.caption} <span className="dim">Click for full size.</span></figcaption>
          </figure>
        ))}
      </div>
      </Exact>
    </section>
  )
}

export function AwsTour() {
  const aws = evidence.aws
  const healthy = aws.healthy.filter((p) => p.total_ms != null)
  const fo = aws.failover
  const hMs = healthy.map((p) => p.total_ms!)
  const shardShare = pct(healthy.map((p) => p.shards_ms ?? 0), 0.5) / pct(hMs, 0.5)
  const lt = aws.loadtest?.levels ?? []
  const plateau = lt.filter((l) => l.concurrency >= 2 && l.concurrency <= 16)
  const plateauRate = plateau.length ? plateau.reduce((n, l) => n + l.req_per_s, 0) / plateau.length : 0
  const cliff = lt.find((l) => l.errors >= l.requests)
  const phaseNames: Record<string, string> = { before_stop: 'both machines up', B_shutting_down: 'shard host B shutting down', B_stopped_router_uses_A: 'B off: router uses A', B_booting: 'B booting', B_back: 'B back' }
  return (
    <section style={{ marginTop: 56 }} aria-label="Recorded AWS tour">
      <h2 className="h-record" style={{ fontSize: 32 }}>Recorded on AWS</h2>
      <p style={{ margin: '12px 0 0', fontSize: 16, lineHeight: '24px', color: '#33333A', maxWidth: '76ch' }}>
        The same system ran for two days on three small AWS machines in Mumbai: one coordinator, and two machines that each hold a full copy of the product list, in separate buildings (zones). The machines were deleted afterwards (2026-10-16), so this is a <strong>recording, not a live view</strong>. Every number comes from a logged run.</p>

      <div className="svg-scroll"><svg viewBox="0 0 720 230" role="img" aria-label="Request path: browser to router host (router, encoder), which asks shard host A in zone a and shard host B in zone b; an ingestion queue feeds the ingest worker on the router host" className="aws-map" style={{ minWidth: 600 }}>
        <g fontFamily="var(--sans)" fontSize="13" fill="var(--ink)">
          <rect x="8" y="88" width="104" height="48" fill="none" stroke="var(--z4)" strokeDasharray="2 4" /><text x="60" y="117" textAnchor="middle">browser</text>
          <rect x="190" y="52" width="190" height="120" fill="var(--paper)" stroke="var(--ink)" strokeWidth="1.5" /><text x="285" y="72" textAnchor="middle" fontWeight="700">router host</text>
          <text x="285" y="98" textAnchor="middle">router (TypeScript)</text><text x="285" y="118" textAnchor="middle">encoder (words to numbers)</text><text x="285" y="138" textAnchor="middle">ingest worker</text><text x="285" y="158" textAnchor="middle" fill="var(--z4)" fontSize="12">zone b</text>
          <rect x="500" y="8" width="204" height="86" fill="var(--paper)" stroke="var(--ink)" strokeWidth="1.5" /><text x="602" y="28" textAnchor="middle" fontWeight="700">shard host A · zone a</text><text x="602" y="52" textAnchor="middle">4 shard workers</text><text x="602" y="72" textAnchor="middle" fill="var(--z4)" fontSize="12">a copy of every shard</text>
          <rect x="500" y="136" width="204" height="86" fill="var(--paper)" stroke="var(--ink)" strokeWidth="1.5" /><text x="602" y="156" textAnchor="middle" fontWeight="700">shard host B · zone b</text><text x="602" y="180" textAnchor="middle">4 shard workers</text><text x="602" y="200" textAnchor="middle" fill="var(--z4)" fontSize="12">a second copy of every shard</text>
          <rect x="190" y="196" width="190" height="28" fill="none" stroke="var(--z4)" /><text x="285" y="215" textAnchor="middle" fontSize="12">queue + dead-letter queue (SQS)</text>
        </g>
        <g stroke="var(--ink)" strokeWidth="1.5" fill="none"><path d="M112 112 H190" /><path d="M380 100 C440 100 440 51 500 51" /><path d="M380 124 C440 124 440 179 500 179" /><path d="M285 196 V172" strokeDasharray="4 3" /></g>
      </svg></div>

      <Section title="How long one search took" plain={<>A typical search took <strong>{f(pct(hMs, 0.5))} ms</strong>, about a third of a second. 19 in 20 finished within {f(pct(hMs, 0.95))} ms. About {pc(shardShare)} of that is looking things up; most of the rest is turning your words into numbers.</>} lead={<>{healthy.length} searches, about one per second, with both shard hosts up and no failover. Half took under <strong>{f(pct(hMs, 0.5))} ms</strong>, 95% under {f(pct(hMs, 0.95))} ms. About {pc(shardShare)} of it is asking the shards; most of the rest is the encoder turning words into numbers.</>}
        source="runs/aws-failover.jsonl, first run (machine-logged, one row per search); matches run1_healthy_120s in runs/aws-failover.summary.json">
        <div style={{ marginTop: 14 }}><Scatter points={aws.healthy} label={`${healthy.length} searches on AWS, milliseconds each`} /></div>
      </Section>

      {fo && (
        <Section title="Switching a whole machine off during searches" plain={<>One machine was switched off while searches kept coming. Result: <strong>{fo.totals.searches} searches over three runs, {fo.totals.errors} errors, {fo.totals.partial_answers} incomplete answers</strong>. The router quietly used the other copy. The exact switch-off times were not logged. A typical search went from {f(fo.phases.before_stop.median_ms)} ms to {f(fo.phases.B_stopped_router_uses_A.median_ms)} ms.</>} lead={<>{fo.totals.searches} searches across three runs (the chart and table show run 3, {fo.series.length} searches): <strong>{fo.totals.errors} errors and {fo.totals.partial_answers} partial answers</strong>. While B shut down, every search used a second copy from host A (a hollow ring); the median moved from {f(fo.phases.before_stop.median_ms)} to {f(fo.phases.B_stopped_router_uses_A.median_ms)} ms.</>}
          source="runs/aws-failover.jsonl and runs/aws-failover.summary.json">
          <p className="bar-key" style={{ marginTop: 14 }}>● one search · ○ a search where the router had to use a second copy because the first one failed.</p>
          <div style={{ marginTop: 6 }}><Scatter points={fo.series} label={`${fo.series.length} searches while a shard host was switched off, milliseconds each; hollow rings mark failovers`} /></div>
          <div style={{ marginTop: 16 }}>
            <div className="aws-head lg dim"><div>phase of run 3</div><div className="num">searches</div><div className="num">median ms</div><div className="num">slowest ms</div><div className="num">second copy used</div></div>
            {Object.entries(fo.phases).map(([k, v]) => (
              <div className="aws-line" key={k}><div style={{ fontWeight: 600 }}>{phaseNames[k] ?? k}</div><div className="num mono" data-label="searches">{v.n}</div><div className="num mono" data-label="median ms">{f(v.median_ms)}</div><div className="num mono" data-label="slowest ms">{f(v.max_ms)}</div><div className="num mono" data-label="second copy used">{v.requests_with_failover} of {v.n}</div></div>
            ))}
          </div>
          <p style={{ margin: '12px 0 0', fontSize: 14, lineHeight: '21px', color: 'var(--z4)', maxWidth: '76ch' }}>Limit: the stop and start times were not logged, so the phases are inferred from when failovers appeared. The chart and the table are both run 3.</p>
        </Section>
      )}

      {aws.loadtest && (
        <Section title="How many searches at once" plain={<>The limit is about <strong>{f(plateauRate, 1)} searches per second</strong>, because every search first needs one shared step that uses all the machine's power. These machines were small (2 processors each), so this is not comparable with the laptop test below. {cliff ? <>At {cliff.concurrency} people at once, every one of {cliff.requests} searches failed after waiting 5 seconds.</> : null}</>} lead={<>Throughput plateaus near <strong>{f(plateauRate, 1)} searches per second</strong> from 2 to 16 at once: the encoder uses all of the router host's two CPUs, and latency is about "in flight ÷ throughput". {cliff ? <>At {cliff.concurrency} at once, all {cliff.requests} failed at the router's 5 s encoder timeout (a cliff, not a slope).</> : null}</>}
          source="runs/aws-loadtest.summary.json (table copied by hand from the run output; the raw log is partial)">
          <div style={{ marginTop: 16 }}>
            <div className="aws-head six lg dim"><div>at once</div><div className="num">answers per second</div><div className="num">p50 ms</div><div className="num">p99 ms</div><div className="num">failed</div><div className="num">CPU busy</div></div>
            {aws.loadtest.levels.map((l) => (
              <div className="aws-line six" key={l.concurrency}>
                <div style={{ fontWeight: 600 }}>{l.concurrency} at once</div><div className="num mono" data-label="answers per second">{l.errors >= l.requests ? '—' : f(l.req_per_s, 1)}</div><div className="num mono" data-label="p50 ms">{f(l.p50_ms)}</div><div className="num mono" data-label="p99 ms">{f(l.p99_ms)}</div><div className="num mono" data-label="failed">{l.errors} of {l.requests}</div><div className="num mono" data-label="CPU busy">{f(l.cpu_busy_pct)}%</div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {aws.overload && (
        <Section title='Past the limit: say "busy", do not fail slowly' plain={<>The first version failed slowly when overloaded, and kept working for people who had already left. Two fixes: drop work nobody is waiting for, and answer "busy, try again" in about {f(aws.overload.variants.v2.hardest_level.shed_p50_ms ?? 0, 0)} ms. Neither adds capacity. With the fix, no search failed: the extra ones were told "busy" within milliseconds.</>} lead={<>The cliff above was not only a limit: the encoder kept computing searches for callers who had already given up (the encoder's log, copied by hand into the experiment notes, shows searches finishing 26.8 s and 37.5 s later against a 5 s deadline), so a later, gentle test failed too. Two fixes were measured the same way: 32 searches at once, 320 requests. Neither adds capacity (about {f(plateauRate, 0)} per second either way); step 2 turns silent 5 s timeouts into a clear "busy" in about {f(aws.overload.variants.v2.hardest_level.shed_p50_ms ?? 0, 0)} ms.</>}
          source="runs/aws-overload-experiment.jsonl and .summary.json (machine-logged; one run per variant)">
          <div style={{ marginTop: 16 }}>
            <OverloadRow name="Before" what="Every request goes to the encoder at once, with no limit." v={aws.overload.variants.baseline} />
            <OverloadRow name="Fix 1" what="The encoder does 2 at a time and drops work nobody is waiting for any more." v={aws.overload.variants.v1} />
            <OverloadRow name="Fix 2" what="Also refuses new requests past 12 in flight (HTTP 429, with retry-after)." v={aws.overload.variants.v2} />
          </div>
          {aws.overload.rebuilt.length > 0 && (
            <p className="doc-p" style={{ marginTop: 14, maxWidth: '76ch' }}>
              <strong>Control on rebuilt machines.</strong> All three machines were deleted and rebuilt from the repository with no hand-tuning; step 2 came from the code defaults. Answers per second at {aws.overload.rebuilt.map((l) => `${l.concurrency} at once`).join(', ')}: {aws.overload.rebuilt.map((l) => f(l.goodput_per_s, 2)).join(', ')}; failed: {aws.overload.rebuilt.reduce((n, l) => n + (l.errors ?? 0), 0)}. <span className="mono dim" style={{ fontSize: 12 }}>runs/aws-rebuilt-loadtest.jsonl</span>
            </p>
          )}
          <p className="bar-key">Solid = answered, hatched = refused quickly (a clear "busy", the caller can retry), cross-hatched = failed after waiting. Limits: each caller retries at once when refused, so the answered <em>count</em> is an artefact (compare answers per second); one run per variant; the limit of 12 is a guess, no other value was tried.</p>
        </Section>
      )}

      {aws.ingest && (
        <Section title="Adding products with a machine off" plain={<>New products arrive through a queue. The first worker crashed in a loop when a machine was off and wrongly set messages aside. The tests found it and it was fixed. The fixes are listed inside.</>} lead={<>Products are sent through a queue; both copies of each shard must end with the same products. {String(aws.ingest.totals)}. The first version of the worker crash-looped and sent {aws.ingest.replicaOff.dlqWhileDown} messages to the dead-letter queue; the tests found it, the fixes are listed below.</>}
          source="runs/aws-ingest.summary.json (numbers copied by hand from command output, not written by a script)">
          <ul style={{ margin: '14px 0 0', paddingLeft: '1.1em', fontSize: 15, lineHeight: '23px' }}>
            {aws.ingest.bugs.map((b) => <li key={b}>{b}</li>)}
          </ul>
        </Section>
      )}

      <Shots />
    </section>
  )
}
