import react from '@vitejs/plugin-react'
import fs from 'node:fs'
import path from 'node:path'
import { defineConfig, type Plugin } from 'vite'

const ROOT = path.resolve(import.meta.dirname, '..')
const RUNS = process.env.EVIDENCE_RUNS_DIR ?? path.join(ROOT, 'runs')   // the override is only for testing the warnings path

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

// Optional second-rater agreement (written by scripts/analyze_agreement.py once a second person has rated a blind sheet). A missing file changes
// nothing and is not a warning: the pages keep saying "one rater". A file that exists but lacks the fields below is an error (a warning in claims()).
// Only these fields reach the page; rater ids are reduced to a count.
type Agreement = { file: string; test: string; date: string; raters: number; nItems: number; weightedKappa: Metric; agreementPct: Metric | null }
const AGREEMENT_FILES = { test4: 'blind-test4-agreement.summary.json', test5: 'blind-test5-agreement.summary.json' } as const
function readAgreement(file: string): Agreement | null {
  const a = readJson(file)
  if (!a) return null
  const wk = a.weighted_kappa, ci = wk?.ci95
  const ids = a.setup?.rater_ids
  if (typeof wk?.value !== 'number' || !Array.isArray(ci) || ci.length !== 2 || typeof a.n_items !== 'number' || !Array.isArray(ids) || ids.length < 2)
    throw new Error(`runs/${file} lacks weighted_kappa.value, weighted_kappa.ci95, n_items or two setup.rater_ids`)
  return { file: `runs/${file}`, test: String(a.setup?.test ?? ''), date: String(a.setup?.date ?? '').slice(0, 10), raters: ids.length, nItems: a.n_items,
    weightedKappa: { mean: wk.value, ci95: [ci[0], ci[1]] }, agreementPct: typeof a.agreement?.pct === 'number' ? { mean: a.agreement.pct, ci95: a.agreement.ci95 } : null }
}
const agreements = () => {
  const safe = (f: string) => { try { return readAgreement(f) } catch { return null } }   // claims() reports a malformed file; the other pages fall back to "one rater"
  return { test4: safe(AGREEMENT_FILES.test4), test5: safe(AGREEMENT_FILES.test5) }
}

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

/** The older, per-page shape (System, AwsTour, CostPanel, docs.ts and the Search page read it). Kept as it was. */
function legacy() {
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
      steps: [...new Set(gen.map((g) => g.steps as number))],
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
    agreement: agreements(),
    blind5: readJson('blind-test5.summary.json'), guard: readJson('guard.summary.json'), claudeVsQwen: readJson('claude-vs-qwen.summary.json'),
    feedback: readJson('feedback-sim.summary.json'), checksEval: readJson('checks-eval.summary.json'),
    // the distributed system (Milestone 6): router, shards, replicas, failures, ingestion
    system: {
      e2e: readJson('router-e2e.summary.json'), chaos: readJson('chaos.summary.json'), replicas: readJson('chaos-replicas.summary.json'),
      ingest: readJson('ingest.summary.json'), equivalence: readJson('sharding-equivalence.summary.json'),
    },
  }
}

// ---------------------------------------------------------------------------------------------------------------------------------------------
// The Evidence claims: one small adapter per research question, each reading only logged run files. The verdict is never typed: it is computed
// from the 95% range against a reference (zero for a difference), knowing which direction is "better" for that claim. A file that cannot be read
// becomes a warning and a card that says "not computed yet"; the build prints the warnings and stops only when EVIDENCE_STRICT=1.
type Verdict = 'helped' | 'no clear effect' | 'hurt'
type EScale = 'retrieval' | 'rating' | 'rate' | 'count'
type ClaimId = 'model' | 'drawing' | 'collections' | 'plan' | 'graph' | 'colour' | 'likes' | 'judge' | 'checks' | 'guard' | 'data'
type Effect = {
  key: string; label: string; sub?: string; scale: EScale; mean: number; ci95: [number, number] | null; n: number | null
  better?: number; tied?: number; worse?: number; ref: number | null; refLabel?: string; higherIsBetter: boolean
  verdict: Verdict | null; rule: string; forest: boolean; digits: number; file: string; unit?: string
}
type LevelRow = { name: string; sub?: string; mean: number; ci95: [number, number] | null; n?: number | null; inUse?: boolean; old?: boolean; value?: string }
type Level = { title: string; note?: string; scale: EScale; domain?: [number, number]; ref?: number | null; digits: number; bars?: boolean; fold?: boolean; rows: LevelRow[] }
type Table = { title: string; head: string[]; num: boolean[]; rows: string[][]; note?: string }
type Source = { file: string; script?: string }
type Claim = {
  id: ClaimId; num: string; short: string; question: string; scale: EScale; status: 'ok' | 'partial' | 'missing'; missing: string[]
  effect: Effect | null; effects: Effect[]; verdict: Verdict | null; verdictLabel: string | null; answer: string[]
  method: string[]; measured: [string, string][]; limits: string[]; test_set: string; date: string; sources: Source[]
  levels: Level[]; tables: Table[]
}

const MINUS = '−'
const fx = (x: number, d = 2) => (Math.abs(x) < 0.5 * 10 ** -d ? 0 : x).toFixed(d).replace('-', MINUS)
const sg = (x: number, d = 2) => { const t = fx(x, d); return t.startsWith(MINUS) ? t : `+${t}` }
const rng = (ci: [number, number], d = 2) => `${sg(ci[0], d)} to ${sg(ci[1], d)}`
const int = (x: number) => Math.round(x).toLocaleString('en')
const pc = (x: number, d = 1) => `${(x * 100).toFixed(d)}%`
const day = (v: unknown) => (v ? String(v).slice(0, 10) : '')
const VERDICT_WORDS: Record<Verdict, string> = { helped: 'Helped', 'no clear effect': 'No clear effect', hurt: 'Hurt' }
const RULE_CI = 'Clear only when the whole 95% range sits on one side of the reference.'
const RULE_SIGN = 'Clear only when a sign test on the requests that changed gives p below 0.05.'

/** The verdict from an interval: clear when the whole 95% range is on one side of the reference, then "helped" or "hurt" by the claim's direction. */
function verdictOf(ci: [number, number] | null, ref: number | null, higherIsBetter: boolean): Verdict | null {
  if (!ci || ref == null) return null
  if (ci[0] > ref) return higherIsBetter ? 'helped' : 'hurt'
  if (ci[1] < ref) return higherIsBetter ? 'hurt' : 'helped'
  return 'no clear effect'
}
/** Exact two-sided sign test on the units that changed (better against worse): used only where a file logs counts but no range. */
function signP(better: number, worse: number) {
  const m = better + worse
  if (!m) return 1
  let tail = 0
  for (let k = 0; k <= Math.min(better, worse); k++) {
    let c = 1
    for (let i = 0; i < k; i++) c = (c * (m - i)) / (i + 1)
    tail += c / 2 ** m
  }
  return Math.min(1, 2 * tail)
}
/** Wilson 95% interval for a share k of n (closed form, nothing resampled). */
function wilson(k: number, n: number): [number, number] {
  if (!n) return [0, 1]
  const z = 1.959964, p = k / n, d = 1 + z * z / n
  const c = (p + z * z / (2 * n)) / d, h = (z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d
  return [Math.max(0, c - h), Math.min(1, c + h)]
}
type EffectIn = Omit<Effect, 'verdict' | 'ref' | 'higherIsBetter' | 'forest' | 'digits' | 'rule'> & Partial<Pick<Effect, 'ref' | 'higherIsBetter' | 'forest' | 'digits'>> & { equal?: number }
function effect(o: EffectIn): Effect {
  const { equal, ...e } = o
  const ref = e.ref === undefined ? 0 : e.ref
  const higherIsBetter = e.higherIsBetter ?? true
  const tied = e.tied ?? equal
  let verdict = verdictOf(e.ci95, ref, higherIsBetter), rule = RULE_CI
  if (!e.ci95 && ref != null && e.better != null && e.worse != null) {
    verdict = signP(e.better, e.worse) < 0.05 ? (e.better > e.worse ? 'helped' : 'hurt') : 'no clear effect'
    rule = RULE_SIGN
  }
  return { ...e, tied, ref, higherIsBetter, verdict, rule, forest: e.forest ?? true, digits: e.digits ?? 2 }
}
/** A paired block as the summaries write it ({mean, ci95, better, tied|equal, worse}), normalised. */
const pairedIn = (p: { mean: number; ci95: [number, number]; better?: number; tied?: number; equal?: number; worse?: number; n_prompts?: number }) => ({
  mean: p.mean, ci95: p.ci95, better: p.better, tied: p.tied ?? p.equal, worse: p.worse,
  n: p.n_prompts ?? (p.better != null && p.worse != null ? p.better + (p.tied ?? p.equal ?? 0) + p.worse : null),
})
const phrase = (v: Verdict | null) => (v === 'helped' ? 'a clear gain' : v === 'hurt' ? 'a clear loss' : v ? 'no clear difference' : 'no verdict yet')
const than = (v: Verdict | null) => (v === 'helped' ? 'clearly better' : v === 'hurt' ? 'clearly worse' : 'not clearly different')

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Opt = (file: string, read?: (f: string) => unknown) => any
type Base = Pick<Claim, 'id' | 'num' | 'short' | 'question' | 'scale' | 'sources'> & { words?: Partial<Record<Verdict, string>> }
type Body = Omit<Claim, keyof Base | 'status' | 'missing' | 'verdict' | 'verdictLabel' | 'effect'> & { effect?: Effect | null }

function claims() {
  const warnings: string[] = []
  const need = (file: string) => {
    const p = path.join(RUNS, file)
    if (!fs.existsSync(p)) throw new Error(`runs/${file} is missing`)
    return JSON.parse(fs.readFileSync(p, 'utf8'))
  }
  const needl = (file: string) => {
    const p = path.join(RUNS, file)
    if (!fs.existsSync(p)) throw new Error(`runs/${file} is missing`)
    return fs.readFileSync(p, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l) as Record<string, unknown>)
  }
  const out: Claim[] = []
  function add(base: Base, fn: (missing: string[], opt: Opt) => Body) {
    const missing: string[] = []
    const opt: Opt = (file, read = need) => {
      try { return read(file) } catch (e) { const m = `${base.id}: ${(e as Error).message}`; missing.push(m); warnings.push(m); return null }
    }
    try {
      const b = fn(missing, opt)
      const head = b.effect === undefined ? b.effects[0] ?? null : b.effect
      const v = head?.verdict ?? null
      out.push({ ...base, ...b, effect: head, verdict: v, verdictLabel: v ? (base.words?.[v] ?? VERDICT_WORDS[v]) : null, status: missing.length ? 'partial' : 'ok', missing })
    } catch (e) {
      const m = `${base.id}: ${(e as Error).message}`
      warnings.push(m)
      out.push({ ...base, status: 'missing', missing: [...missing, m], effect: null, effects: [], verdict: null, verdictLabel: null, answer: ['Not computed yet.'],
        method: [], measured: [], limits: [], test_set: '', date: '', levels: [], tables: [] })
    }
  }
  const S = (file: string, script?: string): Source => ({ file: `runs/${file}`, ...(script ? { script: `scripts/${script}` } : {}) })
  const lead = (v: Verdict | null, yes: string, unclear: string, no: string, none = 'Not computed yet.') => (v === 'helped' ? yes : v === 'hurt' ? no : v ? unclear : none)
  // second-rater agreement: absent is silent (one rater stays the wording); present but malformed is a warning
  const agree = (k: keyof typeof AGREEMENT_FILES) => {
    if (!fs.existsSync(path.join(RUNS, AGREEMENT_FILES[k]))) return null
    try { return readAgreement(AGREEMENT_FILES[k]) } catch (e) { warnings.push(`agreement: ${(e as Error).message}`); return null }
  }
  const nWord = (n: number) => ['zero', 'one', 'two', 'three', 'four', 'five'][n] ?? String(n)
  const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1)
  const raters = (a: Agreement) => {
    const k = a.weightedKappa
    return `${nWord(a.raters)} raters, weighted kappa ${fx(k.mean)} [${fx(k.ci95[0])}, ${fx(k.ci95[1])}] (${a.nItems} options). The author, one of them, wrote the requests.`
  }
  const agreeSource = (a: Agreement | null): Source[] => (a ? [{ file: a.file, script: 'scripts/analyze_agreement.py' }] : [])

  // 01 · which retrieval model: levels from the scale summaries; the paired differences from runs/evidence-paired.summary.json
  add({ id: 'model', num: '01', short: 'Which search model?', question: 'Which way of searching finds the right products?', scale: 'retrieval',
    sources: [S('evidence-paired.summary.json', 'evidence_paired.py'), S('scale-marqo-fashionsiglip.summary.json', 'run_eval.py'), S('scale-siglip-base.summary.json', 'run_eval.py'), S('scale-bm25.summary.json', 'run_eval.py'), S('marqo-fashionsiglip.summary.json', 'run_eval.py')] },
  (missing, opt) => {
    const mq = need('scale-marqo-fashionsiglip.summary.json'), sig = need('scale-siglip-base.summary.json'), bm = need('scale-bm25.summary.json')
    const rnd = opt('scale-random.summary.json')
    const paired = opt('evidence-paired.summary.json') as { pairs: { id: string; n: number; metrics: Record<string, { mean: number; ci95: [number, number]; better: number; tied?: number; equal?: number; worse: number }> }[] } | null
    if (!paired) missing.push('Search-by-search differences not computed yet: run scripts/evidence_paired.py.')
    const pe = (id: string, label: string, sub: string) => {
      const p = paired?.pairs?.find((x) => x.id === id)
      if (paired && !p) { const m = `model: pair ${id} not in runs/evidence-paired.summary.json`; missing.push(m); warnings.push(m) }
      return p ? effect({ key: id, label, sub, scale: 'retrieval', ...pairedIn(p.metrics.ndcg10), n: p.n, digits: 3, file: 'runs/evidence-paired.summary.json' }) : null
    }
    const effects = [pe('scale-marqo-vs-siglip', 'Fashion model minus general model', 'bigger test'), pe('scale-marqo-vs-bm25', 'Fashion model minus keyword search', 'bigger test'),
      pe('pilot-marqo-vs-siglip', 'Fashion model minus general model', 'first test'), pe('pilot-marqo-vs-bm25', 'Fashion model minus keyword search', 'first test')].filter((e): e is Effect => !!e)
    const row = (s: { metrics: { ndcg10: { mean: number; ci95: [number, number] } }; setup: { n_queries: number } }, name: string, sub: string, extra: Partial<LevelRow> = {}): LevelRow =>
      ({ name, sub, mean: s.metrics.ndcg10.mean, ci95: s.metrics.ndcg10.ci95, n: s.setup.n_queries, ...extra })
    const pilot = ([['random', 'Random', 'the floor'], ['bm25', 'Keyword search (BM25)', 'words in titles'], ['siglip-base', 'SigLIP base', 'general model'],
      ['marqo-fashionsiglip', 'Marqo-FashionSigLIP', 'fashion-trained · in use'], ['siglip2-base-384', 'Google SigLIP 2', 'newer, general'], ['zooclaw-fashionsiglip2', 'ZooClaw-FashionSigLIP2', 'newer, fashion-trained'],
      ['siglip2-base-384.BUG-no-lowercase', 'SigLIP 2, first run', 'superseded: lowercasing bug'], ['zooclaw-fashionsiglip2.BUG-no-lowercase', 'ZooClaw, first run', 'superseded: lowercasing bug']] as const)
      .map(([f, name, sub]) => { const s = opt(`${f}.summary.json`); return s ? row(s, name, sub, { inUse: f === 'marqo-fashionsiglip', old: f.includes('BUG') }) : null }).filter((r): r is LevelRow => !!r)
    const h = effects[0] ?? null
    const nq = mq.setup.n_queries as number, np = mq.setup.n_products as number
    return {
      effects,
      answer: [
        lead(h?.verdict ?? null, 'Yes: the fashion-trained model ranks the right products best.', 'The fashion-trained model is not clearly ahead.', 'No: the fashion-trained model ranks worse.',
          `The fashion-trained model ${mq.metrics.ndcg10.mean > Math.max(sig.metrics.ndcg10.mean, bm.metrics.ndcg10.mean) ? 'scored highest' : 'did not score highest'}. The search-by-search check is not computed yet.`),
        `It scored ${fx(mq.metrics.ndcg10.mean)} on a match score from 0 to 1 (higher is better).`,
        `A general model scored ${fx(sig.metrics.ndcg10.mean)}; keyword search scored ${fx(bm.metrics.ndcg10.mean)}.`,
        ...(h ? [`Search by search, the lead over the general model is ${sg(h.mean, 3)}.`] : []),
      ],
      method: [
        `Each of ${int(nq)} labelled searches ran over ${int(np)} products with every method.`,
        'The match score (NDCG@10) says how high the right products sit in the top 10.',
        'The two models are compared on the same searches, one by one (paired).',
        `The 95% range comes from resampling the searches (bootstrap, seed ${mq.setup.seed}).`,
      ],
      measured: [['Searches', int(nq)], ['Products', int(np)], ['Rater', `labels in the dataset (${mq.setup.dataset})`], ['Test set', 'bigger test (scale sample)'], ['Date', day(mq.setup.date)]],
      limits: ['The right answers are the dataset’s own labels, not shoppers’ choices.', 'The two newer models were only tried on the smaller first test.', 'Both tests come from one public dataset.'],
      test_set: `Bigger test: ${int(nq)} searches, ${int(np)} products`, date: day(mq.setup.date),
      levels: [
        { title: 'Match score, bigger test', note: '0 to 1 · higher is better', scale: 'retrieval', digits: 3,
          rows: [...(rnd ? [row(rnd, 'Random', 'the floor')] : []), row(bm, 'Keyword search (BM25)', 'words in titles'), row(sig, 'SigLIP base', 'general model'), row(mq, 'Marqo-FashionSigLIP', 'fashion-trained · in use', { inUse: true })] },
        { title: 'Match score, first test', note: 'a smaller sample · not comparable with the bigger test', scale: 'retrieval', digits: 3, fold: true, rows: pilot },
      ],
      tables: [{ title: 'Found in the top 50 (Recall@50), bigger test', head: ['Method', 'Share found', '95% range'], num: [false, true, true],
        rows: ([[bm, 'Keyword search (BM25)'], [sig, 'SigLIP base'], [mq, 'Marqo-FashionSigLIP']] as const).map(([s, n]) => [n, fx(s.metrics.recall50.mean, 3), `${fx(s.metrics.recall50.ci95[0], 3)} to ${fx(s.metrics.recall50.ci95[1], 3)}`]) }],
    }
  })

  // 02 · drawing first (the v1 idea): m2 paired differences against typed words
  add({ id: 'drawing', num: '02', short: 'Draw first?', question: 'Does drawing the outfit first help?', scale: 'retrieval', sources: [S('m2.summary.json', 'run_m2.py'), S('gen_sd15.jsonl', 'gen_images.py')],
    words: { hurt: 'Hurt: it made results worse' } }, () => {
    const m2 = need('m2.summary.json')
    const names: Record<string, [string, string]> = { 'direct-text': ['Words alone', 'direct text search · in use'], 'text+gen-fashionsiglip': ['Words plus drawing', 'both scores added'],
      'gen-fashionsiglip': ['Drawing only', 'drawing matched by the fashion model'], 'gen-resnet50': ['The v1 way', 'drawing matched by ResNet50'] }
    // the 20 searches are a sample of the first test's searches when every id is in that run and the product count matches; the label says so only then
    const pilot = readJson('marqo-fashionsiglip.summary.json'), pilotIds = new Set(readJsonl('marqo-fashionsiglip.jsonl').map((r) => r.query_id))
    const m2Ids = readJsonl('m2-direct-text.jsonl').map((r) => r.query_id)
    const fromPilot = !!pilot && m2Ids.length === m2.setup.n_queries && m2Ids.every((q) => pilotIds.has(q)) && pilot.setup.n_products === m2.setup.n_products
    const v1 = m2.metrics['gen-resnet50'].ndcg10.mean as number
    const effects = (['text+gen-fashionsiglip', 'gen-fashionsiglip', 'gen-resnet50'] as const).map((k) =>
      effect({ key: `drawing-${k}`, label: `${names[k][0]} minus words alone`, sub: names[k][1], scale: 'retrieval', ...pairedIn(m2.paired_vs_direct_text[k].ndcg10), digits: 3, file: 'runs/m2.summary.json' }))
      .sort((a, b) => b.mean - a.mean)   // the variant kindest to drawing first leads
    const h = effects[0]
    const t = m2.metrics['direct-text'].ndcg10.mean as number
    return {
      effects,
      answer: [
        lead(h.verdict, 'Yes: drawing first helped.', 'Not clearly: drawing first made no clear difference.', 'No: drawing the outfit first made results worse.'),
        `Words alone scored ${fx(t)} on the match score (0 to 1).`,
        `${h.mean < 0 ? 'Even the' : 'The'} best drawing variant (${names[h.key.replace('drawing-', '')][0].toLowerCase()}) scored ${fx(t + h.mean)}: ${sg(h.mean, 2)} search by search.`,
        `The v1 way, a drawing matched by ResNet50, scored ${fx(v1)}.`,
      ],
      method: [
        'An AI tool (Stable Diffusion) drew each request first.',
        'Products were then found by looking like the drawing.',
        `The same ${m2.setup.n_queries} searches were also run on the typed words alone, over ${int(m2.setup.n_products)} products.`,
        'Each variant is compared with typed words, search by search (paired).',
      ],
      measured: [['Searches', String(m2.setup.n_queries)], ['Products', int(m2.setup.n_products)], ['Rater', 'labels in the dataset'], ['Drawing model', String(m2.setup.generator)], ['Date', day(m2.setup.date)]],
      limits: [
        `Only ${m2.setup.n_queries} searches, on the small catalogue of ${int(m2.setup.n_products)} products, so the ranges are wide.`,
        'The right answers come from a shopping ranking for the typed words, so searching with words starts with an advantage.',
        'The drawing prompt was a fixed template, with no step that rewrites the request first.',
        'One drawing per search, from one random seed.',
        'Drawings often leave out the named colour or fabric.',
      ],
      test_set: fromPilot ? `${m2.setup.n_queries} of the ${pilot.setup.n_queries} searches from the first test, ${int(m2.setup.n_products)} products` : `${m2.setup.n_queries} searches, ${int(m2.setup.n_products)} products`,
      date: day(m2.setup.date),
      levels: [{ title: 'Match score', note: '0 to 1 · higher is better', scale: 'retrieval', digits: 3,
        rows: (['direct-text', 'text+gen-fashionsiglip', 'gen-fashionsiglip', 'gen-resnet50'] as const).map((k) => ({ name: names[k][0], sub: names[k][1], mean: m2.metrics[k].ndcg10.mean, ci95: m2.metrics[k].ndcg10.ci95, n: m2.setup.n_queries, inUse: k === 'direct-text' })) }],
      tables: [],
    }
  })

  // 03 · more product collections: blind test 4
  const ag4 = agree('test4'), ag5 = agree('test5')
  add({ id: 'collections', num: '03', short: 'More collections?', question: 'Did adding product collections help?', scale: 'rating', sources: [S('blind-test4.summary.json', 'summarise_blind.py'), ...agreeSource(ag4)] }, () => {
    const b4 = need('blind-test4.summary.json')
    const M = b4.methods, P = b4.paired
    const effects = [
      effect({ key: 'b4-B-A', label: 'Four collections minus one', sub: 'raw words both · blind test 4', scale: 'rating', ...pairedIn(P['B-A']), file: 'runs/blind-test4.summary.json' }),
      effect({ key: 'b4-C-A', label: 'AI plan and four collections minus one', sub: 'everything together · blind test 4', scale: 'rating', ...pairedIn(P['C-A']), file: 'runs/blind-test4.summary.json' }),
    ]
    const h = effects[0]
    return {
      effects,
      answer: [
        lead(h.verdict, 'Yes: adding collections helped.', 'Not clearly: more collections made no clear difference.', 'No: more collections made outfits worse.'),
        `A person’s rating rose from ${fx(M.A.mean)} to ${fx(M.B.mean)} out of 2.`,
        `Request by request, the gain was ${sg(h.mean)}.`,
        'A better-worded request cannot find clothes the list does not have.',
      ],
      method: [
        `${M.A.n_prompts} Indian-occasion requests were searched three ways.`,
        ag4 ? `${cap(nWord(ag4.raters))} people rated each outfit good (2), okay (1) or bad (0).` : 'One person rated each outfit good (2), okay (1) or bad (0).',
        ag4 ? 'The raters did not know which way made which outfit (blind).' : 'The rater did not know which way made which outfit (blind).',
        'The same requests are compared one by one (paired).',
      ],
      measured: [['Requests', String(M.A.n_prompts)], ['Options rated', String(b4.setup.n_options_rated)], ['Rater', ag4 ? `${nWord(ag4.raters)} people, blind; one is the author, who wrote the requests` : String(b4.setup.rater)], ['Test set', String(b4.setup.test)], ['Date', day(b4.setup.date)]],
      limits: [ag4 ? cap(raters(ag4)) : 'One rater, who also wrote the requests.', 'The requests are Indian occasions, where the first collection was weakest.', 'Test set 4 has since been looked at, so it is no longer fresh.'],
      test_set: String(b4.setup.test), date: day(b4.setup.date),
      levels: [{ title: 'Average outfit rating', note: '0 bad · 1 okay · 2 good', scale: 'rating', domain: [0, 2], digits: 2,
        rows: [{ name: 'A · Raw words', sub: 'one collection (Marqo)', mean: M.A.mean, ci95: M.A.ci95, n: M.A.n_prompts }, { name: 'B · Raw words', sub: 'four collections', mean: M.B.mean, ci95: M.B.ci95, n: M.B.n_prompts },
          { name: 'C · AI plan', sub: 'four collections · in use', mean: M.C.mean, ci95: M.C.ci95, n: M.C.n_prompts, inUse: true }] }],
      tables: [{ title: 'Ratings per way', head: ['Way', 'Good', 'Okay', 'Bad'], num: [false, true, true, true], rows: (['A', 'B', 'C'] as const).map((k) => [k, String(M[k].good), String(M[k].okay), String(M[k].bad)]) }],
    }
  })

  // 04 · the AI request plan: blind tests 3, 4 and 5, the earlier labelled check, and the retrieval test on messy rewrites
  add({ id: 'plan', num: '04', short: 'AI request plan?', question: 'Does the AI request plan help?', scale: 'rating',
    sources: [S('blind-test5.summary.json', 'summarise_blind5.py'), S('blind-test4.summary.json', 'summarise_blind.py'), S('blind-test3.summary.json', 'summarise_blind.py'), S('m4.summary.json', 'run_m4.py'), S('m4-heldout-ratings.summary.json'), S('claude-vs-qwen.summary.json', 'compare_plans.py'), ...agreeSource(ag5)] },
  (_missing, opt) => {
    const b5 = need('blind-test5.summary.json')
    const b4 = opt('blind-test4.summary.json'), b3 = opt('blind-test3.summary.json'), m4 = opt('m4.summary.json'), ho = opt('m4-heldout-ratings.summary.json'), cq = opt('claude-vs-qwen.summary.json')
    const F5 = 'runs/blind-test5.summary.json'
    const effects: Effect[] = [
      effect({ key: 'b5-C-B', label: 'Local AI plan minus raw words', sub: 'blind test 5', scale: 'rating', ...pairedIn(b5.C_minus_B), file: F5 }),
      effect({ key: 'b5-D-B', label: 'Claude plan minus raw words', sub: 'blind test 5', scale: 'rating', ...pairedIn(b5.D_minus_B), file: F5 }),
      effect({ key: 'b5-D-C', label: 'Claude plan minus local plan', sub: 'blind test 5', scale: 'rating', ...pairedIn(b5.D_minus_C), file: F5 }),
    ]
    if (b4) effects.push(effect({ key: 'b4-C-B', label: 'AI plan minus raw words', sub: 'blind test 4 · four collections', scale: 'rating', ...pairedIn(b4.paired['C-B']), file: 'runs/blind-test4.summary.json' }))
    if (b3) effects.push(effect({ key: 'b3-plan-raw', label: 'AI plan minus raw words', sub: 'blind test 3 · one collection', scale: 'rating', ...pairedIn(b3.paired['plan-raw']), file: 'runs/blind-test3.summary.json' }))
    if (ho) effects.push(effect({ key: 'heldout', label: 'AI plan minus raw words', sub: 'earlier check · not blind', scale: 'rating', mean: ho.mean_diff_plan_minus_raw_0to2.mean, ci95: ho.mean_diff_plan_minus_raw_0to2.ci95,
      n: ho.n_prompts, better: ho.per_prompt_plan_vs_raw.plan_better, tied: ho.per_prompt_plan_vs_raw.tied, worse: ho.per_prompt_plan_vs_raw.plan_worse, file: 'runs/m4-heldout-ratings.summary.json' }))
    const mr = m4?.results?.valid_rewrites
    if (mr) effects.push(effect({ key: 'm4-understood-raw', label: 'AI-understood rewrite minus messy rewrite', sub: 'search score on labelled searches', scale: 'retrieval',
      mean: mr['embed-understood - embed-raw | ndcg10'].mean, ci95: mr['embed-understood - embed-raw | ndcg10'].ci95, n: m4.setup.n_valid, digits: 3, file: 'runs/m4.summary.json' }))
    const h = effects[0]
    const db = effects.find((e) => e.key === 'b5-D-B') as Effect
    const t3 = effects.find((e) => e.key === 'b3-plan-raw')
    const side = (ci: [number, number] | null) => (!ci ? '' : ci[1] < 0 ? 'The whole range is below zero.' : ci[0] > 0 ? 'The whole range is above zero.' : 'The range includes zero.')
    const m4e = effects.find((e) => e.key === 'm4-understood-raw')
    const levels: Level[] = [{ title: `Average outfit rating, blind test 5`, note: '0 bad · 1 okay · 2 good · this file logs no range per way', scale: 'rating', domain: [0, 2], digits: 2,
      rows: [{ name: 'B · Raw words', mean: b5.mean.B, ci95: null, n: b5.n_prompts }, { name: 'C · Local AI plan', sub: 'Qwen3 4B · in use', mean: b5.mean.C, ci95: null, n: b5.n_prompts, inUse: true },
        { name: 'D · Claude plan', mean: b5.mean.D, ci95: null, n: b5.n_prompts }] }]
    if (b3) levels.push({ title: 'Average outfit rating, blind test 3', note: '0 to 2 · one collection', scale: 'rating', domain: [0, 2], digits: 2, fold: true,
      rows: [{ name: 'Raw words', mean: b3.methods.raw.mean, ci95: b3.methods.raw.ci95, n: b3.methods.raw.n_prompts }, { name: 'AI plan', mean: b3.methods.plan.mean, ci95: b3.methods.plan.ci95, n: b3.methods.plan.n_prompts }] })
    if (mr) levels.push({ title: `Match score, ${int(m4.setup.n_valid)} messy rewrites of labelled searches`, note: '0 to 1 · a different scale from the ratings', scale: 'retrieval', digits: 3, fold: true,
      rows: [{ name: 'Original labelled search', mean: mr['embed-original'].ndcg10.mean, ci95: mr['embed-original'].ndcg10.ci95 }, { name: 'Messy rewrite', mean: mr['embed-raw'].ndcg10.mean, ci95: mr['embed-raw'].ndcg10.ci95 },
        { name: 'AI-understood rewrite', mean: mr['embed-understood'].ndcg10.mean, ci95: mr['embed-understood'].ndcg10.ci95, inUse: true }] })
    return {
      effects,
      answer: [
        lead(h.verdict, 'Yes: the AI plan helped.', 'Not reliably, so far.', 'No: the AI plan made outfits worse.'),
        `On ${b5.n_prompts} fresh requests, raw words rated ${fx(b5.mean.B)} out of 2; the local AI plan ${fx(b5.mean.C)}.`,
        `A paid Claude plan was ${than(db.verdict)} than raw words: ${sg(db.mean)}.`,
        ...(m4e ? [`On a search-score test (0 to 1), understood rewrites were ${than(m4e.verdict)} than messy ones.`] : []),
      ],
      method: [
        'The plan splits a request into pieces before searching.',
        'One person rated each outfit blind: good (2), okay (1) or bad (0).',
        ...(ag5 ? [`In test 5 ${nWord(ag5.raters)} people rated the same options; the differences shown here use the author’s ratings alone.`] : []),
        'Each test compares the same requests one by one (paired).',
        ...(mr ? [`The search-score test rewrote labelled searches messily, using ${m4.setup.understanding_model}.`] : []),
      ],
      measured: [['Requests, test 5', String(b5.n_prompts)], ['Ratings, test 5', String(b5.n_ratings)], ['Rater', ag5 ? `the author, who wrote the requests; test 5 also ${ag5.raters === 2 ? 'a second rater' : `${ag5.raters - 1} more raters`}` : b3 ? String(b3.setup.rater) : 'the project owner'],
        ['Test sets', '3, 4 and 5, plus an earlier labelled check'], ['Date', b3 ? `${day(b3.setup.date)} (tests 3 and 4); test 5 has no date in its file` : 'test 5 has no date in its file']],
      limits: [
        ag5 ? `Test 5: ${raters(ag5)} ${ag4 ? 'Test 4 also has a second rater (see the collections claim); test 3: one rater, the author.' : 'Tests 3 and 4: one rater, the author.'}` : 'One rater, who also wrote the requests.',
        `Test 5, Claude plan minus raw words: ${sg(db.mean)} (${rng(db.ci95 ?? [db.mean, db.mean])}). ${side(db.ci95)}`,
        ...(t3 ? [`Test 3, AI plan minus raw words: ${sg(t3.mean)} (${rng(t3.ci95 ?? [t3.mean, t3.mean])}) on ${t3.n} requests and one collection. ${side(t3.ci95)}`] : []),
        'The plan can drop words that matter, like a colour or a fabric.',
        ...(cq ? [`Claude kept the request’s words ${pc(cq.word_kept_claude, 0)} of the time; the local model ${pc(cq.word_kept_qwen, 0)}.`] : []),
        'The earlier check was not blind: the rater could see the labels.',
      ],
      test_set: `Blind test 5: ${b5.n_prompts} fresh requests`, date: b3 ? day(b3.setup.date) : '',
      levels,
      tables: cq ? [{ title: 'Claude plan against local plan, words kept', head: ['Measure', 'Value'], num: [false, true], rows: [
        ['Share of request words kept, local model', fx(cq.word_kept_qwen, 3)], ['Share of request words kept, Claude', fx(cq.word_kept_claude, 3)],
        ['Claude minus local, 95% range', `${sg(cq.diff_claude_minus_qwen, 3)} (${rng(cq.diff_ci95, 3)})`], ['Requests', String(cq.n)], ['Cost of the Claude calls, US dollars', fx(cq.claude_cost_usd, 2)]] }] : [],
    }
  })

  // 05 · the clothes map (knowledge graph): held-out product types
  const MIN_USAGE = 20
  add({ id: 'graph', num: '05', short: 'Clothes map?', question: 'Does the clothes map help?', scale: 'retrieval', sources: [S('graph-holdout.summary.json', 'eval_graph.py'), S('blind-test3.summary.json', 'summarise_blind.py')] }, (_m, opt) => {
    const g = need('graph-holdout.summary.json')
    const b3 = opt('blind-test3.summary.json')
    const F = 'runs/graph-holdout.summary.json'
    const usage = Object.entries(g.by_usage as Record<string, { n_test: number; graph: number; baseline: number; diff_ci95: [number, number] }>).filter(([, v]) => v.n_test >= MIN_USAGE)
    const effects = [
      effect({ key: 'graph-overall', label: 'With the clothes map minus without', sub: 'right type in the top 3', scale: 'retrieval', mean: g.overall.difference, ci95: g.overall.ci95, n: g.n_test, digits: 3, file: F }),
      ...usage.map(([u, v]) => effect({ key: `graph-${u}`, label: `${u} occasions`, sub: 'with minus without', scale: 'retrieval', mean: v.graph - v.baseline, ci95: v.diff_ci95, n: v.n_test, digits: 3, forest: false, file: F })),
    ]
    const h = effects[0]
    const changed = b3?.methods?.plan_graph?.n_prompts, fresh = b3?.methods?.raw?.n_prompts
    return {
      effects,
      answer: [
        lead(h.verdict, 'Yes, under the hood.', 'Not clearly.', 'No: the map made guesses worse.'),
        `With the map, the right product type was in the top 3 for ${pc(g.overall.graph_hit_at_3)} of hidden products.`,
        `Without it: ${pc(g.overall.baseline_hit_at_3)}.`,
        ...(changed != null && fresh != null ? [`But it changed the plan for only ${changed} of ${fresh} fresh requests.`] : []),
      ],
      method: [
        `${int(g.n_train)} products built the map; ${int(g.n_test)} were hidden to test it.`,
        'For each hidden product, the map guessed its type from its occasion.',
        'We count how often the right type is among the first 3 guesses.',
      ],
      measured: [['Hidden products', int(g.n_test)], ['Products used to build it', int(g.n_train)], ['Rater', 'product labels in the dataset'], ['Map size', `${g.graph_nodes} ideas, ${g.graph_edges} links`], ['Date', 'not in the file']],
      limits: ['The map is built from label counts; no model reads text.', `Occasions with fewer than ${MIN_USAGE} test products are left out.`, 'A better guess of type is not the same as a better outfit.'],
      test_set: `${int(g.n_test)} hidden products`, date: '',
      levels: [{ title: 'Right type in the top 3', note: 'share of hidden products · 0 to 1', scale: 'rate', domain: [0, 1], digits: 3,
        rows: [{ name: 'Without the map', mean: g.overall.baseline_hit_at_3, ci95: null, n: g.n_test }, { name: 'With the map', sub: 'in use', mean: g.overall.graph_hit_at_3, ci95: null, n: g.n_test, inUse: true }] }],
      tables: [{ title: 'By occasion', head: ['Occasion', 'Hidden products', 'With map', 'Without', 'Difference (95% range)'], num: [false, true, true, true, true],
        rows: usage.map(([u, v]) => [u, int(v.n_test), fx(v.graph, 3), fx(v.baseline, 3), `${sg(v.graph - v.baseline, 3)} (${rng(v.diff_ci95, 3)})`]) }],
    }
  })

  // 06 · colour harmony: blind outfit ratings and the rule scores
  add({ id: 'colour', num: '06', short: 'Matching colours?', question: 'Do matching colours make better outfits?', scale: 'rating',
    sources: [S('outfit-ratings.summary.json', 'summarise_blind.py'), S('outfit-objective.summary.json', 'make_outfit_sheet.py')] }, (_m, opt) => {
    const o = need('outfit-ratings.summary.json')
    const ob = opt('outfit-objective.summary.json')
    const F = 'runs/outfit-ratings.summary.json'
    const effects = [
      effect({ key: 'colour-coherent', label: 'Chosen for harmony minus best match', sub: 'blind outfit ratings', scale: 'rating', ...pairedIn(o.paired['coherent-baseline']), file: F }),
      effect({ key: 'colour-clash', label: 'Made to clash minus best match', sub: 'a check that harmony shows', scale: 'rating', ...pairedIn(o.paired['clash-baseline']), file: F }),
    ]
    const h = effects[0], M = o.methods
    return {
      effects,
      answer: [
        lead(h.verdict, 'Yes: matching colours rated higher.', 'No clear change.', 'No: matching colours rated lower.'),
        `Outfits chosen for matching colours rated ${fx(M.coherent.mean)} out of 2; best matches rated ${fx(M.baseline.mean)}.`,
        `Even outfits made to clash rated ${fx(M.clash.mean)}.`,
        ...(ob ? [`The two ways picked the same outfit for ${ob.coherent_equals_baseline} of ${ob.n_prompts} requests.`] : []),
      ],
      method: [`${M.baseline.n_prompts} multi-piece requests got three outfit boards each.`, 'One person rated each board blind: good (2), okay (1) or bad (0).', 'The colour rules were fixed before any rating.'],
      measured: [['Requests', String(M.baseline.n_prompts)], ['Boards rated', String(o.setup.n_options_rated)], ['Rater', String(o.setup.rater)], ['Test set', String(o.setup.test)], ['Date', day(o.setup.date)]],
      limits: ['One rater, who also wrote the requests.', 'Most picks were already neutral colours.', 'Strong contrasts are normal in Indian festive wear, so Western rules may not fit.'],
      test_set: String(o.setup.test), date: day(o.setup.date),
      levels: [{ title: 'Average outfit rating', note: '0 bad · 1 okay · 2 good', scale: 'rating', domain: [0, 2], digits: 2,
        rows: [{ name: 'Best match per piece', sub: 'baseline', mean: M.baseline.mean, ci95: M.baseline.ci95, n: M.baseline.n_prompts },
          { name: 'Chosen for harmony', sub: 'in use', mean: M.coherent.mean, ci95: M.coherent.ci95, n: M.coherent.n_prompts, inUse: true },
          { name: 'Made to clash', mean: M.clash.mean, ci95: M.clash.ci95, n: M.clash.n_prompts }] }],
      tables: ob ? [{ title: 'Colour rule scores (no person involved)', head: ['Way', 'Harmony score', 'Relevance lost'], num: [false, true, true],
        rows: (['baseline', 'coherent', 'clash'] as const).map((k) => [{ baseline: 'Best match', coherent: 'Chosen for harmony', clash: 'Made to clash' }[k], fx(ob.harmony[k], 3), fx(ob.relevance_loss[k], 3)]) }] : [],
    }
  })

  // 07 · likes (simulated shopper)
  add({ id: 'likes', num: '07', short: 'Your likes?', question: 'Do your likes improve the results?', scale: 'retrieval', sources: [S('feedback-sim.summary.json', 'eval_feedback.py')] }, () => {
    const fb = need('feedback-sim.summary.json')
    const L = fb.metrics.likes_only
    const effects = [effect({ key: 'likes', label: 'With likes minus without', sub: 'simulated shopper', scale: 'retrieval', ...pairedIn(L.paired_difference), n: L.n_test_queries, digits: 3, file: 'runs/feedback-sim.summary.json' })]
    const h = effects[0]
    return {
      effects,
      answer: [
        lead(h.verdict, 'A little, in a simulation.', 'Not clearly, in a simulation.', 'No: likes made results worse, in a simulation.'),
        `Likes moved the match score (0 to 1) from ${fx(L.ndcg10_residual_without_feedback.mean, 3)} to ${fx(L.ndcg10_residual_with_feedback.mean, 3)}.`,
        `Results got better for ${h.better} searches and worse for ${h.worse}.`,
      ],
      method: [
        `A computer played the shopper and liked the right products among the first ${fb.setup.shown_before_feedback} shown.`,
        'Results after those were scored with and without the likes.',
        `The weight was tuned on ${fb.setup.tune_queries} other searches first.`,
      ],
      measured: [['Searches', String(L.n_test_queries)], ['With at least one like', String(L.queries_with_at_least_one_like)], ['Rater', 'simulated shopper using dataset labels'], ['Test set', 'held-out half of the bigger test'], ['Date', day(fb.setup.date)]],
      limits: ['No real person took part.', 'The dataset’s labels are incomplete.', 'Only one round of likes was tested.'],
      test_set: `${L.n_test_queries} held-out searches`, date: day(fb.setup.date),
      levels: [{ title: 'Match score after the first results', note: '0 to 1 · higher is better', scale: 'retrieval', digits: 3,
        rows: [{ name: 'Without likes', mean: L.ndcg10_residual_without_feedback.mean, ci95: L.ndcg10_residual_without_feedback.ci95, n: L.n_test_queries },
          { name: 'With likes', sub: 'in use', mean: L.ndcg10_residual_with_feedback.mean, ci95: L.ndcg10_residual_with_feedback.ci95, n: L.n_test_queries, inUse: true }] }],
      tables: [],
    }
  })

  // 08 · the AI judge: agreement with the person (tests 4 and 5), and what it would have concluded on test 5
  const SUBSTANTIAL = 0.6   // the usual line for "substantial" agreement on the weighted-kappa scale (Landis and Koch)
  add({ id: 'judge', num: '08', short: 'AI judge?', question: 'Can an AI judge replace the human rater?', scale: 'rate',
    sources: [S('judge-test5.summary.json', 'analyze_judge5.py'), S('judge-validate.summary.json', 'analyze_judge.py'), S('claude-vs-qwen-judged.summary.json', 'compare_judged.py'), S('blind-test5.summary.json', 'summarise_blind5.py')],
    words: { helped: 'Yes: it agrees well enough', 'no clear effect': 'Unclear', hurt: 'Not yet: it agrees too little' } }, (_m, opt) => {
    const j5 = need('judge-test5.summary.json')
    const jv = opt('judge-validate.summary.json'), cj = opt('claude-vs-qwen-judged.summary.json'), b5 = opt('blind-test5.summary.json')
    const ref = { ref: SUBSTANTIAL, refLabel: 'substantial agreement' }
    const effects: Effect[] = [effect({ key: 'kappa-5', label: 'Agreement score, judge with person', sub: 'test 5 · fresh', scale: 'rate', mean: j5.weighted_kappa, ci95: j5.kappa_ci95, n: j5.n_options, ...ref, forest: false, file: 'runs/judge-test5.summary.json' })]
    if (jv) effects.push(effect({ key: 'kappa-4', label: 'Agreement score, judge with person', sub: 'test 4', scale: 'rate', mean: jv.weighted_kappa, ci95: jv.kappa_ci95, n: jv.n_usable, ...ref, forest: false, file: 'runs/judge-validate.summary.json' }))
    const mc = j5.method_comparisons as Record<string, { n: number; human_mean_diff: number; judge_mean_diff: number; judge_ci95: [number, number] }>
    const human = b5 ? effect({ key: 'person-D-B', label: 'Person: Claude plan minus raw words', sub: 'test 5', scale: 'rating', ...pairedIn(b5.D_minus_B), forest: false, file: 'runs/blind-test5.summary.json' }) : null
    const judge = effect({ key: 'judge-D-B', label: 'AI judge: Claude plan minus raw words', sub: 'test 5', scale: 'rating', mean: mc['D-B'].judge_mean_diff, ci95: mc['D-B'].judge_ci95, n: mc['D-B'].n, forest: false, file: 'runs/judge-test5.summary.json' })
    if (human) effects.push(human)
    effects.push(judge)
    if (b5) effects.push(effect({ key: 'person-C-B', label: 'Person: local plan minus raw words', sub: 'test 5', scale: 'rating', ...pairedIn(b5.C_minus_B), forest: false, file: 'runs/blind-test5.summary.json' }))
    effects.push(effect({ key: 'judge-C-B', label: 'AI judge: local plan minus raw words', sub: 'test 5', scale: 'rating', mean: mc['C-B'].judge_mean_diff, ci95: mc['C-B'].judge_ci95, n: mc['C-B'].n, forest: false, file: 'runs/judge-test5.summary.json' }))
    if (cj) effects.push(effect({ key: 'judge-only-D-C', label: 'AI judge only: Claude plan minus local plan', sub: 'test 4 · no person rated these', scale: 'rating', mean: cj.diff_claude_minus_qwen, ci95: cj.diff_ci95, n: cj.n, forest: false, file: 'runs/claude-vs-qwen-judged.summary.json' }))
    const h = effects[0]
    const conf = j5.confusion_human_rows_judge_cols as Record<'good' | 'okay' | 'bad', Record<'good' | 'okay' | 'bad', number>>
    return {
      effects,
      answer: [
        lead(h.verdict, 'Yes: the AI judge agrees well with the person.', 'Not clearly.', 'Not yet.'),
        `On fresh test 5, the judge gave the same rating on ${pc(j5.agreement, 0)} of ${j5.n_options} outfits.`,
        `Its agreement score was ${fx(j5.weighted_kappa)}, where 0 is chance and 1 is perfect.`,
        ...(human ? [`For the Claude plan, the person saw ${phrase(human.verdict)}; the judge saw ${phrase(judge.verdict)}.`] : []),
      ],
      method: [
        'An AI model (the judge) rated the same outfit options as the person, blind.',
        'The agreement score is weighted kappa: it removes chance and counts near-misses less.',
        `We call it good enough when the whole 95% range is above ${SUBSTANTIAL}, the usual line for “substantial”.`,
        'Ranges come from resampling the options.',
      ],
      measured: [['Options, test 5', String(j5.n_options)], ...(jv ? [['Options, test 4', String(jv.n_usable)] as [string, string]] : []), ['Rater compared', 'the project owner'], ['Test sets', '4 and 5'], ['Date', 'not in the files']],
      limits: [
        ...(jv ? [`The judge was stricter than the person on ${pc(jv.judge_stricter_share, 0)} of test 4 options.`] : []),
        'The human side is one person, with their own noise.',
        ...(cj ? [`On test 4 the judge alone preferred Claude plans by ${sg(cj.diff_claude_minus_qwen)}; no person checked that.`] : []),
      ],
      test_set: `Test 5: ${j5.n_options} outfit options`, date: '',
      levels: [{ title: 'Same rating as the person', note: 'share of options · 0 to 1', scale: 'rate', domain: [0, 1], digits: 3,
        rows: [...(jv ? [{ name: 'Test 4', mean: jv.agreement, ci95: jv.agreement_ci95, n: jv.n_usable }] : []), { name: 'Test 5', sub: 'fresh', mean: j5.agreement, ci95: j5.agreement_ci95, n: j5.n_options }] }],
      tables: [
        { title: 'Test 5: person’s rating (rows) against the judge’s (columns)', head: ['Person', 'Judge good', 'Judge okay', 'Judge bad'], num: [false, true, true, true],
          rows: (['good', 'okay', 'bad'] as const).map((r) => [r, String(conf[r].good), String(conf[r].okay), String(conf[r].bad)]) },
        { title: 'Average rating (0 to 2)', head: ['Test', 'Person', 'Judge'], num: [false, true, true],
          rows: [...(jv ? [['Test 4', fx(jv.human_mean, 3), fx(jv.judge_mean, 3)]] : []), ['Test 5', fx(j5.human_mean, 3), fx(j5.judge_mean, 3)]] },
      ],
    }
  })

  // 09 · rule checks on the candidates: before and after, per request (counts, so the verdict is a sign test over requests)
  add({ id: 'checks', num: '09', short: 'Rule checks?', question: 'Do the rule checks fix wrong items?', scale: 'count', sources: [S('checks-eval.summary.json', 'eval_checks.py'), S('checks-eval.jsonl', 'eval_checks.py')] }, (_m, opt) => {
    const c = need('checks-eval.summary.json')
    const prompts = (c.prompts ?? c.setup?.prompts) as number
    const rows = opt('checks-eval.jsonl', needl) as { before: Record<string, number>; after: Record<string, number> }[] | null
    const BREAKS = ['wrong_slot', 'child_for_adult', 'mixed_gender_outfit', 'colour_missing'] as const
    const NAMES: Record<(typeof BREAKS)[number], [string, string]> = { wrong_slot: ['Wrong slot', 'pieces'], child_for_adult: ['Child item for an adult', 'pieces'],
      mixed_gender_outfit: ['Mixed-gender outfit', 'requests'], colour_missing: ['Named colour missing', 'pieces with a named colour'] }
    const total = (o: Record<string, number>) => BREAKS.reduce((s, k) => s + (o[k] ?? 0), 0)
    let better: number | undefined, worse: number | undefined, tied: number | undefined, mean = (total(c.after) - total(c.before)) / prompts
    if (rows) {
      const d = rows.map((r) => total(r.after) - total(r.before))
      better = d.filter((x) => x < 0).length; worse = d.filter((x) => x > 0).length; tied = d.filter((x) => x === 0).length
      mean = d.reduce((s, x) => s + x, 0) / d.length
    }
    const of = (k: (typeof BREAKS)[number]) => (k === 'colour_missing' ? c.before.colour_named : k === 'mixed_gender_outfit' ? prompts : c.pieces) as number
    const h = effect({ key: 'checks', label: 'Rule breaks per request, after minus before', scale: 'count', mean, ci95: null, n: rows ? rows.length : prompts, better, tied, worse,
      higherIsBetter: false, ref: rows ? 0 : null, digits: 2, forest: false, file: rows ? 'runs/checks-eval.jsonl' : 'runs/checks-eval.summary.json' })
    return {
      effects: [h],
      answer: [
        lead(h.verdict, 'Yes, for most rule breaks.', 'Not clearly.', 'No: the checks added rule breaks.', 'The per-request file is missing, so there is no verdict.'),
        ...(better != null ? [`Rule breaks fell on ${better} of ${h.n} requests and rose on ${worse ? worse : 'none'}.`] : []),
        `Pieces in the wrong slot fell from ${c.before.wrong_slot} to ${c.after.wrong_slot} of ${c.pieces}.`,
        `A named colour went missing ${c.before.colour_missing} times before and ${c.after.colour_missing} after.`,
      ],
      method: [
        `${prompts} requests were searched with and without the rule checks.`,
        'We count rule breaks in the first pick for every piece.',
        `The request was read by ${c.setup.understand}.`,
        'This is a count of breaks, not a rating of looks.',
      ],
      measured: [['Requests', String(prompts)], ['Pieces', String(c.pieces)], ['Requests changed', String(c.requests_changed)], ['Rater', 'fixed rules, no person'], ['Date', day(c.setup.date)]],
      limits: ['Only the first pick of each piece is checked.', 'Fewer rule breaks does not prove a better-looking outfit.', 'The rules were written by the same person who wrote the checks.'],
      test_set: `${prompts} requests from test sets 4 and 5`, date: day(c.setup.date),
      levels: [{ title: 'Rule breaks, before and after', note: 'counts · fewer is better', scale: 'count', digits: 0, bars: true,
        rows: BREAKS.flatMap((k) => [
          { name: `${NAMES[k][0]}, before`, mean: c.before[k], ci95: null, value: `${c.before[k]} of ${of(k)}` },
          { name: `${NAMES[k][0]}, after`, sub: 'with the checks · in use', mean: c.after[k], ci95: null, value: `${c.after[k]} of ${of(k)}`, inUse: true }]) }],
      tables: [{ title: 'Every rule', head: ['Rule', 'Counted over', 'Before', 'After'], num: [false, false, true, true],
        rows: BREAKS.map((k) => [NAMES[k][0], `${of(k)} ${NAMES[k][1]}`, String(c.before[k]), String(c.after[k])]) }],
    }
  })

  // 10 · the safety guard: hand-written unsafe and safe prompts, and every real shopper request
  add({ id: 'guard', num: '10', short: 'Safety guard?', question: 'Does the safety guard refuse the right things?', scale: 'rate', sources: [S('guard.summary.json', 'eval_guard.py'), S('guard.jsonl', 'eval_guard.py')],
    words: { helped: 'Yes, on these tests', 'no clear effect': 'Unclear', hurt: 'No' } }, () => {
    const g = need('guard.summary.json')
    const F = 'runs/guard.summary.json'
    const hf = g.hand_full, rf = g.real_full, hr = g.hand_rules_only
    const caught = hf.n_unsafe - hf.missed
    const effects = [
      effect({ key: 'guard-caught', label: 'Unsafe test prompts stopped', sub: 'without a guard, none are', scale: 'rate', mean: caught / hf.n_unsafe, ci95: wilson(caught, hf.n_unsafe), n: hf.n_unsafe, ref: 0, refLabel: 'no guard', forest: false, digits: 3, file: F }),
      effect({ key: 'guard-false-hand', label: 'Safe test prompts wrongly refused', scale: 'rate', mean: hf.falsely_refused / hf.n_safe, ci95: wilson(hf.falsely_refused, hf.n_safe), n: hf.n_safe, ref: null, higherIsBetter: false, forest: false, digits: 3, file: F }),
      effect({ key: 'guard-false-real', label: 'Real requests wrongly refused', scale: 'rate', mean: rf.falsely_refused / rf.n_safe, ci95: wilson(rf.falsely_refused, rf.n_safe), n: rf.n_safe, ref: null, higherIsBetter: false, forest: false, digits: 3, file: F }),
    ]
    const h = effects[0]
    return {
      effects,
      answer: [
        lead(h.verdict, 'Yes, on these tests.', 'Not clearly.', 'No.'),
        `It stopped ${caught} of ${hf.n_unsafe} unsafe test prompts.`,
        `It wrongly refused ${hf.falsely_refused} of ${hf.n_safe} safe test prompts, and ${rf.falsely_refused} of ${rf.n_safe} real requests.`,
        `A model review took ${fx(g.model_review_seconds_mean)} seconds on average.`,
      ],
      method: [
        'Fixed rules check each request first; unclear ones go to a small local model.',
        `${hf.n_unsafe} unsafe and ${hf.n_safe} safe test prompts were written by hand.`,
        `Every real shopper request in the logs (${g.n_real_prompts}) was also run.`,
        'Ranges are Wilson 95% ranges for a share.',
      ],
      measured: [['Unsafe test prompts', String(hf.n_unsafe)], ['Safe test prompts', String(hf.n_safe)], ['Real requests', String(g.n_real_prompts)], ['Model reviews', String(g.n_model_reviews)], ['Date', 'not in the file']],
      limits: [
        'The test prompts were written by the person who wrote the rules.',
        ...(rf.n_unsafe === 0 ? ['No real request was unsafe, so real misses are untested.'] : []),
        'Without a guard nothing is stopped, so the “helped” bar is low.',
      ],
      test_set: `${hf.n_unsafe + hf.n_safe} hand-written prompts and ${g.n_real_prompts} real requests`, date: '',
      levels: [],
      tables: [{ title: 'Each setup', head: ['Setup', 'Unsafe missed', 'Safe wrongly refused', 'Sent to model review'], num: [false, true, true, true],
        rows: ([['Rules only, test prompts', hr], ['Rules and model, test prompts', hf], ['Rules only, real requests', g.real_rules_only], ['Rules and model, real requests', rf]] as const)
          .map(([n, r]) => [n, `${r.missed} of ${r.n_unsafe}`, `${r.falsely_refused} of ${r.n_safe}`, String(r.sent_to_review)]) }],
    }
  })

  // 11 · catalogue quality: near-copies across the four collections, and whether removing them changes the model scores
  add({ id: 'data', num: '11', short: 'Clean catalogue?', question: 'Is the catalogue clean enough to trust the scores?', scale: 'count',
    sources: [S('data-quality-4.summary.json', 'data_quality_4.py'), S('duplicates.summary.json', 'analyze_duplicates.py')],
    words: { helped: 'Yes: the scores hold', 'no clear effect': 'Unclear: the lead may not hold', hurt: 'No: the lead reverses' } }, (_m, opt) => {
    const dq = need('data-quality-4.summary.json'), du = need('duplicates.summary.json')
    const sc = opt('scale-marqo-fashionsiglip.summary.json')
    const F = 'runs/duplicates.summary.json'
    const pr = (k: string, which: 'std' | 'ded') => { const [mean, lo, hi] = du.rescoring_pairs[k][which] as [number, number, number]; return { mean, ci95: [lo, hi] as [number, number] } }
    const n = sc?.setup?.n_queries ?? null   // analyze_duplicates.py re-scores the bigger test (the scale-marqo index)
    const effects = [
      effect({ key: 'dup-marqo-siglip-ded', label: 'Fashion model minus general model', sub: 'near-copies merged', scale: 'retrieval', ...pr('marqo-fashionsiglip - siglip-base', 'ded'), n, digits: 3, forest: false, file: F }),
      effect({ key: 'dup-marqo-siglip-std', label: 'Fashion model minus general model', sub: 'as logged', scale: 'retrieval', ...pr('marqo-fashionsiglip - siglip-base', 'std'), n, digits: 3, forest: false, file: F }),
      effect({ key: 'dup-marqo-bm25-ded', label: 'Fashion model minus keyword search', sub: 'near-copies merged', scale: 'retrieval', ...pr('marqo-fashionsiglip - bm25', 'ded'), n, digits: 3, forest: false, file: F }),
    ]
    const h = effects[0]
    const share = dq.products_in_clusters / dq.total
    const t97 = du.by_tau['0.97']
    const lg = du.label_consistency
    const SRC: Record<string, string> = { marqo: 'Marqo (general)', kaggle: 'Kaggle fashion', myntra2: 'Myntra photos', mens3: 'Men’s set' }
    return {
      effects,
      answer: [
        lead(h.verdict, 'Clean enough to trust the scores.', 'Near-copies may change the result.', 'No: near-copies change the result.'),
        `${pc(share)} of the ${int(dq.total)} products across four collections are near-copies.`,
        `Merging near-copies keeps the fashion model’s lead at ${sg(h.mean, 3)}.`,
        `But ${lg.groups_disagreeing_on_relevance} of ${lg.groups_inside_a_query} copy groups inside one search carry mixed labels.`,
      ],
      method: [
        'Two products count as near-copies when their pictures are almost the same.',
        `“Almost the same” means a similarity of at least ${dq.tau_within} within a collection, ${dq.tau_cross} across.`,
        'The cut-offs were chosen by looking at pairs by eye.',
        'The searches were then scored again with each copy group counted once.',
      ],
      measured: [['Products', int(dq.total)], ['Unique after merging', int(dq.unique_after_merge)], ['Copy groups', int(dq.clusters_with_copies)], ['Rater', 'picture similarity, no person'], ['Date', 'not in the files']],
      limits: ['Picture similarity misses copies that were photographed differently.', 'The cut-offs were chosen by eye.', 'Label disagreements inside a search cannot be fixed by merging.'],
      test_set: `${int(dq.total)} products in four collections`, date: '',
      levels: [{ title: 'Shares of products and labels', note: '0 to 1 · Wilson 95% ranges · lower is cleaner', scale: 'rate', digits: 3,
        rows: [
          { name: 'Near-copies, four collections', mean: share, ci95: wilson(dq.products_in_clusters, dq.total), n: dq.total, value: `${int(dq.products_in_clusters)} of ${int(dq.total)}` },
          { name: 'Near-copies, Marqo collection', sub: `similarity ≥ ${dq.tau_within}`, mean: t97.share_of_products, ci95: wilson(t97.products_in_such_clusters, du.n_products), n: du.n_products, value: `${int(t97.products_in_such_clusters)} of ${int(du.n_products)}` },
          { name: 'Copy groups disagreeing on labels', sub: 'inside one search', mean: lg.groups_disagreeing_on_relevance / lg.groups_inside_a_query, ci95: wilson(lg.groups_disagreeing_on_relevance, lg.groups_inside_a_query), n: lg.groups_inside_a_query, value: `${lg.groups_disagreeing_on_relevance} of ${lg.groups_inside_a_query}` }] }],
      tables: [
        { title: 'Products per collection', head: ['Collection', 'Products'], num: [false, true], rows: [...Object.entries(dq.sizes as Record<string, number>).map(([k, v]) => [SRC[k] ?? k, int(v)]), ['All four', int(dq.total)], ['Unique after merging', int(dq.unique_after_merge)]] },
        { title: 'Copies across collections (pairs at or above the cut-off)', head: ['Pair', 'Pairs'], num: [false, true], rows: Object.entries(dq.cross_pairs_ge_tau as Record<string, number>).map(([k, v]) => [k.split('-').map((x) => SRC[x] ?? x).join(' and '), String(v)]) },
        { title: 'Match score with near-copies merged', head: ['Method', 'As logged', 'Merged'], num: [false, true, true],
          rows: Object.entries(du.rescoring as Record<string, { std: number; ded: number }>).map(([k, v]) => [k, fx(v.std, 4), fx(v.ded, 4)]) },
      ],
    }
  })

  return { claims: out, warnings }
}

/** Every number on the Evidence page is read here, from the logged run files, each time the app starts or builds. */
function evidence() {
  const c = claims()
  return { ...legacy(), claims: c.claims, warnings: c.warnings }
}

/** The handful of logged values used outside the Evidence, System and Docs pages: same source, same numbers, a much smaller first download. */
function evidenceFront() {
  const e = legacy()
  return {
    blind5: e.blind5, feedback: e.feedback, claudeSpend: e.claudeSpend,
    aws: { loadtest: e.aws.loadtest },
    drawing: { text: e.drawing.text, textGen: e.drawing.textGen, genFashion: e.drawing.genFashion, genResnet: e.drawing.genResnet },
    findings: { blind4: e.findings.blind4 }, agreement: e.agreement,
  }
}

function genkartLocal(): Plugin {
  const id = 'virtual:evidence'
  const front = 'virtual:evidence-front'      // the few values the first download needs (Search page, cost and compare cards), so the rest loads with Evidence
  return {
    name: 'genkart-local',
    // read every run file once at the start, print what could not be read, and stop the build only when EVIDENCE_STRICT=1 (CI)
    buildStart() {
      const { warnings } = evidence()
      for (const w of warnings) this.warn(`evidence: ${w}`)
      if (warnings.length && process.env.EVIDENCE_STRICT === '1') this.error(`evidence: ${warnings.length} warning(s) and EVIDENCE_STRICT=1`)
    },
    resolveId: (source) => (source === id || source === front ? '\0' + source : null),
    load: (source) => (source === '\0' + id ? `export default ${JSON.stringify(evidence())}`
      : source === '\0' + front ? `export default ${JSON.stringify(evidenceFront())}` : null),
  }
}


// Content-Security-Policy for the built page (GitHub Pages cannot send headers, so it is a meta tag). Build only: the dev server injects an
// inline script. connect-src: this site, the hosted Lab (VITE_PHOTO_BASE: photos and waking it) and models on the visitor's own device
// (localhost). Keys go to the server in POST bodies, never to a provider from the page.
function cspMeta(): Plugin {
  let photo = ''
  try { photo = process.env.VITE_PHOTO_BASE ? new URL(process.env.VITE_PHOTO_BASE).origin : '' } catch { photo = '' }
  const csp = ["default-src 'self'", "script-src 'self'", "style-src 'self' 'unsafe-inline'", `img-src 'self' data: ${photo}`.trim(),
    "font-src 'self' data:", `connect-src 'self' ${photo} http://localhost:* http://127.0.0.1:*`.replace(/\s+/g, ' '),
    "object-src 'none'", "base-uri 'self'", "form-action 'self'"].join('; ')
  return { name: 'csp-meta', apply: 'build', transformIndexHtml: () => [{ tag: 'meta', attrs: { 'http-equiv': 'Content-Security-Policy', content: csp }, injectTo: 'head-prepend' }] }
}

export default defineConfig({
  base: process.env.VITE_BASE ?? '/',   // GitHub Pages serves a project at /<repo-name>/: the workflow sets VITE_BASE
  plugins: [react(), genkartLocal(), cspMeta()],
  server: { proxy: { '/api': process.env.GENKART_API ?? 'http://localhost:7860' } },   // GENKART_API overrides the target; space/start.sh runs on :7860 by default
})
