// The human-rated test results on the Evidence page, one card per question: the answer and a small bar chart up front, the rated methods, paired
// differences and 95% ranges in the exact-numbers panel. Plus the simulated feedback test (Milestone 8).
import type { ReactNode } from 'react'
import { Exact } from './Plain'
import { Bars, Card, MiniStats } from './EvidenceKit'
import evidence, { type Paired, type Rated } from 'virtual:evidence'

const pct = (v: number, max: number) => `${(Math.max(0, Math.min(max, v)) / max) * 100}%`
const sign = (n: number, d = 2) => `${n >= 0 ? '+' : '−'}${Math.abs(n).toFixed(d)}`

function Axis({ max, ticks }: { max: number; ticks: number[] }) {
  return <div className="scale">{ticks.map((v) => <span key={v}>{v}</span>)}<span style={{ display: 'none' }}>{max}</span></div>
}

function Head({ last, max, ticks }: { last: string; max: number; ticks: number[] }) {
  return (
    <div className="srow head-row" style={{ padding: '12px 0 6px' }}>
      <div className="lg dim">Method</div><Axis max={max} ticks={ticks} />
      <div className="lg dim" style={{ textAlign: 'right' }}>Average</div>
      <div className="lg dim" style={{ textAlign: 'right' }}>good / okay / bad</div>
      <div className="lg dim">{last}</div>
    </div>
  )
}

function RatedRow({ name, sub, m, max, inUse, note }: { name: string; sub: string; m: Rated | undefined; max: number; inUse?: boolean; note?: ReactNode }) {
  return (
    <div className="srow" style={{ padding: '14px 0', borderTop: '1px solid var(--z8)' }}>
      <div>
        <div style={{ fontWeight: 700, fontSize: 18 }}>{name}</div>
        <div style={{ fontSize: 13, lineHeight: '18px', color: 'var(--z4)', marginTop: 2 }}>{sub}</div>
      </div>
      {m ? (
        <div className="track" role="img" style={{ backgroundSize: `${100 / 4}% 100%` }} aria-label={`average ${m.mean.toFixed(2)}, 95% range ${m.ci95[0].toFixed(2)} to ${m.ci95[1].toFixed(2)}`}>
          <div className="solid" style={{ width: pct(m.ci95[0], max) }} />
          <div className="ci hatch" style={{ left: pct(m.ci95[0], max), width: pct(m.ci95[1] - m.ci95[0], max) }} />
          <div className={`tick${inUse ? ' in-use' : ''}`} style={{ left: pct(m.mean, max) }} />
        </div>
      ) : <div className="track none lg">Not run yet</div>}
      <div className="mono" style={{ textAlign: 'right', fontSize: 28, letterSpacing: '-.02em', color: inUse ? 'var(--mag)' : 'var(--ink)' }}>{m ? m.mean.toFixed(2) : '—'}</div>
      <div className="mono" style={{ textAlign: 'right', fontSize: 14 }}>{m ? `${m.good}/${m.okay}/${m.bad}` : '—'}</div>
      <div style={{ fontSize: 14 }}>{note}</div>
    </div>
  )
}

function Diff({ label, p, hint }: { label: string; p: Paired | undefined; hint: string }) {
  if (!p) return null
  const clear = p.ci95[0] > 0 || p.ci95[1] < 0
  return (
    <div className="diff-row">
      <div style={{ fontWeight: 600 }}>{label}</div>
      <div>
        <span className="mono" style={{ fontSize: 20 }}>{sign(p.mean)}</span>{' '}
        <span className="mono dim" style={{ fontSize: 13 }}>[{sign(p.ci95[0])}, {sign(p.ci95[1])}]</span>{' '}
        <span style={{ fontSize: 14 }}>better on {p.better}, worse on {p.worse}, same on {p.tied} of {p.n_prompts} prompts · <strong>{clear ? 'a clear difference' : 'not clearly different'}</strong></span>
        <div style={{ fontSize: 13, color: 'var(--z4)', marginTop: 2 }}>{hint}</div>
      </div>
    </div>
  )
}

const Limit = ({ children }: { children: ReactNode }) => <p style={{ margin: '14px 0 0', fontSize: 14, lineHeight: '21px', color: 'var(--z4)', maxWidth: '84ch' }}>{children}</p>
const Reading = ({ children }: { children: ReactNode }) => <p style={{ margin: '18px 0 0', fontSize: 16, lineHeight: '24px', maxWidth: '78ch' }}>{children}</p>
const RATE = 'Ratings: good = 2, okay = 1, bad = 0. One rater, who also wrote the prompts, so treat these as strong hints and not final proof.'
const TICKS = [0, 0.5, 1, 1.5, 2]

export function Findings() {
  const { blind4, blind3, heldout, graph, outfit, outfitObjective } = evidence.findings
  const { blind5, understanding, claudeVsQwen, feedback } = evidence
  const g = graph
  const fb = feedback?.metrics.likes_only
  return (
    <>
      {blind4 && (
        <Card id="sec-catalogues" num="03" title="Did adding product collections help?" meta={['Blind human ratings', `${blind4.methods.A.n_prompts} Indian-occasion prompts`, 'One rater', 'Test set 4 · fresh then, now used']}
          answer={<>Yes: the biggest improvement came from more collections. A person's rating rose from <strong>{blind4.methods.A.mean.toFixed(2)}</strong> with one collection to <strong>{blind4.methods.B.mean.toFixed(2)}</strong> with four (out of 2). Adding the AI request plan on top gave {blind4.methods.C.mean.toFixed(2)}: a little higher, but not clearly.</>}
          means={<>The first collection had almost no Indian ethnic wear. A better-worded request cannot find a garment that is not in the product list.</>} meansLabel="Why it matters">
          <Bars title="Average outfit rating" scale="0 = bad · 1 = okay · 2 = good" max={2} ticks={TICKS} digits={2}
            rows={[{ name: 'A · Raw request', sub: 'one collection (Marqo)', value: blind4.methods.A.mean }, { name: 'B · Raw request', sub: 'four collections', value: blind4.methods.B.mean, primary: true }, { name: 'C · AI plan', sub: 'four collections', value: blind4.methods.C.mean }]}
            caption={RATE} />
          <Exact label="Show the exact differences and limits">
          <div style={{ marginTop: 22, borderTop: '2px solid var(--ink)' }}>
            <Head last="What it is" max={2} ticks={TICKS} />
            <RatedRow name="A · raw sentence, one collection" sub="the sentence as typed, searched in Marqo only" m={blind4.methods.A} max={2} note="the old setup" />
            <RatedRow name="B · raw sentence, four collections" sub="the sentence as typed, searched in all four" m={blind4.methods.B} max={2} note="adds Kaggle, Myntra photos, men's set" />
            <RatedRow name="C · AI plan, four collections" sub="the AI plan, clothes map, gender; all four" m={blind4.methods.C} max={2} inUse note="what this page runs" />
          </div>
          <div style={{ marginTop: 18 }}>
            <Diff label="B minus A" p={blind4.paired['B-A']} hint="adding the three Indian-wear collections" />
            <Diff label="C minus B" p={blind4.paired['C-B']} hint="understanding the request first, on top of that" />
            <Diff label="C minus A" p={blind4.paired['C-A']} hint="everything together" />
          </div>
          <Reading>Adding the collections was the big win: Marqo has almost no Indian wear (the build log counted zero kurtas, lehengas or sherwanis in the titles of its 40,513 products). Understanding the request added a little more, but not clearly. Where nothing scored above okay, the cause was data: no children's Indian wear, almost no men's kurtas, no indo-western mixes.</Reading>
          <Limit>{RATE} Source: runs/blind-test4.summary.json, recomputed by scripts/summarise_blind.py from the raw ratings and the answer key.</Limit>
          </Exact>
        </Card>
      )}

      {(blind3 || heldout) && (
        <Card id="sec-understanding" num="04" title="Does the AI request plan help?" meta={['Human-rated comparisons', 'Test sets 3 and 5 · fresh then, now used', 'Separate experiments']}
          answer={<>Not reliably, so far. The plan splits a request into pieces before searching. On {blind3 ? blind3.methods.raw?.n_prompts : '—'} new requests, the plain words scored <strong>{blind3 ? blind3.methods.raw?.mean.toFixed(2) : '—'}</strong> and the AI's pieces <strong>{blind3 ? blind3.methods.plan?.mean.toFixed(2) : '—'}</strong>{blind5 ? <>; on {blind5.n_prompts} more, plain words {blind5.mean.B.toFixed(2)}, a local model's plan {blind5.mean.C.toFixed(2)} and a Claude plan {blind5.mean.D.toFixed(2)}</> : null}. It can drop words like a colour or a fabric.</>}
          means={<>Keep the free local model: a paid one did no better. The next version must never drop a product word, and splitting multi-piece requests needs its own fair test.</>} meansLabel="What we learned">
          {blind3 && (
            <Bars title={`Blind test 3 · ${blind3.methods.raw?.n_prompts ?? '—'} fresh prompts`} scale="human rating · 0–2" max={2} ticks={TICKS} digits={2}
              rows={[{ name: 'Raw sentence', value: blind3.methods.raw?.mean, primary: true }, { name: 'Understood plan', value: blind3.methods.plan?.mean }]}
              caption="Different tests and different measures stay apart: the extra tests are inside, each with its own scale." />
          )}
          <Exact label="Compare the related prompt experiments">
          {blind3 && (
            <>
              <div style={{ marginTop: 22, borderTop: '2px solid var(--ink)' }}>
                <Head last="Test" max={2} ticks={TICKS} />
                <RatedRow name="Raw sentence" sub={`blind test, ${blind3.methods.raw?.n_prompts ?? '—'} fresh prompts`} m={blind3.methods.raw} max={2} note="runs/blind-test3.summary.json" />
                <RatedRow name="Understood plan" sub="blind test, same prompts" m={blind3.methods.plan} max={2} note="" />
              </div>
              <Diff label="Plan minus raw" p={blind3.paired['plan-raw']} hint="one collection (Marqo), so only the plan differs" />
            </>
          )}
          {blind5 && (
            <div style={{ marginTop: 26 }}>
              <Bars title={`Blind test 5 · ${blind5.n_prompts} fresh prompts, ${blind5.n_ratings} ratings`} scale="human rating · 0–2" max={2} ticks={TICKS} digits={2}
                rows={[{ name: 'Raw request', value: blind5.mean.B, primary: true }, { name: 'Local model plan', sub: 'Qwen3 4B', value: blind5.mean.C }, { name: 'Claude plan', value: blind5.mean.D }]}
                caption={<>Claude minus local plan: {sign(blind5.D_minus_C.mean)} [{sign(blind5.D_minus_C.ci95[0])}, {sign(blind5.D_minus_C.ci95[1])}], not clearly different{claudeVsQwen ? <>; those Claude calls cost ${claudeVsQwen.claude_cost_usd.toFixed(2)}</> : null}. Source: runs/blind-test5.summary.json.</>} />
            </div>
          )}
          {understanding && (
            <div style={{ marginTop: 26 }}>
              <Bars title={`Retrieval test · ${understanding.n} messy rewrites of labelled searches`} scale="match score NDCG@10 · 0–1" max={0.6} ticks={[0, 0.2, 0.4, 0.6]}
                rows={[{ name: 'Original labelled query', value: understanding.original }, { name: 'Messy rewrite', value: understanding.raw }, { name: 'AI-understood rewrite', value: understanding.understood, primary: true }]}
                caption="A different scale from the human ratings above (0–1, not 0–2): do not rank them together. Source: runs/m4.summary.json." />
            </div>
          )}
          {heldout && (
            <div style={{ marginTop: 18 }}>
              <div className="diff-row">
                <div style={{ fontWeight: 600 }}>Earlier check (not blind)</div>
                <div>
                  <span className="mono" style={{ fontSize: 20 }}>{sign(heldout.mean_diff_plan_minus_raw_0to2.mean)}</span>{' '}
                  <span className="mono dim" style={{ fontSize: 13 }}>[{sign(heldout.mean_diff_plan_minus_raw_0to2.ci95[0])}, {sign(heldout.mean_diff_plan_minus_raw_0to2.ci95[1])}]</span>{' '}
                  <span style={{ fontSize: 14 }}>plan better on {heldout.per_prompt_plan_vs_raw.plan_better}, worse on {heldout.per_prompt_plan_vs_raw.plan_worse}, same on {heldout.per_prompt_plan_vs_raw.tied} of {heldout.n_prompts} prompts · <strong>not clearly different</strong></span>
                  <div style={{ fontSize: 13, color: 'var(--z4)', marginTop: 2 }}>runs/m4-heldout-ratings.summary.json; row labels were visible when rating</div>
                </div>
              </div>
            </div>
          )}
          <Reading>It helps when a request must be split into garments (a men's kurta plus pyjama) and keeps gender. It hurts when it shortens a request and drops words that carry meaning, such as colour or fabric; the build log lists those cases, and the next version must never drop a product word.</Reading>
          <Limit>{RATE}</Limit>
          </Exact>
        </Card>
      )}

      {g && (
        <Card id="sec-graph" num="05" title="Does the clothes map help?" meta={['Held-out product test', `${g.n_test.toLocaleString('en')} hidden products`, 'Separate from outfit ratings']}
          answer={<>It guessed product types better: with hidden products, the map of clothes and occasions was right <strong>{(g.overall.graph_hit_at_3 * 100).toFixed(1)}%</strong> of the time, against <strong>{(g.overall.baseline_hit_at_3 * 100).toFixed(1)}%</strong> without it. But it changed the plan on only {blind3 ? blind3.methods.plan_graph?.n_prompts : '—'} of {blind3 ? blind3.methods.raw?.n_prompts : '—'} fresh requests, so what people saw barely moved.</>}
          means={<>The map links an occasion to likely clothing types. Useful under the hood; no broad visible gain in the whole search yet.</>}>
          <MiniStats items={[{ value: g.overall.graph_hit_at_3.toFixed(3), label: 'type guessed in the top 3, with the clothes map' }, { value: g.overall.baseline_hit_at_3.toFixed(3), label: 'without the occasion links' },
            { value: blind3 ? `${blind3.methods.plan_graph?.n_prompts ?? '—'} / ${blind3.methods.raw?.n_prompts ?? '—'}` : '—', label: 'fresh requests whose plan it changed' }]} />
          <Exact label="Show the graph test, by occasion">
          <div style={{ marginTop: 22, display: 'flex', gap: 32, flexWrap: 'wrap', alignItems: 'baseline' }}>
            <div><span className="mono" style={{ fontSize: 28 }}>{sign(g.overall.difference, 3)}</span> <span className="mono dim" style={{ fontSize: 14 }}>[{sign(g.overall.ci95[0], 3)}, {sign(g.overall.ci95[1], 3)}]</span> <span className="lg dim">difference, clear</span></div>
          </div>
          <div style={{ marginTop: 16, borderTop: '2px solid var(--ink)' }}>
            {Object.entries(g.by_usage).filter(([, v]) => v.n_test >= 20).map(([u, v]) => (
              <div key={u} className="usage-row">
                <span style={{ fontWeight: 700 }}>{u}</span>
                <span className="mono dim" style={{ fontSize: 13 }}>n = {v.n_test}</span>
                <span className="mono">{v.graph.toFixed(3)}</span>
                <span className="mono dim">{v.baseline.toFixed(3)}</span>
                <span className="mono" style={{ fontSize: 14 }}>{sign(v.graph - v.baseline, 3)} <span className="dim">[{sign(v.diff_ci95[0], 3)}, {sign(v.diff_ci95[1], 3)}]</span></span>
              </div>
            ))}
          </div>
          <Reading>The clothes map helps most where occasions have a clear dress code (formal and ethnic wear) and barely for everyday casual wear. Occasions with fewer than 20 test items (party, travel, smart casual) are left out: too few to judge. The graph is a lookup of label counts, not full GraphRAG: no model extracts relations from text.</Reading>
          <Limit>Source: runs/graph-holdout.summary.json. Column order: with graph, without, difference with its 95% range.</Limit>
          </Exact>
        </Card>
      )}

      {outfit && (
        <Card id="sec-colour" num="06" title="Do matching colours make better outfits?" meta={['Blind outfit ratings', `${outfit.methods.baseline.n_prompts} prompts`, 'One rater']}
          answer={<>No visible change: choosing pieces for matching colours rated <strong>{outfit.methods.coherent.mean.toFixed(2)}</strong>, the same as the best match per piece at <strong>{outfit.methods.baseline.mean.toFixed(2)}</strong>. Even outfits made to clash scored {outfit.methods.clash.mean.toFixed(2)}.</>}
          means={<>Most pieces were neutral colours, and strong contrasts such as red with green are normal in Indian festive wear. Western colour rules may be the wrong rules here.</>} meansLabel="Why it surprised us">
          <Bars title="Average rating per outfit" scale="human rating · 0–2" max={2} ticks={TICKS} digits={2}
            rows={[{ name: 'Best match per piece', sub: 'baseline', value: outfit.methods.baseline.mean }, { name: 'Chosen for harmony', value: outfit.methods.coherent.mean, primary: true }, { name: 'Made to clash', value: outfit.methods.clash.mean }]}
            caption={outfitObjective ? `The harmony and baseline boards were identical on ${outfitObjective.coherent_equals_baseline} of ${outfitObjective.n_prompts} prompts.` : undefined} />
          <Exact label="Show paired ratings and the colour scores">
          <div style={{ marginTop: 22, borderTop: '2px solid var(--ink)' }}>
            <Head last="What it is" max={2} ticks={TICKS} />
            <RatedRow name="Best match per piece" sub="independent picks" m={outfit.methods.baseline} max={2} note="baseline" />
            <RatedRow name="Chosen for harmony" sub="joint pick, rules fixed before rating" m={outfit.methods.coherent} max={2} inUse note="what 'Pick an outfit' runs" />
            <RatedRow name="Made to clash" sub="worst harmony in the top 6 per piece" m={outfit.methods.clash} max={2} note="a check that harmony is visible" />
          </div>
          <div style={{ marginTop: 18 }}>
            <Diff label="Harmony minus best match" p={outfit.paired['coherent-baseline']} hint="the two boards were often identical" />
            <Diff label="Clash minus best match" p={outfit.paired['clash-baseline']} hint="deliberate clashes, by Western colour rules" />
          </div>
          {outfitObjective && (
            <Reading>By the rules, harmony rose from {outfitObjective.harmony.baseline.toFixed(2)} (best match) to {outfitObjective.harmony.coherent.toFixed(2)} (chosen), and the clash boards sat at {outfitObjective.harmony.clash.toFixed(2)}. Yet the ratings did not move: independent best matches were already almost always neutral colours that go together, and the deliberate clashes did not rate worse. The harmony step stays in as a check; it has not been shown to improve outfits.</Reading>
          )}
          <Limit>{RATE} Sources: runs/outfit-ratings.summary.json, runs/outfit-objective.summary.json.</Limit>
          </Exact>
        </Card>
      )}

      {fb && feedback && (
        <Card id="sec-feedback" num="07" title="Do your likes improve the results?" meta={['Simulated shopper, not a person', `${feedback.setup.test_queries} held-out searches`, 'One round of likes']}
          answer={<>A little, in a simulation. A computer pretending to be a shopper liked the right products among the first {feedback.setup.shown_before_feedback} shown; the results after those improved from <strong>{fb.ndcg10_residual_without_feedback.mean.toFixed(3)}</strong> to <strong>{fb.ndcg10_residual_with_feedback.mean.toFixed(3)}</strong> (better on {fb.paired_difference.better} searches, worse on {fb.paired_difference.worse}). Pushing away from disliked products made results worse, so the Lab uses likes only.</>}
          means={<>A simulation built from the dataset's own labels, which are incomplete. A consented study with real people is running in the Lab; it has no results yet.</>} meansLabel="How sure">
          <Bars title="Results beyond the first ten shown" scale="match score NDCG@10 · 0–1" max={0.6} ticks={[0, 0.2, 0.4, 0.6]}
            rows={[{ name: 'Without likes', value: fb.ndcg10_residual_without_feedback.mean }, { name: 'With likes', value: fb.ndcg10_residual_with_feedback.mean, primary: true }]}
            caption={<>Difference {sign(fb.paired_difference.mean, 3)} [{sign(fb.paired_difference.ci95[0], 3)}, {sign(fb.paired_difference.ci95[1], 3)}]: small but clear. The weight was chosen on the other half of the searches. Source: runs/feedback-sim.summary.json.</>} />
        </Card>
      )}
    </>
  )
}
