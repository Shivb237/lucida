// The human-rated test results on the Evidence page: rated methods, paired differences, bars with 95% ranges.
import type { ReactNode } from 'react'
import { Exact, Plain } from './Plain'
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

function SectionHead({ title, lead }: { title: string; lead: ReactNode }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 24, flexWrap: 'wrap' }}>
      <div>
        <h2 className="voice" style={{ margin: 0, fontSize: 'clamp(40px, 5vw, 64px)', lineHeight: 1.06, maxWidth: '22ch' }}>{title}</h2>
      </div>
      {lead ? <p style={{ margin: 0, fontSize: 16, lineHeight: '24px', color: '#33333A', maxWidth: '54ch' }}>{lead}</p> : null}
    </div>
  )
}

const Limit = ({ children }: { children: ReactNode }) => <p style={{ margin: '14px 0 0', fontSize: 14, lineHeight: '21px', color: 'var(--z4)', maxWidth: '84ch' }}>{children}</p>
const Reading = ({ children }: { children: ReactNode }) => <p style={{ margin: '18px 0 0', fontSize: 16, lineHeight: '24px', maxWidth: '78ch' }}>{children}</p>
const RATE = 'Ratings: good = 2, okay = 1, bad = 0. One rater, who also wrote the prompts, so treat these as strong hints and not final proof.'
const TICKS = [0, 0.5, 1, 1.5, 2]

export function Findings() {
  const { blind4, blind3, heldout, graph, outfit, outfitObjective } = evidence.findings
  const g = graph
  return (
    <>
      {blind4 && (
        <section id="sec-catalogues" style={{ marginTop: 96, scrollMarginTop: 24 }}>
          <SectionHead title="Did adding product collections help?"
            lead="" />
          <Plain>A person rated results from 0 to 2 without knowing which method made them. With one product collection the rating was <strong>{blind4.methods.A.mean.toFixed(2)}</strong>. Adding three more collections raised it to <strong>{blind4.methods.B.mean.toFixed(2)}</strong>. Using AI to read the request on top gave {blind4.methods.C.mean.toFixed(2)}: a little higher, but not clearly.</Plain>
          <Exact>
          <div style={{ marginTop: 28, borderTop: '2px solid var(--ink)' }}>
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
        </section>
      )}

      {(blind3 || heldout) && (
        <section id="sec-understanding" style={{ marginTop: 96, scrollMarginTop: 24 }}>
          <SectionHead title="Does the AI step help?"
            lead="" />
          <Plain>The AI step splits a request into pieces before searching. On 30 new requests, searching your plain words scored <strong>{blind3 ? blind3.methods.raw?.mean.toFixed(2) : '—'}</strong> and searching the AI's pieces <strong>{blind3 ? blind3.methods.plan?.mean.toFixed(2) : '—'}</strong>. No clear gain, and it can hurt when it drops words like a colour or a fabric. We expect it to help when a request needs several pieces, but we did not measure that.</Plain>
          <Exact>
          {blind3 && (
            <>
              <div style={{ marginTop: 28, borderTop: '2px solid var(--ink)' }}>
                <Head last="Test" max={2} ticks={TICKS} />
                <RatedRow name="Raw sentence" sub="blind test, 30 fresh prompts" m={blind3.methods.raw} max={2} note="runs/blind-test3.summary.json" />
                <RatedRow name="Understood plan" sub="blind test, same 30 prompts" m={blind3.methods.plan} max={2} note="" />
              </div>
              <Diff label="Plan minus raw" p={blind3.paired['plan-raw']} hint="one collection (Marqo), so only the plan differs" />
            </>
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
          <Reading>No clear gain from the plan on its own, and a small dip on the fresh blind set. It helps when a request must be split into garments (a men's kurta plus pyjama) and keeps gender. It hurts when it shortens a request and drops words that carry meaning, such as colour or fabric; the build log lists those cases, and the next version must never drop a product word.</Reading>
          <Limit>{RATE}</Limit>
                  </Exact>
        </section>
      )}

      {g && (
        <section id="sec-graph" style={{ marginTop: 96, scrollMarginTop: 24 }}>
          <SectionHead title="Does the clothes map help?"
            lead="" />
          <Plain>We hid {g.n_test.toLocaleString('en')} products and asked the map of clothes and occasions to guess their type. It was right <strong>{(g.overall.graph_hit_at_3 * 100).toFixed(0)}%</strong> of the time; without the occasion, <strong>{(g.overall.baseline_hit_at_3 * 100).toFixed(0)}%</strong>. It helps most for formal and ethnic wear. But it changed the plan on only {blind3 ? blind3.methods.plan_graph?.n_prompts : '—'} of {blind3 ? blind3.methods.raw?.n_prompts : '—'} fresh requests, so what people saw barely moved.</Plain>
          <Exact>
          <div style={{ marginTop: 28, display: 'flex', gap: 48, flexWrap: 'wrap', alignItems: 'baseline' }}>
            <div><span className="mono" style={{ fontSize: 64, letterSpacing: '-.04em' }}>{g.overall.graph_hit_at_3.toFixed(3)}</span> <span className="lg dim">with the clothes map</span></div>
            <div><span className="mono" style={{ fontSize: 64, letterSpacing: '-.04em', color: 'var(--z4)' }}>{g.overall.baseline_hit_at_3.toFixed(3)}</span> <span className="lg dim">without it</span></div>
            <div><span className="mono" style={{ fontSize: 28 }}>{sign(g.overall.difference, 3)}</span> <span className="mono dim" style={{ fontSize: 14 }}>[{sign(g.overall.ci95[0], 3)}, {sign(g.overall.ci95[1], 3)}]</span> <span className="lg dim">clear</span></div>
          </div>
          <div style={{ marginTop: 22, borderTop: '2px solid var(--ink)' }}>
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
        </section>
      )}

      {outfit && (
        <section id="sec-colour" style={{ marginTop: 96, scrollMarginTop: 24 }}>
          <SectionHead title="Do matching colours make better outfits?"
            lead="" />
          <Plain>Choosing pieces for matching colours did not change how people rated whole outfits (<strong>{outfit.methods.coherent.mean.toFixed(2)}</strong> against <strong>{outfit.methods.baseline.mean.toFixed(2)}</strong>). Even outfits made to clash scored {outfit.methods.clash.mean.toFixed(2)}: many are festive Indian wear, where strong contrasts are normal.</Plain>
          <Exact>
          <div style={{ marginTop: 28, borderTop: '2px solid var(--ink)' }}>
            <Head last="What it is" max={2} ticks={TICKS} />
            <RatedRow name="Best match per piece" sub="independent picks" m={outfit.methods.baseline} max={2} note="baseline" />
            <RatedRow name="Chosen for harmony" sub="joint pick, rules fixed before rating" m={outfit.methods.coherent} max={2} inUse note="what 'Pick an outfit' runs" />
            <RatedRow name="Made to clash" sub="worst harmony in the top 6 per piece" m={outfit.methods.clash} max={2} note="a check that harmony is visible" />
          </div>
          <div style={{ marginTop: 18 }}>
            <Diff label="Harmony minus best match" p={outfit.paired['coherent-baseline']} hint="the two boards were identical on 28 of 30 prompts" />
            <Diff label="Clash minus best match" p={outfit.paired['clash-baseline']} hint="deliberate clashes, by Western colour rules" />
          </div>
          {outfitObjective && (
            <Reading>By the rules, harmony rose from {outfitObjective.harmony.baseline.toFixed(2)} (best match) to {outfitObjective.harmony.coherent.toFixed(2)} (chosen), and the clash boards sat at {outfitObjective.harmony.clash.toFixed(2)}. Yet the ratings did not move: independent best matches were already almost always neutral colours that go together, and the deliberate clashes did not rate worse. The harmony step stays in as a check; it has not been shown to improve outfits.</Reading>
          )}
          <Limit>{RATE} Many prompts were festive Indian wear, where strong contrasting colours are traditional, so Western harmony rules may be the wrong rules. Sources: runs/outfit-ratings.summary.json, runs/outfit-objective.summary.json.</Limit>
                  </Exact>
        </section>
      )}
    </>
  )
}
