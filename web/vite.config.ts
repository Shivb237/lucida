import react from '@vitejs/plugin-react'
import fs from 'node:fs'
import path from 'node:path'
import { defineConfig, type Plugin } from 'vite'

const ROOT = path.resolve(__dirname, '..')
const RUNS = path.join(ROOT, 'runs')

const readJson = (file: string) => {
  const p = path.join(RUNS, file)
  return fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, 'utf8')) : null
}
const readJsonl = (file: string): Record<string, unknown>[] => {
  const p = path.join(RUNS, file)
  if (!fs.existsSync(p)) return []
  return fs.readFileSync(p, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l))
}

type Metric = { mean: number; ci95: [number, number] }
const strip = (file: string) => {
  const s = readJson(file)
  if (!s) return { file: `runs/${file}`, logged: false }
  return { file: `runs/${file}`, logged: true, date: String(s.setup?.date ?? '').slice(0, 10), nQueries: s.setup?.n_queries,
    nProducts: s.setup?.n_products, ndcg10: s.metrics.ndcg10 as Metric, recall50: s.metrics.recall50.mean as number }
}

// AWS runs (Mumbai, recorded 2026-10-16): only whitelisted fields are passed to the page, never whole files, so no machine id, address or bucket path can reach a public build
const awsSeries = (file: string) => readJsonl(file).map((r) => ({ t: r.t as number, total_ms: r.total_ms as number | null, shards_ms: r.shards_ms as number | null, hedged: r.hedged as number, failovers: r.failovers as number,
  partial: r.partial as boolean, status: r.status as number }))
function aws() {
  const fo = readJson('aws-failover.summary.json')
  const ov = readJson('aws-overload-experiment.summary.json')
  const lt = readJson('aws-loadtest.summary.json')
  const ing = readJson('aws-ingest.summary.json')
  // aws-failover.jsonl holds three probe runs back to back (the clock t restarts at 0): run 1 is 120 healthy searches, run 3 is the one the summary table describes
  const all = awsSeries('aws-failover.jsonl')
  const starts = all.flatMap((r, i) => (r.t === 0 ? [i] : []))
  if (all.length && starts.length !== 3) throw new Error(`aws-failover.jsonl should hold 3 probe runs, found ${starts.length}: the AWS section would show the wrong runs`)
  const run1 = all.slice(starts[0] ?? 0, starts[1] ?? all.length)
  const run3 = all.slice(starts[2] ?? 0)
  return {
    healthy: run1,
    failover: fo && { phases: fo.run3, healthy120: fo.run1_healthy_120s, totals: fo.totals, note: fo.note as string, series: run3 },
    overload: ov && { setting: ov.setting as string, variants: ov.variants, rebuilt: ov.rebuilt_control?.levels ?? [] },
    loadtest: lt && { levels: lt.levels, reading: lt.reading },
    ingest: ing && { baseline: ing.baseline_products_per_shard, happy: ing.test1_happy_path, dedup: ing.test1b_dedup, replicaOff: { sent: ing.test2_replica_machine_off?.sent,
      dlqWhileDown: ing.test2_replica_machine_off?.messages_in_dlq_when_B_still_down, cause: ing.test2_replica_machine_off?.cause_of_dlq },
      permanent: { sent: ing.test3_permanent_error?.sent }, totals: ing.totals, bugs: ing.bugs_found_by_the_tests, source: ing.source },
  }
}

/** Every number on the Evidence page is read here, from the logged run files, each time the app starts or builds. */
function evidence() {
  const m2 = readJson('m2.summary.json')
  const gen = readJsonl('gen_sd15.jsonl')
  const drawn = new Map(readJsonl('m2-gen-resnet50.jsonl').map((r) => [r.query_id, r.ndcg10 as number]))
  const words = new Map(readJsonl('m2-direct-text.jsonl').map((r) => [r.query_id, r.ndcg10 as number]))
  const m2Method = (key: string) => m2 && { file: 'runs/m2.summary.json', logged: true, date: String(m2.setup.date).slice(0, 10),
    ndcg10: m2.metrics[key].ndcg10 as Metric, recall50: m2.metrics[key].recall50.mean as number,
    paired: m2.paired_vs_direct_text?.[key]?.ndcg10 ?? null }
  return {
    pilot: {
      random: strip('random.summary.json'), bm25: strip('bm25.summary.json'), siglipBase: strip('siglip-base.summary.json'),
      marqo: strip('marqo-fashionsiglip.summary.json'), siglip2: strip('siglip2-base-384.summary.json'),
      zooclaw: strip('zooclaw-fashionsiglip2.summary.json'),
      siglip2Bug: strip('siglip2-base-384.BUG-no-lowercase.summary.json'), zooclawBug: strip('zooclaw-fashionsiglip2.BUG-no-lowercase.summary.json'),
    },
    drawing: {
      text: m2Method('direct-text'), textGen: m2Method('text+gen-fashionsiglip'),
      genFashion: m2Method('gen-fashionsiglip'), genResnet: m2Method('gen-resnet50'),
      frames: gen.map((g) => ({ queryId: String(g.query_id), query: g.query as string, seconds: g.seconds as number,
        image: `drawings/${g.query_id}.jpg`, drawn: drawn.get(g.query_id) ?? null, words: words.get(g.query_id) ?? null })),
    },
    scale: {
      random: strip('scale-random.summary.json'), bm25: strip('scale-bm25.summary.json'),
      marqo: strip('scale-marqo-fashionsiglip.summary.json'), siglipBase: strip('scale-siglip-base.summary.json'),
    },
    // human-rated tests and the knowledge graph (Milestones 4-5): summaries written by scripts/summarise_blind.py and the eval scripts
    findings: {
      blind4: readJson('blind-test4.summary.json'), blind3: readJson('blind-test3.summary.json'), heldout: readJson('m4-heldout-ratings.summary.json'),
      graph: readJson('graph-holdout.summary.json'), outfit: readJson('outfit-ratings.summary.json'), outfitObjective: readJson('outfit-objective.summary.json'),
    },
    aws: aws(),
    // what the real Claude calls cost (the project's own ledger, written by src/genkart/claude_client.py): per purpose, never the key or the prompts
    claudeSpend: (() => {
      const by = new Map<string, { purpose: string; model: string; calls: number; input_tokens: number; output_tokens: number; cost_usd: number }>()
      for (const r of readJsonl('claude-spend.jsonl')) {
        const k = `${r.purpose}|${r.model}`
        const e = by.get(k) ?? { purpose: String(r.purpose), model: String(r.model), calls: 0, input_tokens: 0, output_tokens: 0, cost_usd: 0 }
        e.calls += 1; e.input_tokens += Number(r.input_tokens); e.output_tokens += Number(r.output_tokens); e.cost_usd += Number(r.cost_usd)
        by.set(k, e)
      }
      return [...by.values()]
    })(),
    judge5: (() => { const j = readJson('judge-test5.summary.json'); return j && { agreement: j.agreement as number, kappa: j.weighted_kappa as number, n: j.n_options as number } })(),
    // the understanding step (Milestone 4): 650 messy rewrites of labelled queries, three ways of searching the same index
    understanding: (() => { const m = readJson('m4.summary.json')?.results?.valid_rewrites
      return m && { n: readJson('m4.summary.json').setup.n_valid as number, original: m['embed-original'].ndcg10.mean as number, raw: m['embed-raw'].ndcg10.mean as number, understood: m['embed-understood'].ndcg10.mean as number } })(),
    blind5: readJson('blind-test5.summary.json'), guard: readJson('guard.summary.json'), claudeVsQwen: readJson('claude-vs-qwen.summary.json'),
    feedback: readJson('feedback-sim.summary.json'),
    // the distributed system (Milestone 6): router, shards, replicas, failures, ingestion
    system: {
      e2e: readJson('router-e2e.summary.json'), chaos: readJson('chaos.summary.json'), replicas: readJson('chaos-replicas.summary.json'),
      ingest: readJson('ingest.summary.json'), equivalence: readJson('sharding-equivalence.summary.json'),
    },
  }
}

function genkartLocal(): Plugin {
  const id = 'virtual:evidence'
  return {
    name: 'genkart-local',
    resolveId: (source) => (source === id ? '\0' + id : null),
    load: (source) => (source === '\0' + id ? `export default ${JSON.stringify(evidence())}` : null),
  }
}

export default defineConfig({
  base: process.env.VITE_BASE ?? '/',   // GitHub Pages serves a project at /<repo-name>/: the workflow sets VITE_BASE
  plugins: [react(), genkartLocal()],
  server: { proxy: { '/api': process.env.GENKART_API ?? 'http://localhost:8000' } },   // GENKART_API points the dev page at a server on another port
})
