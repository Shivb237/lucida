// The contact sheet, outfit print and at-a-glance row, with a placeholder where the Viewer has no photo.
import { useState } from 'react'
import { NAME } from '../brand'
import { scrollToId } from '../ui'
import { Flat, type FlatName } from '../flats'
import { SOURCE_LABEL, SOURCE_NOTE, type Hit, type OutfitItem, type PieceResult } from '../trace'

const CIRCLES = [
  'M52 3 C82 2 98 22 97 51 C96 81 74 98 46 97 C18 96 2 76 4 47 C6 20 27 5 60 6',
  'M44 5 C76 1 99 26 95 56 C91 86 64 99 36 94 C10 89 1 62 6 36 C10 14 32 4 56 8',
  'M58 4 C86 8 97 34 93 60 C89 88 60 98 34 91 C8 84 3 56 9 32 C15 10 40 2 52 2',
]
const hash = (s: string) => [...s].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7)

export type Mode = 'idle' | 'live' | 'demo' | 'recorded'

export function Picture({ hit }: { hit: Hit }) {
  const [failed, setFailed] = useState(false)   // a photo that cannot be loaded (no local server) falls back to the labelled placeholder
  if (hit.flat) return <Flat shape={hit.flat.shape as FlatName} fill={hit.flat.fill} label={hit.title} />
  if (!hit.image || failed) return <div className="no-photo" role="img" aria-label={`No photo in the recorded Viewer. ${hit.title || 'Untitled product'}`}><span className="lg">No photo</span><span>{SOURCE_LABEL[hit.source] ?? hit.source}</span></div>
  return <img src={hit.image} alt={hit.title} loading="lazy" onLoad={() => window.dispatchEvent(new Event('genkart-photo'))} onError={() => setFailed(true)} />
}

export function SourceChip({ source }: { source: string }) {
  return <span className="src" title={SOURCE_NOTE[source] ?? ''}>{SOURCE_LABEL[source] ?? source}</span>
}

/** The closest products per piece. Shows the first 3 (plus the pick, if it sat lower) until the visitor asks for all of them. */
export function ContactSheet({ pieces, picked, mode, liked, onLike, inStep = false }: { pieces: PieceResult[]; picked: Set<string>; mode: Mode; liked?: Set<string>; onLike?: (id: string) => void; inStep?: boolean }) {
  const [all, setAll] = useState(false)
  const sources = [...new Set(pieces.flatMap((p) => p.hits.map((h) => h.source)))]
  const most = Math.max(0, ...pieces.map((p) => p.hits.length))
  return (
    <section aria-label="Search results" className="film contact dev" style={{ marginTop: inStep ? 18 : 72 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', alignItems: 'baseline' }}>
        <h3 className="h-record">Contact sheet</h3>
        <span style={{ fontSize: 16, color: 'var(--z7)', maxWidth: '72ch' }}>
          The closest products for each piece. <span style={{ color: 'var(--mag-film)' }}>Circled</span> = picked for your outfit (it can skip a closer match). The number under each photo is how close it is to your words: higher is closer.
          {mode === 'live' && ' Real photos from this computer.'}
        </span>
      </div>
      {mode !== 'demo' && sources.length > 0 && (
        <p style={{ margin: '12px 0 0', fontSize: 15, lineHeight: '22px', color: 'var(--z7)' }}>
          Collections here: {sources.map((s) => `${SOURCE_LABEL[s] ?? s} (${SOURCE_NOTE[s] ?? ''})`).join('; ')}.
        </p>
      )}
      {pieces.map((row) => {
        const shown = all ? row.hits : row.hits.filter((h, i) => i < 3 || picked.has(h.id))
        return (
          <div key={row.text} style={{ marginTop: 24 }}>
            <div className="edge"><span style={{ color: 'var(--paper)' }}>{row.kind.toUpperCase()}</span><span>{row.text}</span><span>{NAME.toUpperCase()} 400</span><span>{row.seconds.toFixed(3)} s</span></div>
            {row.hits.length === 0 && <p style={{ margin: '10px 0 0', color: 'var(--z7)' }}>No product found for this piece.</p>}
            <div className="frames">
              {shown.map((h) => {
                const i = row.hits.indexOf(h)
                return (
                  <figure key={h.id}>
                    <div style={{ position: 'relative' }}>
                      <div className="positive"><Picture hit={h} /></div>
                      {picked.has(h.id) && (
                        <svg className="grease" aria-hidden="true" viewBox="0 0 100 100" preserveAspectRatio="none" style={{ transform: `rotate(${(hash(h.id) % 13) - 6}deg) scale(${1 + (hash(h.id) % 7) / 100})` }}>
                          <path pathLength={100} d={CIRCLES[hash(h.id) % 3]} fill="none" stroke="var(--mag-film)" strokeWidth="3.4" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
                        </svg>
                      )}
                    </div>
                    <figcaption><span style={{ color: 'var(--z7)' }}>#{i + 1}{picked.has(h.id) ? ' · picked' : ''}</span><span>{h.score.toFixed(3)}</span></figcaption>
                    <div className="frame-title">{h.title || <span style={{ fontStyle: 'italic' }}>no title in this collection</span>}</div>
                    <SourceChip source={h.source} />
                    {onLike && (
                      <button type="button" className="like-btn" aria-pressed={liked?.has(h.id) ?? false} aria-label={`Like: ${h.title || 'this product'}`} onClick={() => onLike(h.id)}>
                        <svg aria-hidden="true" width="14" height="14" viewBox="0 0 14 14" fill={liked?.has(h.id) ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"><path d="M7 12.2 1.9 7.3a2.9 2.9 0 0 1 4.1-4.1L7 4.2l1-1a2.9 2.9 0 0 1 4.1 4.1Z" /></svg>
                        {liked?.has(h.id) ? 'Liked' : 'Like'}
                      </button>
                    )}
                  </figure>
                )
              })}
            </div>
          </div>
        )
      })}
      {most > 3 && (
        <button type="button" className="film-btn" aria-expanded={all} onClick={() => setAll((a) => !a)}>
          {all ? 'Show the first 3 for each piece' : `Show all ${most} for each piece`}
        </button>
      )}
    </section>
  )
}

export function Print({ items, alreadyHas, mode }: { items: OutfitItem[]; alreadyHas: string[]; mode: Mode }) {
  return (
    <div className="dev print-row">
      <div className="print" style={{ flex: '1 1 460px', minWidth: 0 }}>
        <div className="tapebit" style={{ left: -26, top: 16, transform: 'rotate(-38deg)' }} />
        <div className="tapebit tape-r" style={{ right: -26, top: 16, transform: 'rotate(38deg)' }} />
        <div className="board" style={{ gridTemplateColumns: `repeat(${items.length === 4 ? 2 : Math.min(items.length, 3)}, minmax(0, 1fr))` }}>
          {items.map((it) => (
            <figure key={it.pick.id} style={{ margin: 0 }}>
              <div className="positive"><Picture hit={it.pick} /></div>
              <figcaption className="lg" style={{ marginTop: 6, color: 'var(--z4)' }}>{it.kind}</figcaption>
            </figure>
          ))}
        </div>
        <div className="mono dim" style={{ position: 'absolute', left: 22, right: 22, bottom: 16, fontSize: 13, display: 'flex', justifyContent: 'space-between' }}>
          <span>look 01 · {items.length} piece{items.length === 1 ? '' : 's'}</span><span>{mode === 'demo' ? 'demo' : mode === 'recorded' ? 'recorded' : 'real photos'}</span>
        </div>
      </div>
      <div id="outfit-why" style={{ flex: '1 1 380px', minWidth: 0 }}>
        <h3 className="lg dim step-h">Why each piece</h3>
        {alreadyHas.length > 0 && (
          <p style={{ margin: '10px 0 0', fontSize: 17, lineHeight: '26px' }}>
            <span className="lg dim">Built to go with what you own</span><br />
            <span className="voice" style={{ fontSize: 30 }}>{alreadyHas.join(', ')}</span>
          </p>
        )}
        <div style={{ marginTop: 20, borderTop: '2px solid var(--ink)' }}>
          {items.map((it) => (
            <div className="credit" key={it.pick.id}>
              <div><div className="lg">{it.kind}</div><SourceChip source={it.pick.source} /></div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 18 }}>{it.pick.title || it.piece} <span className="mono dim" style={{ fontWeight: 400, fontSize: 13, marginLeft: 6 }}>match #{it.rank}</span></div>
                <ul style={{ margin: '4px 0 0', paddingLeft: '1.1em', fontSize: 17, lineHeight: '26px', color: 'var(--z2a)' }}>
                  {it.reasons.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
              </div>
            </div>
          ))}
        </div>
        <p style={{ margin: '18px 0 0', fontSize: 16, lineHeight: '24px', color: 'var(--z4)', maxWidth: '56ch' }}>
          Each reason comes from data (scores, the clothes map, photo colour), not from an AI-written story. <strong style={{ color: 'var(--ink)' }}>Drawn preview: off</strong>, because drawing first scored worse.
        </p>
      </div>
    </div>
  )
}

/** The payoff at the top of the page: the picked photos in a row, so a first-time viewer sees the outfit without scrolling past the process. */
export function Glance({ items, mode }: { items: OutfitItem[]; mode: Mode }) {
  return (
    <section aria-label="Your outfit at a glance" className="glance dev">
      <div className="lg dim">Your outfit, at a glance{mode === 'demo' ? ' (demo)' : mode === 'recorded' ? ' (recorded)' : ''}</div>
      <div className="glance-row">
        {items.map((it) => (
          <figure key={it.pick.id} style={{ margin: 0 }}>
            <div className="positive glance-pic"><Picture hit={it.pick} /></div>
            <figcaption className="lg" style={{ marginTop: 4, color: 'var(--z4)' }}>{it.kind}</figcaption>
          </figure>
        ))}
        <button type="button" className="btn-line" onClick={() => scrollToId('outfit-why')}>See why, piece by piece <svg aria-hidden="true" width="12" height="12" viewBox="0 0 12 12" style={{ marginLeft: 6, verticalAlign: '-1px' }}><path d="M2 4l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg></button>
      </div>
    </section>
  )
}
