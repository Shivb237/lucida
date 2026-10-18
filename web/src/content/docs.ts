// The project's documentation, as data, in plain words. Every number is computed from the logged runs (virtual:evidence) or the recorded runs, never typed in.
// Rule: say what it means first; each item is at most three lines on a normal screen; a measured claim names the file in runs/ it came from.
import evidence from 'virtual:evidence'
import { RECORDED } from '../recorded'
import type { StageId } from '../trace'

type Ev = typeof evidence
export type Fact = { text: string; source: string }
export type StepDoc = {
  id: StageId
  title: string
  what: string
  why: string
  measured: Fact[]
  fails: string[]
  helped: 'helped' | 'no clear effect' | 'did not help' | 'safety' | 'plumbing'
  helpedWhy: string
  code: string[]
}
export type Decision = { date: string; decision: string; why: string; source?: string }

const n2 = (x: number) => x.toFixed(2)
const n3 = (x: number) => x.toFixed(3)
const sg = (x: number, d = 2) => `${x >= 0 ? '+' : '−'}${Math.abs(x).toFixed(d)}`
const pc = (x: number, d = 0) => `${(x * 100).toFixed(d)}%`
const med = (xs: number[]) => { const s = [...xs].sort((a, b) => a - b); return s.length ? s[Math.floor(s.length / 2)] : 0 }
const sourceFile = (f: string) => `runs/${f}`

export function recordedUnderstandMedian(): number {
  return med(RECORDED.runs.flatMap((r) => r.events.filter((e) => e.kind === 'step' && e.stage === 'understand' && e.status === 'done').map((e) => (e.kind === 'step' ? e.seconds ?? 0 : 0))))
}

export function buildSteps(ev: Ev = evidence): StepDoc[] {
  const g = ev.guard, b3 = ev.findings.blind3, b4 = ev.findings.blind4, b5 = ev.blind5, gr = ev.findings.graph, oc = ev.findings.outfit, u = ev.understanding
  const sc = ev.scale, dr = ev.drawing, cq = ev.claudeVsQwen, ck = ev.checksEval
  return [
    {
      id: 'request', title: 'Your request',
      what: 'A safety check reads your sentence first. It blanks phone numbers and similar details, applies fixed rules, and asks the local AI model about unclear wording. A refused request stops here.',
      why: 'A public search box takes anything. Refusing early costs nothing; refusing late wastes a search.',
      measured: g ? [
        { text: `Fixed rules missed ${g.hand_rules_only.missed} of ${g.hand_rules_only.n_unsafe} unsafe test requests (the author wrote them, so this is optimistic). With the AI review, ${g.hand_full.falsely_refused} of ${g.hand_full.n_safe} safe ones were wrongly refused.`, source: sourceFile('guard.summary.json') },
        { text: `Of ${g.n_real_prompts} real requests, ${g.real_full.falsely_refused} were refused. The AI review took ${n2(g.model_review_seconds_mean)} s on average.`, source: sourceFile('guard.summary.json') },
      ] : [],
      fails: ['Wording the rules do not know goes to the AI model. If it is off, unclear requests pass and are marked "not reviewed".', 'The unsafe test cases were written by the author, so "0 missed" is optimistic.'],
      helped: 'safety', helpedWhy: 'It is a gate, not a search improvement, so it has no score.',
      code: ['src/genkart/guard.py', 'src/genkart/server.py'],
    },
    {
      id: 'understand', title: 'Read your sentence',
      what: 'A small AI model on your own computer turns the sentence into a plan: the pieces to search, who it is for, the occasion, the season, the budget, what you already own. Plain code then checks the plan against your words.',
      why: 'Real requests are whole outfits for events. One search for a whole sentence finds one kind of product. A plan lets each piece be searched on its own.',
      measured: [
        ...(u ? [{ text: `On ${u.n} messy rewrites of labelled searches, the match score (0 to 1) was ${n3(u.original)} for the clean original, ${n3(u.raw)} for the messy text as it was, and ${n3(u.understood)} with the plan. So the plan wins back about ${pc((u.understood - u.raw) / (u.original - u.raw))} of what messy wording loses.`, source: sourceFile('m4.summary.json') }] : []),
        ...(b5 ? [{ text: `On ${b5.n_prompts} fresh requests, one person rated results 0 to 2 without knowing which method made them: plain sentence ${n2(b5.mean.B)}, local plan ${n2(b5.mean.C)}. Plan minus plain: ${sg(b5.C_minus_B.mean)} (range ${sg(b5.C_minus_B.ci95[0])} to ${sg(b5.C_minus_B.ci95[1])}). It did not help.`, source: sourceFile('blind-test5.summary.json') }] : []),
        ...(cq && b5 ? [{ text: `A paid Claude plan scored the same as the local one (${sg(b5.D_minus_C.mean)}) and cost $${cq.claude_cost_usd.toFixed(2)} in calls. The local model stays.`, source: sourceFile('blind-test5.summary.json') }] : []),
      ],
      fails: ['It can drop colour, fabric or theme words, and can slip on a word ("brocade" became "broad").', `It is the slowest step: about ${n2(recordedUnderstandMedian())} s in the recorded runs, most of the whole request.`],
      helped: 'no clear effect', helpedWhy: 'Better than messy text, but not better than searching the sentence as typed (possibly worse: the range only just reaches zero). Kept because it is the only way to build an outfit from several pieces. We did not measure whether that is worth the wait.',
      code: ['src/genkart/understand.py'],
    },
    {
      id: 'expand', title: 'Add missing ideas',
      what: 'A small map of how clothes and occasions go together, counted from Kaggle product labels, checks each piece. It swaps a generic piece for what that occasion usually needs, and adds a missing one, such as shoes.',
      why: 'An AI model can invent a piece or miss one. The map is simple enough to read and question: a short word list plus counts from labels.',
      measured: gr ? [
        { text: `We hid ${gr.n_test.toLocaleString('en')} products from the map. Its top 3 guesses contained the right type ${pc(gr.overall.graph_hit_at_3, 1)} of the time, against ${pc(gr.overall.baseline_hit_at_3, 1)} without the occasion (${sg(gr.overall.difference * 100, 1)} points).`, source: sourceFile('graph-holdout.summary.json') },
        { text: `It gains most for formal wear (${pc(gr.by_usage.Formal.graph)} against ${pc(gr.by_usage.Formal.baseline)}) and ethnic wear (${pc(gr.by_usage.Ethnic.graph)} against ${pc(gr.by_usage.Ethnic.baseline)}). In groups of 6 products (party, travel) it is no better.`, source: sourceFile('graph-holdout.summary.json') },
      ] : [],
      fails: [b3 ? `It changed the plan on only ${b3.methods.plan_graph.n_prompts} of ${b3.methods.raw.n_prompts} fresh requests in one blind test, so its effect on what people see is small and unproven.` : 'Its effect on what people see is small and unproven.', 'Its occasion word list is short and hand-written: a word it does not know changes nothing.'],
      helped: 'no clear effect', helpedWhy: 'A real gain on held-back labels, but no clear effect on how people rated whole searches.',
      code: ['src/genkart/graph.py', 'scripts/eval_graph.py'],
    },
    {
      id: 'search', title: 'Find products',
      what: 'Each piece becomes numbers (with a fashion-tuned AI model) and is compared with every product photo. The big general collection is searched first. If its best match is weak, three specialist collections are searched too. Duplicates are merged.',
      why: 'One collection cannot hold Indian occasion wear. Matching words to photos also ranked better than matching words to titles.',
      measured: [
        { text: `On ${sc.marqo.nQueries} searches over ${(sc.marqo.nProducts ?? 0).toLocaleString('en')} products, the match score (0 to 1) was ${n3(sc.marqo.ndcg10?.mean ?? 0)} for the fashion model, ${n3(sc.siglipBase.ndcg10?.mean ?? 0)} for a general model and ${n3(sc.bm25.ndcg10?.mean ?? 0)} for plain keyword search.`, source: sourceFile('scale-marqo-fashionsiglip.summary.json') },
        ...(b4 ? [{ text: `Adding three specialist collections raised a person's rating from ${n2(b4.methods.A.mean)} to ${n2(b4.methods.B.mean)} (out of 2) on ${b4.methods.A.n_prompts} Indian-occasion requests. It is the biggest effect we measured.`, source: sourceFile('blind-test4.summary.json') }] : []),
        ...(ck ? [{ text: `Checks after the search (slot fit, children's items, one gender, the named colour first) cut rule breaks in the first pick on ${ck.setup.prompts} requests: a garment in the wrong slot ${ck.before.wrong_slot} to ${ck.after.wrong_slot}, a named colour missing from the photo ${ck.before.colour_missing} to ${ck.after.colour_missing} (of ${ck.after.colour_named}). Counted with the same rules the checks use: how often the rules hold, not a quality rating.`, source: sourceFile('checks-eval.summary.json') }] : []),
        ...(dr.genResnet && dr.text ? [{ text: `The original idea, drawing the outfit first and matching the drawing, scored ${n2(dr.genResnet.ndcg10?.mean ?? 0)} against ${n2(dr.text.ndcg10?.mean ?? 0)} for matching the words (${dr.text.nQueries ?? 20} searches). It was dropped.`, source: sourceFile('m2.summary.json') }] : []),
      ],
      fails: ["Children's ethnic wear and men's kurta and dhoti sets are thin in every collection.", 'Kaggle photos are tiny (60 by 80 pixels). The Myntra set has photos but no titles.'],
      helped: 'helped', helpedWhy: 'More collections helped most. The choice of model helped a little. Drawing first hurt.',
      code: ['src/genkart/catalogue.py', 'src/genkart/embed.py', 'src/genkart/index.py', 'src/genkart/sharding.py', 'src/genkart/dedup.py', 'services/router/src/server.ts'],
    },
    {
      id: 'compose', title: 'Pick an outfit',
      what: 'For each piece, one product is chosen from the closest few, favouring colours that go together (the colour is read from the photo).',
      why: 'The closest match for each piece can clash as a set. A colour score lets a nearly-as-close neutral replace a loud one.',
      measured: oc ? [
        { text: `On ${oc.methods.baseline.n_prompts} multi-piece requests, rated 0 to 2: best match ${n2(oc.methods.baseline.mean)}, colour-matched ${n2(oc.methods.coherent.mean)}, made to clash on purpose ${n2(oc.methods.clash.mean)}. The step changed no rating.`, source: sourceFile('outfit-ratings.summary.json') },
        ...(ev.findings.outfitObjective ? [{ text: `The colour-matched pick equalled the best-match pick on ${ev.findings.outfitObjective.coherent_equals_baseline} of ${ev.findings.outfitObjective.n_prompts} requests: best matches were already harmonious. Red with green was rated fine, as in festive Indian wear.`, source: sourceFile('outfit-objective.summary.json') }] : []),
      ] : [],
      fails: ['Missing items and an AI slip hurt outfits more than colour does.'],
      helped: 'no clear effect', helpedWhy: 'It takes a fraction of a second and changed no rating, so it is no reason to prefer this system.',
      code: ['src/genkart/colour.py', 'src/genkart/outfit.py'],
    },
    {
      id: 'outfit', title: 'Your outfit',
      what: 'The picks, each with a reason taken from data: its score, where it came from, the map note, and the colour read from its photo.',
      why: 'An AI-written story about a pick would sound sure and prove nothing. A reason that can be recomputed can be checked.',
      measured: [{ text: 'No number here: this step only reports what the earlier steps found. The drawn preview is off, because drawing first scored worse.', source: sourceFile('m2.summary.json') }],
      fails: ['If nothing can be built (no product for any piece), the step is skipped and says why.'],
      helped: 'plumbing', helpedWhy: 'Presentation, not search.',
      code: ['src/genkart/server.py', 'src/genkart/outfit.py'],
    },
  ]
}

export function buildDecisions(ev: Ev = evidence): Decision[] {
  const sc = ev.scale, dr = ev.drawing, b4 = ev.findings.blind4, b5 = ev.blind5, aw = ev.aws, oc = ev.findings.outfit
  const o = aw.overload?.variants
  return [
    { date: '2026-10-11', decision: 'Drop "draw the outfit first".', why: dr.genResnet && dr.text ? `Drawing first scored ${n2(dr.genResnet.ndcg10?.mean ?? 0)}; matching the words scored ${n2(dr.text.ndcg10?.mean ?? 0)} (20 searches, free local image tool).` : 'It scored worse than matching the words.', source: sourceFile('m2.summary.json') },
    { date: '2026-10-11', decision: 'Do not repeat the old "+30% accuracy" claim.', why: 'It came from 3 hand-checked searches. Every number now comes from a logged run.' },
    { date: '2026-10-13', decision: 'Keep the fashion-tuned model for search.', why: `On the big test it scored ${n3(sc.marqo.ndcg10?.mean ?? 0)}, against ${n3(sc.siglipBase.ndcg10?.mean ?? 0)} for a general model and ${n3(sc.bm25.ndcg10?.mean ?? 0)} for keywords.`, source: sourceFile('scale-marqo-fashionsiglip.summary.json') },
    { date: '2026-10-14', decision: 'Add three specialist product collections.', why: b4 ? `The first collection has almost no sarees, kurtas or lehengas. A person's score rose from ${n2(b4.methods.A.mean)} to ${n2(b4.methods.B.mean)}.` : 'The first collection lacks Indian ethnic wear.', source: sourceFile('blind-test4.summary.json') },
    { date: '2026-10-14', decision: 'Do not use the IndoFashion dataset.', why: 'It has no clear licence and its authors scraped shops. The rule is public, licensed or made-up data only.' },
    { date: '2026-10-14', decision: 'Keep the colour check, but do not claim it helps.', why: oc ? `Colour-matched scored ${n2(oc.methods.coherent.mean)}, the same as best match (${n2(oc.methods.baseline.mean)}).` : 'No measured effect.', source: sourceFile('outfit-ratings.summary.json') },
    { date: '2026-10-14', decision: 'Keep the local AI model for reading sentences, not Claude.', why: b5 ? `Claude plans scored the same as local ones (${sg(b5.D_minus_C.mean)}). An AI judge said Claude was better on another set${ev.judge5 ? `, but it agrees with the human on only ${pc(ev.judge5.agreement)} of ratings` : ''}, so only human ratings decide.` : 'No measured gain.', source: sourceFile('blind-test5.summary.json') },
    { date: '2026-10-14', decision: 'Split search across several programs, even though one is not slower at this size.', why: 'It lets us measure how a split system behaves: switching to backups, slow parts, incomplete answers, adding products through a queue.', source: sourceFile('router-e2e.summary.json') },
    { date: '2026-10-15', decision: 'Run on AWS in Mumbai, on plain virtual machines.', why: 'Mumbai is closest to Indian shoppers. The author ran every AWS command and holds the credentials. The recording does not need the machines running.' },
    { date: '2026-10-16', decision: 'Say "busy" past 12 searches at once, and drop work nobody waits for.', why: o ? `At 32 people at once, answered searches per second went from ${n2(o.baseline.hardest_level.goodput_per_s)} to ${n2(o.v2.hardest_level.goodput_per_s)}. "Busy" came back in about ${Math.round(o.v2.hardest_level.shed_p50_ms ?? 0)} ms.` : 'Measured on AWS.', source: sourceFile('aws-overload-experiment.summary.json') },
    { date: '2026-10-16', decision: 'The public site shows recordings only. Interaction needs your own model or key, on your own computer.', why: "Nothing can reach the author's computer or keys, and no AWS password is in the site." },
  ]
}

export function buildLimits(ev: Ev = evidence): string[] {
  const j = ev.guard
  return [
    'One person scored the results. They also wrote the requests, but did not know which method made which result. The ranges show chance, not that person\'s taste.',
    ev.judge5 ? `An AI judge agrees with the human on only ${pc(ev.judge5.agreement)} of ${ev.judge5.n} ratings. It is a rough hint and decides nothing.` : 'An AI judge was tried. It is a rough hint and decides nothing.',
    'Test sets 3, 4 and 5 are used up. A change made after seeing their results needs a new set.',
    "Gaps remain in the products: children's ethnic wear, men's kurta and dhoti sets.",
    'The ratings in the Viewer are for plain search on the same request. The page runs the full pipeline, so an outfit can differ from the one rated.',
    'The AWS adding-products numbers were copied by hand from command output. The two copies were compared by counts, not product by product.',
    'The switch-off test phases were worked out afterwards from when the backup was used: start and stop times were not logged.',
    'One early test run was invalid (a helper program was down, cause unknown) and is kept out of the results.',
    'The real AWS bill has not been read: Cost Explorer lags 1 to 2 days. The machines were deleted on 2026-10-16, so the AWS cost shown is an estimate.',
    ...(j ? [`The ${j.hand_rules_only.n_unsafe} unsafe safety-check test cases were written by the author.`] : []),
    'A plan that never drops a product word is an idea, not built. Testing it needs a new set of requests.',
  ]
}

export const RUN_IT = [
  { cmd: 'scripts/setup_env.sh', what: 'Once: set up Python and the libraries.' },
  { cmd: '.venv/bin/python scripts/fetch_pilot_shards.py && .venv/bin/python scripts/fetch_scale_shards.py', what: 'Once: download the Marqo product data (about 4.3 GB). The photos and index are not in the repository.' },
  { cmd: '.venv/bin/python scripts/build_scale_sample.py', what: 'Once: pick the apparel products and save their photos in data/images.' },
  { cmd: '.venv/bin/python scripts/run_eval.py marqo-fashionsiglip --name scale-marqo-fashionsiglip --sample data/sample_scale --manifest data/raw/MANIFEST_scale.json && .venv/bin/python scripts/build_index.py marqo-fashionsiglip', what: 'Once: turn every photo into numbers (slow on a laptop) and save the search index.' },
  { cmd: 'ollama pull qwen3:4b-instruct', what: 'Once: download the local AI model (skip it if you will use your own key).' },
  { cmd: 'GENKART_CATALOGUES=marqo .venv/bin/uvicorn genkart.server:app --app-dir src --port 8000', what: 'Start the server and keep it running. Marqo catalogue only (the other three catalogues need their own downloads). The first search takes about 8 s to load.' },
  { cmd: 'cd web && npm ci && npm run dev', what: 'Start this site. Open http://localhost:5173.' },
  { cmd: 'scripts/cluster.sh start', what: 'Optional: run the split search system on your computer.' },
]
