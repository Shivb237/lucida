// The Evidence page: the clearest finding first, then one card per research question (the answer, a small chart on that question's own scale, and the
// exact tables, drawings and sources folded below), with a contents list that follows you down the page. Every number comes from virtual:evidence.
import { useState, type ReactNode } from 'react'
import evidence, { type Strip } from 'virtual:evidence'
import { Findings } from '../components/Findings'
import { Bars, Card, Toc } from '../components/EvidenceKit'
import { Exact } from '../components/Plain'
import { GLOSSARY } from '../content/glossary'
import { PHOTO_BASE } from '../recorded'

const MAX = 0.6

/** One Stable Diffusion drawing. If it fails to load it is asked for once more (past any bad cached answer); if that fails too, a labelled tile says
 *  which address failed, so the problem can be named instead of showing a bare broken-image icon. */
function Drawing({ src, query }: { src: string; query: string }) {
  const [tries, setTries] = useState(0)
  if (tries >= 2) return <a className="drawing-fail" href={src} target="_blank" rel="noreferrer"><span className="lg">Drawing did not load</span><span>{src}</span></a>
  return (
    <img src={tries ? `${src}?retry=${tries}` : src} alt={`Stable Diffusion drawing for: ${query}`} width={512} height={512} loading="lazy" decoding="async"
      onError={() => window.setTimeout(() => setTries((n) => n + 1), tries ? 0 : 1200)}
      style={{ width: '100%', aspectRatio: '1 / 1', objectFit: 'cover', background: 'var(--z2)' }} />
  )
}
const pct = (v: number) => `${(Math.max(0, Math.min(MAX, v)) / MAX) * 100}%`

// What is visibly missing from a drawing, noted by eye on 2026-10-13 (an observation, not a measurement).
const SEEN: Record<string, string> = { '39544': 'no lights', '39583': 'no garment drawn', '39592': 'no graphic', '42170': 'no garment drawn' }


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
const sign = (n: number, d = 2) => `${n >= 0 ? '+' : '−'}${Math.abs(n).toFixed(d)}`

/** The one finding the evidence supports best, with the two that did not hold up and the main limit, before any detail. */
function Takeaway() {
  const b4 = evidence.findings.blind4
  if (!b4) return null
  const ba = b4.paired['B-A'], cb = b4.paired['C-B']
  return (
    <section className="ev-take" aria-labelledby="ev-take-h">
      <div className="ev-take-main">
        <div className="lg dim">The clearest finding</div>
        <h2 id="ev-take-h">Better product coverage mattered more than rewriting the request.</h2>
        <p>In a blind test of Indian-occasion outfits, adding specialist clothing collections moved the ratings a lot. The AI request plan added a smaller change that was not clearly different. These are ratings by a person, on a 0 to 2 scale, not a search-accuracy score.</p>
        <div className="ev-take-scores">
          {([['One collection', b4.methods.A.mean, 'Raw request · Marqo only'], ['Four collections', b4.methods.B.mean, ba ? `Raw request · ${sign(ba.mean)} [${sign(ba.ci95[0])}, ${sign(ba.ci95[1])}]` : 'Raw request'],
            ['Plan + four', b4.methods.C.mean, cb ? `${sign(cb.mean)} [${sign(cb.ci95[0])}, ${sign(cb.ci95[1])}]: not clear` : 'not clearly higher']] as [string, number, string][]).map(([n, v, h]) => (
            <div key={n}><div className="lg dim">{n}</div><div className="mono ev-take-v">{v.toFixed(2)}<small> / 2</small></div><div className="ev-take-hint">{h}</div></div>
          ))}
        </div>
      </div>
      <div className="ev-take-side">
        <div><i className="tile done" aria-hidden="true" /><div><h3>Best-supported change</h3><p>More useful product collections, including Indian ethnic wear.</p></div></div>
        <div><i className="tile hatch" aria-hidden="true" /><div><h3>Not every added step helped</h3><p>Drawing first, rewriting the request and colour-harmony rules did not beat their simpler versions in these tests.</p></div></div>
        <div><i className="tile cross" aria-hidden="true" /><div><h3>Important limit</h3><p>The human ratings came from one person, who also wrote the prompts. A useful signal, not final proof.</p></div></div>
      </div>
    </section>
  )
}

const SECTIONS: [string, string][] = [['sec-methods', 'Which search model?'], ['sec-drawing', 'Draw first?'], ['sec-catalogues', 'More collections?'], ['sec-understanding', 'AI request plan?'],
  ['sec-graph', 'Clothes map?'], ['sec-colour', 'Colour harmony?'], ['sec-feedback', 'Your likes?'], ['words', 'Words and marks']]

export function EvidencePage() {
  const { pilot, drawing, scale } = evidence
  const nPilot = pilot.marqo.nProducts?.toLocaleString('en') ?? '—'
  const nScale = scale.marqo.nProducts?.toLocaleString('en') ?? '—'
  const present = SECTIONS.filter(([id]) => id === 'sec-methods' || id === 'sec-drawing' || id === 'words' || (id === 'sec-catalogues' && evidence.findings.blind4) || (id === 'sec-understanding' && (evidence.findings.blind3 || evidence.findings.heldout))
    || (id === 'sec-graph' && evidence.findings.graph) || (id === 'sec-colour' && evidence.findings.outfit) || (id === 'sec-feedback' && evidence.feedback))
  return (
    <main id="main" tabIndex={-1} className="wrap ev" style={{ paddingTop: 56, paddingBottom: 110 }}>
      <h1 className="voice" style={{ margin: 0, fontSize: 'clamp(52px, 7vw, 96px)', lineHeight: 1, letterSpacing: '-.015em', maxWidth: '15ch' }}>What we measured, and how sure we are.</h1>
      <p className="plain">Every number comes from a saved test run. Each question below has its answer first; the methods, comparisons, drawings and source files are one click deeper, not removed.</p>
      <div className="ev-marks lg dim"><span><i className="tile done" aria-hidden="true" /> Results from logged runs</span><span><i className="tile hatch" aria-hidden="true" /> Ranges show uncertainty</span><span><i className="tile" aria-hidden="true" /> Separate tests stay separate</span></div>
      <Takeaway />
      <div className="ev-read"><span aria-hidden="true" /><p><strong>How to read the page:</strong> search match scores use a 0 to 1 scale (higher is better). Ratings by a person use a separate 0 to 2 scale. The two cannot be compared. A 95% range shows the uncertainty around a measured number; it is not a guarantee.</p></div>

      <div className="ev-layout">
        <Toc items={present} />
        <div className="ev-stack">
          <Card id="sec-methods" num="01" title="Which way of searching works best?" meta={[`Bigger test: ${scale.marqo.nQueries ?? '—'} searches, ${nScale} products`, `First test: ${pilot.marqo.nQueries ?? '—'} searches, ${nPilot} products`]}
            answer={<>A fashion-trained picture-and-words model ranked the right products best. On the bigger test it scored <strong>{f2(m(scale.marqo))}</strong>, ahead of a general model at <strong>{f2(m(scale.siglipBase))}</strong> and keyword matching at <strong>{f2(m(scale.bm25))}</strong>. The lead over the general model is small, but comparing the two search by search puts it clearly above zero.</>}
            means={<>It matches what clothes look like, not only whether your words appear in a title. The bigger test confirmed the first one. Two newer models scored about the same in the first test, so the current one stays.</>}>
            <Bars title="Match score · NDCG@10, bigger test" scale="higher is better · 0–1" max={0.6} ticks={[0, 0.2, 0.4, 0.6]}
              rows={[{ name: 'Marqo-FashionSigLIP', sub: 'fashion-trained · in use', value: m(scale.marqo), primary: true }, { name: 'SigLIP base', sub: 'general model', value: m(scale.siglipBase) }, { name: 'Keyword search (BM25)', sub: 'words in titles', value: m(scale.bm25) }]}
              caption="How high the right products sit in the first ten results. Not a percentage of correct answers." />
            <Exact label="Show both tests, every method and the logged metrics">
              <h3 className="ev-sub">Bigger test · {scale.marqo.nQueries ?? '—'} searches, {nScale} products</h3>
              <Head last="Logged" />
              <Row name="Random" sub="the floor" s={scale.random} />
              <Row name="Keyword search (BM25)" sub="classic word matching on titles" s={scale.bm25} />
              <Row name="SigLIP base" sub="general picture-and-words model" s={scale.siglipBase} />
              <Row name="Marqo-FashionSigLIP" sub="fashion-tuned · in use · the live search uses this index" s={scale.marqo} inUse />
              <p className="ev-note">On the larger catalogue both picture-and-words models clearly beat keyword search. The fashion model is ahead of SigLIP base: the two ranges drawn here overlap slightly, but comparing the two search by search on the same searches puts the difference clearly above zero. Small, but real.</p>
              <h3 className="ev-sub">First test · {pilot.marqo.nQueries ?? '—'} searches, {nPilot} products · not comparable with the bigger test</h3>
              <Head last="Logged" />
              <Row name="Random" sub="the floor" s={pilot.random} />
              <Row name="Keyword search (BM25)" sub="classic word matching on titles" s={pilot.bm25} />
              <Row name="SigLIP base" sub="general picture-and-words model" s={pilot.siglipBase} />
              <Row name="Marqo-FashionSigLIP" sub="fashion-tuned · in use" s={pilot.marqo} inUse />
              <Row name="Google SigLIP 2" sub="newer, general, 384 px" s={pilot.siglip2} />
              <Row name="ZooClaw-FashionSigLIP2" sub="newer, fashion-tuned; its makers claim best, we measured" s={pilot.zooclaw} />
              <Row name="SigLIP 2, first run" sub="superseded: lowercasing bug" s={pilot.siglip2Bug} old />
              <Row name="ZooClaw, first run" sub="superseded: lowercasing bug" s={pilot.zooclawBug} old />
              <p className="ev-note">Picture-and-words models clearly beat keyword search. The two newer models land level with the one <span style={{ color: 'var(--mag)', fontWeight: 700 }}>in use</span>; their ranges overlap, so it stays. Struck rows are first runs with a lowercasing bug, kept on the record. The solid part of each bar is the score we are sure of, the hatched band the 95% range, the tick the average.</p>
            </Exact>
          </Card>

          <Card id="sec-drawing" num="02" title="Does drawing the outfit first help?" meta={['The original GenKart idea', `${drawing.text?.nQueries ?? drawing.frames.length} searches`, 'Stable Diffusion 1.5']}
            answer={<>No. Drawing an outfit with AI and then searching for products that look like the drawing scored <strong>{f2(m(drawing.genResnet))}</strong>. Searching directly with the typed words scored <strong>{f2(m(drawing.text))}</strong>. Drawing first made results worse, so it was dropped.</>}
            means={<>A drawing can lose the colour, fabric, pattern or garment the request named. In this small test the typed words carried more useful information.</>}>
            <Bars title="Direct words against drawing first" scale="match score NDCG@10 · 0–1" max={0.6} ticks={[0, 0.2, 0.4, 0.6]}
              rows={[{ name: 'Typed words', sub: 'direct text search', value: m(drawing.text), primary: true }, { name: 'Words plus drawing', value: m(drawing.textGen) }, { name: 'Drawing, fashion model', value: m(drawing.genFashion) }, { name: 'Drawing, ResNet50', sub: 'the v1 way', value: m(drawing.genResnet) }]}
              caption="Small sample, and a fixed prompt instead of v1's GPT-3.5 rewrite: a clear signal, not the final word on every way of drawing first." />
            {PHOTO_BASE && <p style={{ margin: '16px 0 0' }}><a className="btn-line" style={{ display: 'inline-flex', alignItems: 'center', textDecoration: 'none' }} href={`${PHOTO_BASE}/#/study`}>Take part in a 5-minute study: does a drawing help you?</a></p>}
            <Exact label={`Show the ${drawing.frames.length} drawings and the paired results`}>
            <div className="film" style={{ marginTop: 22, padding: '24px 26px 22px' }}>
              <div className="edge" style={{ justifyContent: 'space-between' }}><span style={{ color: 'var(--paper)' }}>LUCIDA 400 · STABLE DIFFUSION 1.5 · 20 STEPS</span><span>{drawing.frames.length} DRAWINGS</span></div>
              <div className="drawn-grid">
                {drawing.frames.map((f) => {
                  const won = f.drawn != null && f.words != null && f.drawn > f.words
                  return (
                    <figure key={f.queryId} style={{ margin: 0, position: 'relative' }}>
                      <div style={{ position: 'relative' }}>
                        <Drawing src={`${import.meta.env.BASE_URL}${f.image}`} query={f.query} />
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
                NDCG@10 per search. <span style={{ color: 'var(--mag-film)' }}>Circled</span>: where the drawing won. Tags note what is visibly missing from a drawing, seen by eye, not a score. These are AI drawings, not product photos. Sources: runs/gen_sd15.jsonl · runs/m2-gen-resnet50.jsonl · runs/m2-direct-text.jsonl.
              </p>
            </div>
            <div style={{ marginTop: 32 }}>
              <Head last="Against typed words, search by search" />
              <Row name="Typed words" sub="direct text search (reference)" s={drawing.text} extra={<Paired s={drawing.text} />} />
              <Row name="Words plus drawing" sub="both scores added" s={drawing.textGen} extra={<Paired s={drawing.textGen} />} />
              <Row name="Drawing, fashion model" sub="drawing matched with Marqo-FashionSigLIP" s={drawing.genFashion} extra={<Paired s={drawing.genFashion} />} />
              <Row name="Drawing, ResNet50 (v1 way)" sub="the original GenKart pipeline" s={drawing.genResnet} extra={<Paired s={drawing.genResnet} />} />
            </div>
            </Exact>
          </Card>

          <Findings />

          <Card id="words" num={String(present.length).padStart(2, '0')} title="Words, and what the marks mean." meta={['Reading guide', `${GLOSSARY.length} terms`, 'State shown by pattern, not colour alone']}
            answer={<>The page uses two score scales and a few marks. The marks show state by line and pattern; pink means something is picked or can be pressed, never whether a test succeeded.</>}
            means={<>Read the plain answer first. Open the exact details for ranges, per-prompt results, methods and source files.</>} meansLabel="Quick rule">
            <div className="ev-legend">
              <div><span className="ev-mark" style={{ border: '1.5px dotted var(--z4)' }} /><div><strong>Waiting, or not run yet</strong><p>Dotted outline: no measured result yet.</p></div></div>
              <div><span className="ev-mark hatch" /><div><strong>Running, or the likely range</strong><p>Hatching: work in progress, or a 95% range on a bar.</p></div></div>
              <div><span className="ev-mark" style={{ background: 'var(--ink)' }} /><div><strong>Done</strong><p>Solid: a step completed.</p></div></div>
              <div><span className="ev-mark cross" /><div><strong>Failed or partial</strong><p>Cross-hatching: a part that did not reply, or an incomplete answer.</p></div></div>
              <div><span className="ev-mark" style={{ position: 'relative' }}><i style={{ position: 'absolute', left: 0, right: 0, top: 11, height: 2, background: 'var(--ink)' }} /></span><div><strong>Crossed out</strong><p>Not built yet, skipped, or replaced.</p></div></div>
              <div><svg className="ev-mark" aria-hidden="true" viewBox="0 0 100 60" style={{ border: 0 }}><ellipse cx="50" cy="30" rx="44" ry="25" fill="none" stroke="var(--mag)" strokeWidth="3" /></svg><div><strong>Pink</strong><p>Picked, or something you can press.</p></div></div>
            </div>
            <p className="ev-note"><a className="inline-link" href="#/words">See all {GLOSSARY.length} terms in the Glossary →</a></p>
          </Card>
        </div>
      </div>
    </main>
  )
}

