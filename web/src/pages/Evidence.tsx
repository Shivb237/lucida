// The Evidence page: the short version in six lines, then each question with its plain answer and the exact bars and tables folded below.
import type { ReactNode } from 'react'
import evidence, { type Strip } from 'virtual:evidence'
import { Findings } from '../components/Findings'
import { Exact, Plain } from '../components/Plain'

const MAX = 0.6
const pct = (v: number) => `${(Math.max(0, Math.min(MAX, v)) / MAX) * 100}%`

// What is visibly missing from a drawing, noted by eye on 2026-10-13 (an observation, not a measurement).
const SEEN: Record<string, string> = { '39544': 'no lights', '39583': 'no garment drawn', '39592': 'no graphic', '42170': 'no garment drawn' }

const JUMPS: [string, string][] = [['sec-methods', 'Best way to search'], ['sec-drawing', 'Drawing first?'], ['sec-scale', 'Bigger test'], ['sec-catalogues', 'More collections?'],
  ['sec-understanding', 'The AI step?'], ['sec-graph', 'Clothes map'], ['sec-colour', 'Matching colours'], ['words', 'Words']]

function Jump() {
  return (
    <nav aria-label="On this page" className="chip-row" style={{ marginTop: 28 }}>
      <span className="lg dim" style={{ marginRight: 4 }}>Jump to</span>
      {JUMPS.map(([id, label]) => (
        <button key={id} type="button" className="chip" onClick={() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })}>{label}</button>
      ))}
    </nav>
  )
}

function Scale() {
  return <div className="scale">{[0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6].map((v) => <span key={v}>{v}</span>)}</div>
}

function Row({ name, sub, s, inUse, old, extra }: { name: string; sub: string; s: Strip | null; inUse?: boolean; old?: boolean; extra?: ReactNode }) {
  const m = s?.logged ? s.ndcg10 : undefined
  return (
    <div className="srow" style={{ padding: '14px 0', borderTop: '1px solid var(--z8)', opacity: old ? 0.55 : 1 }}>
      <div>
        <div style={{ fontWeight: 700, fontSize: 18, textDecoration: old ? 'line-through' : 'none' }}>{name}</div>
        <div style={{ fontSize: 13, lineHeight: '18px', color: 'var(--z4)', marginTop: 2 }}>{sub}</div>
      </div>
      {m ? (
        <div className="track" role="img" aria-label={`NDCG at 10 ${m.mean.toFixed(4)}, 95% range ${m.ci95[0].toFixed(4)} to ${m.ci95[1].toFixed(4)}`}>
          <div className="solid" style={{ width: pct(m.ci95[0]) }} />
          <div className="ci hatch" style={{ left: pct(m.ci95[0]), width: pct(m.ci95[1] - m.ci95[0]) }} />
          <div className={`tick${inUse ? ' in-use' : ''}`} style={{ left: pct(m.mean) }} />
          {old && <div className="strike" />}
        </div>
      ) : (
        <div className="track none lg">Not exposed yet</div>
      )}
      <div className="mono" style={{ textAlign: 'right', fontSize: 28, letterSpacing: '-.02em', color: inUse ? 'var(--mag)' : 'var(--ink)' }}>{m ? m.mean.toFixed(4) : '—'}</div>
      <div className="mono" style={{ textAlign: 'right', fontSize: 15 }}>{s?.logged && s.recall50 != null ? s.recall50.toFixed(4) : '—'}</div>
      <div>
        {extra ?? (
          <>
            <div style={{ fontSize: 14 }}>{s?.logged ? s.date : 'not run yet'}</div>
            <div className="mono" style={{ fontSize: 12, lineHeight: '15px', color: 'var(--z4)', wordBreak: 'break-all' }}>{s?.logged ? s.file : 'no file yet'}</div>
          </>
        )}
      </div>
    </div>
  )
}

function Head({ last }: { last: string }) {
  return (
    <div className="srow head-row" style={{ padding: '12px 0 6px' }}>
      <div className="lg dim">Method</div><Scale />
      <div className="lg dim" style={{ textAlign: 'right' }}>Average</div>
      <div className="lg dim" style={{ textAlign: 'right' }}>In top 50</div>
      <div className="lg dim">{last}</div>
    </div>
  )
}

function Paired({ s }: { s: Strip | null }) {
  const p = s?.paired
  if (!p) return <div style={{ fontSize: 14 }}>reference</div>
  return (
    <>
      <div style={{ fontSize: 15, fontWeight: 600 }}>worse on {p.worse} of {p.better + p.tied + p.worse}</div>
      <div className="mono" style={{ fontSize: 12, lineHeight: '15px', color: 'var(--z4)' }}>{p.mean.toFixed(4)} [{p.ci95[0].toFixed(4)}, {p.ci95[1].toFixed(4)}]</div>
    </>
  )
}

const f2 = (x: number | undefined) => (x == null ? '—' : x.toFixed(2))
const m = (s: Strip | null) => s?.ndcg10?.mean
function plainMethods(p: typeof evidence.pilot) {
  return <>Searching product <strong>photos</strong> with an AI trained on fashion scored <strong>{f2(m(p.marqo))}</strong> out of 1. Matching the words to product <strong>titles</strong> scored {f2(m(p.bm25))}. Two newer models scored about the same as the one we use, so we kept it.</>
}
function plainDrawing(d: typeof evidence.drawing) {
  return <>The original idea was to draw the outfit with AI, then find products that look like the drawing. That scored <strong>{f2(m(d.genResnet))}</strong>. Using your typed words directly scored <strong>{f2(m(d.text))}</strong>. So drawing first made results <strong>worse</strong>, and we dropped it. It was a small test: {d.text?.nQueries ?? 20} searches.</>
}
function plainScale(s: typeof evidence.scale) {
  return <>On a much bigger test the fashion AI scored <strong>{f2(m(s.marqo))}</strong>, a general model {f2(m(s.siglipBase))}, and plain keyword matching {f2(m(s.bm25))}. The fashion model stays a little ahead.</>
}

function ShortVersion() {
  const { drawing, scale, findings: f } = evidence
  const b4 = f.blind4, b3 = f.blind3, g = f.graph, o = f.outfit
  return (
    <ol className="short">
      <li><b>Drawing the outfit first made search worse</b> ({f2(m(drawing.genResnet))} against {f2(m(drawing.text))} for your words).</li>
      <li><b>An AI trained on fashion is a little better than a general-purpose one</b> ({f2(m(scale.marqo))} against {f2(m(scale.siglipBase))}).</li>
      {b4 && <li><b>Adding Indian-wear collections helped most</b>: a person's rating went from {f2(b4.methods.A.mean)} to {f2(b4.methods.B.mean)} out of 2.</li>}
      {b3 && <li><b>The AI step that reads your sentence did not clearly help</b> ({f2(b3.methods.plan?.mean)} against {f2(b3.methods.raw?.mean)} for plain words).</li>}
      {g && <li><b>A map of how clothes fit occasions guessed hidden products' types better</b> ({(g.overall.graph_hit_at_3 * 100).toFixed(0)}% right against {(g.overall.baseline_hit_at_3 * 100).toFixed(0)}%), but it changed the plan on only {b3 ? b3.methods.plan_graph.n_prompts : '—'} of {b3 ? b3.methods.raw.n_prompts : '—'} fresh requests.</li>}
      {o && <li><b>Choosing for matching colours changed nothing people could see</b> ({f2(o.methods.coherent.mean)} against {f2(o.methods.baseline.mean)}).</li>}
    </ol>
  )
}

export function EvidencePage() {
  const { pilot, drawing, scale } = evidence
  const nPilot = pilot.marqo.nProducts?.toLocaleString('en') ?? '—'
  const nScale = scale.marqo.nProducts?.toLocaleString('en') ?? '—'
  return (
    <main id="main" tabIndex={-1} className="wrap" style={{ paddingTop: 56, paddingBottom: 110 }}>
      <h1 className="voice" style={{ margin: 0, fontSize: 'clamp(52px, 7vw, 96px)', lineHeight: 1, letterSpacing: '-.015em', maxWidth: '15ch' }}>What we measured, and how sure we are.</h1>
      <p className="plain">The short version, in six lines. Every number comes from a saved test run. Below, each question has its answer in a sentence, and the exact bars and tables are one click away.</p>
      <ShortVersion />
      <Exact label="How to read the bars">
        <p className="plain" style={{ fontSize: 16, lineHeight: '24px' }}>Each bar shows a match score from 0 to 1 (its technical name is NDCG@10): how high up the list the right products sit. 1 is perfect. The solid part is the score we are sure of; the hatched band is the 95% range, where the true score probably lies; the tick is the average. Different sets of searches never share a chart.</p>
      </Exact>

      <Jump />

      <section id="sec-methods" style={{ marginTop: 72, scrollMarginTop: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 16, flexWrap: 'wrap', borderBottom: '2px solid var(--ink)', paddingBottom: 12 }}>
          <h2 className="h-record" style={{ fontSize: 28 }}>Which way of searching works best?</h2>
          <span className="lg dim">First test · {pilot.marqo.nQueries ?? '—'} test requests, {nPilot} products</span>
        </div>
        <Plain>{plainMethods(pilot)}</Plain>
        <Exact>
        <Head last="Logged" />
        <Row name="Random" sub="the floor" s={pilot.random} />
        <Row name="Keyword search (BM25)" sub="classic word matching on titles" s={pilot.bm25} />
        <Row name="SigLIP base" sub="general picture-and-words model" s={pilot.siglipBase} />
        <Row name="Marqo-FashionSigLIP" sub="fashion-tuned · in use" s={pilot.marqo} inUse />
        <Row name="Google SigLIP 2" sub="newer, general, 384 px" s={pilot.siglip2} />
        <Row name="ZooClaw-FashionSigLIP2" sub="newer, fashion-tuned; its makers claim best, we measured" s={pilot.zooclaw} />
        <Row name="SigLIP 2, first run" sub="superseded: lowercasing bug" s={pilot.siglip2Bug} old />
        <Row name="ZooClaw, first run" sub="superseded: lowercasing bug" s={pilot.zooclawBug} old />
        <p style={{ margin: '18px 0 0', fontSize: 16, lineHeight: '24px', maxWidth: '78ch' }}>
          Picture-and-words models clearly beat keyword search. The two newer models land level with the one <span style={{ color: 'var(--mag)', fontWeight: 700 }}>in use</span>; their ranges overlap, so it stays. Struck rows are first runs with a lowercasing bug, kept on the record.
        </p>
        </Exact>
      </section>

      <section id="sec-drawing" style={{ marginTop: 96, scrollMarginTop: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 24, flexWrap: 'wrap' }}>
          <div>
            <h2 className="voice" style={{ margin: 0, fontSize: 'clamp(40px, 5vw, 64px)', lineHeight: 1.06, maxWidth: '20ch' }}>Does drawing the outfit first help?</h2>
          </div>
          <p style={{ margin: 0, fontSize: 16, lineHeight: '24px', color: '#33333A', maxWidth: '52ch' }}>
            {drawing.frames.length} real drawings an AI image tool made, with how well each found products against how well the typed words did.
          </p>
        </div>
        <Plain>{plainDrawing(drawing)}</Plain>
        <Exact label="Show the 20 drawings and the exact numbers">
        <div className="film" style={{ marginTop: 28, padding: '24px 26px 22px' }}>
          <div className="edge" style={{ justifyContent: 'space-between' }}><span style={{ color: 'var(--paper)' }}>LUCIDA 400 · STABLE DIFFUSION 1.5 · 20 STEPS</span><span>runs/gen_sd15.jsonl · runs/m2-gen-resnet50.jsonl · runs/m2-direct-text.jsonl</span></div>
          <div className="drawn-grid">
            {drawing.frames.map((f) => {
              const won = f.drawn != null && f.words != null && f.drawn > f.words
              return (
                <figure key={f.queryId} style={{ margin: 0, position: 'relative' }}>
                  <div style={{ position: 'relative' }}>
                    <img src={`${import.meta.env.BASE_URL}${f.image}`} alt={`Stable Diffusion drawing for: ${f.query}`} loading="lazy" style={{ width: '100%', aspectRatio: '1 / 1', objectFit: 'cover', background: 'var(--z2)' }} />
                    {SEEN[f.queryId] && <div className="tagnote lg">{SEEN[f.queryId]}</div>}
                    {won && <svg className="grease" aria-hidden="true" viewBox="0 0 100 100" preserveAspectRatio="none" style={{ left: '-8%', top: '-8%', width: '116%', height: '116%' }}><path pathLength={100} d="M52 3 C82 2 98 22 97 51 C96 81 74 98 46 97 C18 96 2 76 4 47 C6 20 27 5 60 6" fill="none" stroke="var(--mag-film)" strokeWidth="3.4" strokeLinecap="round" vectorEffect="non-scaling-stroke" /></svg>}
                  </div>
                  <figcaption style={{ marginTop: 10 }}>
                    <div style={{ fontSize: 13, lineHeight: '17px', minHeight: 34 }}>{f.query}</div>
                    <div className="mini">
                      <span className="lg" style={{ fontSize: 12, color: 'var(--z7)' }}>Drawn</span>
                      <div className="b"><div style={{ width: `${((f.drawn ?? 0) / 0.8) * 100}%`, background: 'repeating-linear-gradient(-45deg, var(--paper) 0 1.2px, transparent 1.2px 4px)' }} /></div>
                      <span className="mono" style={{ fontSize: 12, textAlign: 'right' }}>{f.drawn?.toFixed(3) ?? '—'}</span>
                      <span className="lg" style={{ fontSize: 12, color: 'var(--z7)' }}>Words</span>
                      <div className="b"><div style={{ width: `${((f.words ?? 0) / 0.8) * 100}%`, background: 'var(--paper)' }} /></div>
                      <span className="mono" style={{ fontSize: 12, textAlign: 'right' }}>{f.words?.toFixed(3) ?? '—'}</span>
                    </div>
                  </figcaption>
                </figure>
              )
            })}
          </div>
          <p style={{ margin: '20px 0 0', fontSize: 14, lineHeight: '21px', color: 'var(--z7)', maxWidth: '100ch' }}>
            NDCG@10 per search. <span style={{ color: 'var(--mag-film)' }}>Circled</span>: where the drawing won. Tags note what is visibly missing from a drawing, seen by eye. Drawings are read from this computer and never stored in the repository.
          </p>
        </div>
        <div style={{ marginTop: 40 }}>
          <Head last="Against typed words, search by search" />
          <Row name="Typed words" sub="direct text search (reference)" s={drawing.text} extra={<Paired s={drawing.text} />} />
          <Row name="Words plus drawing" sub="both scores added" s={drawing.textGen} extra={<Paired s={drawing.textGen} />} />
          <Row name="Drawing, fashion model" sub="drawing matched with Marqo-FashionSigLIP" s={drawing.genFashion} extra={<Paired s={drawing.genFashion} />} />
          <Row name="Drawing, ResNet50 (v1 way)" sub="the original GenKart pipeline" s={drawing.genResnet} extra={<Paired s={drawing.genResnet} />} />
          <p style={{ margin: '18px 0 0', fontSize: 16, lineHeight: '24px', maxWidth: '78ch' }}>
            On these searches, matching the typed words directly ranked better than drawing first and matching the drawing; the v1 way was the weakest. Small sample and a fixed prompt rather than v1's GPT-3.5 rewrite: a clear signal, not a final word.
          </p>
        </div>
        </Exact>
      </section>

      <section id="sec-scale" style={{ marginTop: 96, scrollMarginTop: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 16, flexWrap: 'wrap', borderBottom: '2px solid var(--ink)', paddingBottom: 12 }}>
          <h2 className="h-record" style={{ fontSize: 28 }}>Does it still hold on a bigger test?</h2>
          <span className="lg dim">{scale.marqo.nQueries ?? '—'} test requests, {nScale} products · not comparable with the first test</span>
        </div>
        <Plain>{plainScale(scale)}</Plain>
        <Exact>
        <Head last="Logged" />
        <Row name="Random" sub="the floor" s={scale.random} />
        <Row name="Keyword search (BM25)" sub="classic word matching on titles" s={scale.bm25} />
        <Row name="SigLIP base" sub="general picture-and-words model" s={scale.siglipBase} />
        <Row name="Marqo-FashionSigLIP" sub="fashion-tuned · in use · the live search uses this index" s={scale.marqo} inUse />
        <p style={{ margin: '18px 0 0', fontSize: 16, lineHeight: '24px', maxWidth: '78ch' }}>
          On the larger catalogue both picture-and-words models clearly beat keyword search. The fashion model is ahead of SigLIP base by 0.026: the two ranges drawn here overlap slightly, but comparing the two search by search on the same 852 searches puts the difference clearly above zero. Small, but real.
        </p>
              </Exact>
      </section>

      <Findings />

      <section id="words" style={{ marginTop: 96, scrollMarginTop: 24 }}>
        <h2 className="voice" style={{ margin: 0, fontSize: 'clamp(40px, 5vw, 64px)', lineHeight: 1.06 }}>Words, and what the marks mean.</h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 56, marginTop: 28 }}>
          <div className="sheet" style={{ flex: '1 1 380px', minWidth: 0, padding: '24px 26px', transform: 'rotate(-.5deg)' }}>
            <div className="tapebit" style={{ left: 40, top: -12, transform: 'rotate(-3deg)' }} />
            <div className="lg dim">The marks</div>
            <div style={{ display: 'grid', gridTemplateColumns: '60px minmax(0, 1fr)', gap: '14px 18px', marginTop: 14, alignItems: 'center', fontSize: 15 }}>
              <div style={{ height: 26, border: '1.5px dotted var(--z4)' }} /><div>Waiting, or not run yet</div>
              <div className="hatch" style={{ height: 26 }} /><div>Running, or the likely range on a bar</div>
              <div style={{ height: 26, background: 'var(--ink)' }} /><div>Done</div>
              <div className="cross" style={{ height: 26 }} /><div>Failed, for example a part that did not reply</div>
              <div style={{ height: 26, position: 'relative' }}><div style={{ position: 'absolute', left: 0, right: 0, top: 12, height: 2, background: 'var(--ink)' }} /></div><div>Crossed out: not built yet, or replaced</div>
              <svg aria-hidden="true" viewBox="0 0 100 60" style={{ width: 60, height: 34 }}><ellipse cx="50" cy="30" rx="44" ry="25" fill="none" stroke="var(--mag)" strokeWidth="3" /></svg><div>Pink: picked, or something you can press</div>
            </div>
          </div>
          <div style={{ flex: '2 1 560px', minWidth: 0 }}><Exact label="Show all 12 terms"><dl style={{ flex: '2 1 560px', minWidth: 0, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '0 40px', margin: 0 }}>
            {GLOSSARY.map(([t, d]) => (
              <div key={t} style={{ padding: '14px 0', borderTop: '1px solid var(--z8)' }}>
                <dt style={{ fontWeight: 700, fontSize: 16 }}>{t}</dt>
                <dd style={{ margin: '3px 0 0', fontSize: 15, lineHeight: '22px', color: '#33333A' }}>{d}</dd>
              </div>
            ))}
          </dl></Exact></div>
        </div>
      </section>
    </main>
  )
}

const GLOSSARY: [string, string][] = [
  ['Match score (NDCG@10)', 'A 0 to 1 score for how high the right products sit in the top 10. 1 is perfect.'],
  ['Found in the top 50 (Recall@50)', 'Of the products people rated as right, the share that appear in the first 50 results.'],
  ['95% range', 'The span where the true score probably lies, found by re-running the test on shuffled samples 1,000 times.'],
  ['Labelled search', 'A search where people already rated the products, so its score can be worked out.'],
  ['Embedding', 'A list of numbers standing for a picture or a sentence, so the two can be compared.'],
  ['Similarity score (cosine)', 'How closely two lists of numbers point the same way: the number under each photo.'],
  ['Keyword search (BM25)', 'The classic way: count how many of your words appear in a product title.'],
  ['SigLIP', 'An AI model that reads pictures and words together. Fashion versions are trained further on clothes.'],
  ['Slice (shard)', 'One part of the product list, searched by its own worker at the same time as the others.'],
  ['Clothes map (knowledge graph)', 'A map of how clothes, colours and occasions relate. It adds ideas you did not type.'],
  ['Ollama', 'Software that runs an AI model on your own computer, so no paid key is needed.'],
  ['Stable Diffusion', 'An AI tool that draws pictures from words. Version 1 of this project drew outfits first.'],
]
