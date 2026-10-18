// What a run costs, in one short table: time, memory held and money, per part of the run. Every number is measured or read from a logged file; where a number
// cannot be known (a provider's price you did not give, the AWS bill that has not been read) the cell says so instead of guessing.
import evidence from 'virtual:evidence'
import type { BrainSetting } from '../brain'
import { KNOWN_PRICES } from '../brain'
import type { StageId, StepState } from '../trace'

export type Resources = {
  server: { rss_mb: number | null; peak_mb: number }
  ollama: { name: string; size_mb: number; vram_mb: number }[]
  cluster: { name: string; rss_mb: number }[]
  computer: { cpus: number | null; memory_gb: number | null }
  measured?: string
}

const mem = (mb: number) => (mb >= 1000 ? `${(mb / 1000).toFixed(1)} GB` : `${Math.round(mb)} MB`)
const usd = (x: number) => (x === 0 ? '$0' : x < 0.01 ? `$${x.toPrecision(2)}` : `$${x.toFixed(3)}`)
const sec = (x: number | null | undefined) => (x == null ? '—' : x < 0.01 ? '<0.01 s' : `${x.toFixed(2)} s`)
// the project's own running estimate (project notes, 2026-10-16): not a logged run and not the bill, so it is always labelled as an estimate
const AWS_PER_HOUR_USD = 0.1

export function CostPanel({ steps, mode, brain, live, recorded }: { steps: Record<StageId, StepState>; mode: 'live' | 'recorded' | 'demo'; brain: BrainSetting; live: Resources | null; recorded: Resources | null }) {
  const res = mode === 'recorded' ? recorded : live
  const t = (id: StageId) => (steps[id].status === 'done' ? steps[id].seconds : null)
  const other = (['request', 'expand', 'compose', 'outfit'] as StageId[]).reduce((n, id) => n + (t(id) ?? 0), 0)
  const total = (['request', 'understand', 'expand', 'search', 'compose', 'outfit'] as StageId[]).reduce((n, id) => n + (t(id) ?? 0), 0)

  // reading the sentence
  const usage = (steps.understand.payload as { usage?: { input_tokens: number; output_tokens: number } }).usage
  const onDevice = mode === 'live' && brain.kind === 'device'
  const byKey = mode === 'live' && brain.kind !== 'local' && !onDevice
  const known = KNOWN_PRICES[brain.model || (brain.kind === 'anthropic' ? 'claude-haiku-5-5' : '')]
  const pIn = (brain.priceIn ?? '').trim() !== '' ? Number(brain.priceIn) : known?.[0]
  const pOut = (brain.priceOut ?? '').trim() !== '' ? Number(brain.priceOut) : known?.[1]
  const understandMoney = onDevice ? { text: '$0', note: 'the model runs on your own device' } : byKey
    ? usage && pIn != null && pOut != null && Number.isFinite(pIn) && Number.isFinite(pOut)
      ? { text: usd((usage.input_tokens * pIn + usage.output_tokens * pOut) / 1e6), note: `${usage.input_tokens} in + ${usage.output_tokens} out tokens` }
      : usage ? { text: 'give a price', note: `${usage.input_tokens} in + ${usage.output_tokens} out tokens; enter your provider's price per million tokens in Settings` } : { text: '—', note: 'the provider sent no token counts' }
    : { text: '$0', note: 'the model runs on this computer' }
  const model = res?.ollama[0]
  const understandMem = onDevice ? { text: 'none here', note: 'it runs on your own device' } : byKey ? { text: 'none here', note: 'it runs at your provider' } : model ? { text: mem(model.size_mb), note: `${model.name}, kept in memory by Ollama` } : { text: '—', note: 'Ollama reported no loaded model' }

  // searching
  const cluster = res?.cluster ?? []
  const clusterMb = cluster.reduce((n, c) => n + c.rss_mb, 0)
  const searchMem = res?.server.rss_mb != null ? { text: mem((res.server.rss_mb ?? 0) + clusterMb), note: cluster.length ? `web server ${mem(res.server.rss_mb)} + local cluster ${mem(clusterMb)} (${cluster.length} processes)` : `the web server; the product lists are not on this computer in this run` } : { text: '—', note: '' }

  // the Viewer's comparison: what reading a sentence costs with Claude, from the real ledger
  const claude = evidence.claudeSpend.filter((r) => r.purpose.startsWith('plan-comparison') && r.model.includes('sonnet')).sort((a, b) => b.calls - a.calls)[0]
  const plateau = evidence.aws.loadtest?.levels.filter((l) => l.concurrency >= 2 && l.concurrency <= 16) ?? []
  const rate = plateau.length ? plateau.reduce((n, l) => n + l.req_per_s, 0) / plateau.length : 0
  const aws = mode === 'recorded' && rate > 0 ? { limit: AWS_PER_HOUR_USD / (rate * 3600), one: AWS_PER_HOUR_USD / 3600 } : null

  const rows: { part: string; time: string; mem: { text: string; note: string }; money: { text: string; note: string } }[] = [
    { part: 'Reading your sentence', time: sec(t('understand')), mem: understandMem, money: understandMoney },
    { part: 'Finding products', time: sec(t('search')), mem: searchMem,
      money: mode === 'recorded' ? { text: aws ? `~$${Math.round(aws.limit * 1e6)} per million searches` : '—', note: 'on AWS at its measured limit (machines cost about $0.10 an hour: an estimate)' } : { text: '$0', note: 'this computer (its electricity is not counted)' } },
    { part: 'Everything else', time: sec(other), mem: { text: 'included', note: '' }, money: { text: '$0', note: 'plain code' } },
  ]
  return (
    <section id="cost" aria-label="What this run cost" className="cost">
      <h2 className="cost-h">What this run cost</h2>
      <p className="cost-lead">{mode === 'recorded' ? `Time is from the recorded run. Memory was measured on the computer that recorded it (${res?.computer.memory_gb ?? '?'} GB, ${res?.computer.cpus ?? '?'} processors).` : `Measured on this computer (${res?.computer.memory_gb ?? '?'} GB memory, ${res?.computer.cpus ?? '?'} processors).`} Memory used is what the programs keep in the computer's working memory while they run.</p>
      <div className="cost-table" role="table" aria-label="Time, memory and money per part of the run">
        <div className="cost-row head" role="row"><div role="columnheader">Part</div><div role="columnheader">Time</div><div role="columnheader">Memory used</div><div role="columnheader">Money</div></div>
        {rows.map((r) => (
          <div className="cost-row" role="row" key={r.part}>
            <div role="cell" className="cost-part">{r.part}</div>
            <div role="cell" className="mono" data-label="Time">{r.time}</div>
            <div role="cell" data-label="Memory used"><strong>{r.mem.text}</strong>{r.mem.note && <span className="dim">{r.mem.note}</span>}</div>
            <div role="cell" data-label="Money"><strong>{r.money.text}</strong>{r.money.note && <span className="dim">{r.money.note}</span>}</div>
          </div>
        ))}
        <div className="cost-row total" role="row"><div role="cell" className="cost-part">Whole run</div><div role="cell" className="mono" data-label="Time">{sec(total)}</div>
          <div role="cell" data-label="Memory used"><strong>{res ? mem((byKey ? 0 : model?.size_mb ?? 0) + (res.server.rss_mb ?? 0) + clusterMb) : '—'}</strong></div>
          <div role="cell" data-label="Money"><strong>{byKey && understandMoney.text.startsWith('$') ? understandMoney.text : aws ? `~$${Math.round(aws.limit * 1e6)} per million searches` : '$0'}</strong>{byKey && !understandMoney.text.startsWith('$') ? <span className="dim">add a price to see it</span> : aws ? <span className="dim">estimate, AWS search only</span> : null}</div></div>
      </div>
      {mode === 'recorded' && claude && (
        <p className="cost-note">
          <strong>If Claude read the sentence instead:</strong> {claude.calls} real requests cost {usd(claude.cost_usd / claude.calls)} each (about {Math.round(claude.input_tokens / claude.calls)} tokens in and {Math.round(claude.output_tokens / claude.calls)} out; a token is roughly three quarters of a word). The local model costs no money but uses {res?.ollama[0] ? mem(res.ollama[0].size_mb) : 'its'} of memory. <span className="mono dim">runs/claude-spend.jsonl</span>
        </p>
      )}
      <details className="cmp-exact">
        <summary>How these numbers are worked out</summary>
      {aws && <p className="cost-note"><strong>AWS, at one search per second:</strong> about ${Math.round(aws.one * 1e6)} per million searches. This is an estimate: three machines at about $0.10 an hour, from the project's notes. The real bill has not been read yet. The machines have been deleted, so nothing is billing now.</p>}
      <p className="cost-note">{byKey ? 'Money for your key = tokens your provider reported × its price per million tokens. Known Claude models fill the price in; for others, enter yours in Settings. Your provider\'s invoice is the truth.' : 'Electricity, wear on your computer and network use are not counted.'}</p>
      </details>
    </section>
  )
}
