// One small drawing for the "journey of one request" (How it works page): the recorded sentence moving through the six steps.
// Words -> pieces -> the clothes map -> matches in the four collections -> candidates beside each piece -> one outfit.
// It moves only when the reader's step changes (no loop), stops when off-screen or the tab is hidden, and under reduced motion
// draws each step's still frame. Greys only; magenta marks the picked products. Square forms only. Everything drawn comes from the run.
import { useEffect, useRef } from 'react'
import { SOURCE_LABEL } from '../trace'
import type { Journey } from '../content/story'

type Tone = 'ink' | 'z4' | 'z6' | 'z8' | 'mag' | 'paper' | 'white'
type Item =
  | { k: string; t: 'box'; x: number; y: number; w: number; h: number; fill?: Tone; stroke?: Tone; dash?: boolean; a: number }
  | { k: string; t: 'text'; x: number; y: number; s: string; size: number; tone: Tone; caps?: boolean; bold?: boolean; a: number; max?: number }
  | { k: string; t: 'line'; x: number; y: number; x2: number; y2: number; tone: Tone; dash?: boolean; a: number }

const calm = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
const ease = (t: number) => 1 - Math.pow(1 - t, 3)
const lerp = (a: number, b: number, t: number) => a + (b - a) * t
const PW = 108   // the width of a piece box from step 4 on
const SANS = "'Archivo Variable', 'Archivo', system-ui, sans-serif"

/** Lays the sentence's words out in lines that fit the width (measured with the real font). */
function wrapWords(ctx: CanvasRenderingContext2D, words: string[], x0: number, y0: number, maxW: number, size: number, lh: number) {
  ctx.font = `500 ${size}px ${SANS}`
  const out: { x: number; y: number; w: number }[] = []
  let x = x0, y = y0
  for (const w of words) {
    const ww = ctx.measureText(w).width
    if (x > x0 && x + ww > x0 + maxW) { x = x0; y += lh }
    out.push({ x, y, w: ww })
    x += ww + 7
  }
  return out
}

/** The layout of one step: every item has a key, so the same thing glides from one step's place to the next. */
function scene(step: number, j: Journey, W: number, H: number, ctx: CanvasRenderingContext2D): Item[] {
  const items: Item[] = []
  const pad = 14
  const words = j.prompt.split(/\s+/).filter(Boolean)
  // the sentence: large and dark on step 1, a quiet line at the top afterwards
  const big = step === 0
  // after step 1 the words sit on one quiet line; words past the edge fade out
  const placed = wrapWords(ctx, words, pad, big ? 44 : 22, big ? W - pad * 2 : 1e6, big ? 17 : 13, big ? 26 : 18)
  const lastY = placed.length ? placed[placed.length - 1].y : 22
  placed.forEach((p, i) => items.push({ k: `w${i}`, t: 'text', x: p.x, y: p.y, s: words[i], size: big ? 17 : 13, tone: big ? 'ink' : 'z4', a: big || p.x + p.w <= W - pad ? 1 : 0 }))
  const top = lastY + (big ? 30 : 24)

  if (step === 0) {
    // a straight gate under the words: the safety check, and its answer
    items.push({ k: 'gate', t: 'line', x: pad, y: top + 8, x2: W - pad, y2: top + 8, tone: 'ink', a: 1 })
    items.push({ k: 'gate-l', t: 'text', x: pad, y: top + 30, s: `Safety check: ${j.guard === 'allow' ? 'allowed' : j.guard.replace(/_/g, ' ')}`, size: 13, tone: 'ink', caps: true, bold: true, a: 1 })
    items.push({ k: 'gate-pass', t: 'box', x: pad, y: top + 44, w: W - pad * 2, h: 10, fill: 'ink', a: 1 })
    return items
  }

  const n = Math.max(j.pieces.length, 1)
  const pieceW = step >= 3 ? PW : Math.min(150, (W - pad * 2 - (n - 1) * 10) / n)
  const pieceH = step >= 3 ? 40 : 58
  const area = H - top - pad
  const piecePos = (i: number) => step >= 3
    ? { x: pad, y: top + (area / n) * i + (area / n - pieceH) / 2 }
    : { x: pad + i * (pieceW + 10), y: top + 6 }

  j.pieces.forEach((p, i) => {
    const { x, y } = piecePos(i)
    items.push({ k: `p${i}`, t: 'box', x, y, w: pieceW, h: pieceH, fill: 'paper', stroke: 'ink', a: 1 })
    items.push({ k: `pk${i}`, t: 'text', x: x + 8, y: y + 18, s: p.kind, size: 13, tone: 'ink', caps: true, bold: true, a: 1, max: pieceW - 14 })
    if (step < 3) items.push({ k: `pt${i}`, t: 'text', x: x + 8, y: y + 38, s: p.text, size: 13, tone: 'z4', a: 1, max: pieceW - 14 })
  })

  if (step === 1) return items

  if (step === 2) {
    // the clothes map: a small grid of square nodes; the occasion it recognised is solid, joined to every piece by a straight rule
    const gy = top + pieceH + 30
    const cols = 6, cell = Math.min(26, (W - pad * 2) / cols - 8)
    for (let r = 0; r < 2; r++) for (let c = 0; c < cols; c++) {
      const hit = r === 0 && c < j.usages.length
      items.push({ k: `m${r}${c}`, t: 'box', x: pad + c * (cell + 8), y: gy + r * (cell + 8), w: cell, h: cell, fill: hit ? 'ink' : undefined, stroke: hit ? 'ink' : 'z6', dash: !hit, a: 1 })
    }
    j.pieces.forEach((_, i) => {
      const p = piecePos(i)
      items.push({ k: `ml${i}`, t: 'line', x: p.x + pieceW / 2, y: p.y + pieceH, x2: pad + cell / 2, y2: gy, tone: 'z4', a: 1 })
    })
    const said = j.usages.length ? `Occasion: ${j.usages.join(', ')}` : 'No occasion recognised'
    items.push({ k: 'm-l', t: 'text', x: pad, y: gy + cell * 2 + 28, s: said, size: 13, tone: 'ink', caps: true, bold: true, a: 1, max: W - pad * 2 })
    items.push({ k: 'm-l2', t: 'text', x: pad, y: gy + cell * 2 + 46, s: j.added ? `${j.added} idea${j.added === 1 ? '' : 's'} added` : 'Nothing added', size: 13, tone: 'z4', a: 1 })
    return items
  }

  // steps 4 to 6: four collections as rows on the right
  const cx = pad + PW + 26, cw = W - cx - pad
  const rowH = Math.min(46, (area - 3 * 8) / 4)
  const rowY = (r: number) => top + r * (rowH + 8)
  const sq = 10, gap = 3

  if (step === 3) {
    j.collections.forEach((c, r) => {
      items.push({ k: `c${r}`, t: 'box', x: cx, y: rowY(r), w: cw, h: rowH, stroke: 'z6', a: 1 })
      items.push({ k: `cl${r}`, t: 'text', x: cx + 6, y: rowY(r) + 16, s: SOURCE_LABEL[c] ?? c, size: 13, tone: 'z4', caps: true, a: 1, max: cw - 12 })
    })
    const fill = new Map<string, number>()
    j.pieces.forEach((p, i) => {
      const pp = piecePos(i)
      const used = new Set(p.hits.map((h) => h.source))
      const searched = [...used].some((s) => s !== 'marqo') ? j.collections : ['marqo']   // the specialists are asked only when the general match is weak
      searched.forEach((c) => {
        const r = j.collections.indexOf(c)
        if (r < 0) return
        items.push({ k: `fan${i}${r}`, t: 'line', x: pp.x + PW, y: pp.y + pieceH / 2, x2: cx, y2: rowY(r) + rowH / 2, tone: used.has(c) ? 'ink' : 'z6', dash: !used.has(c), a: 1 })
      })
      p.hits.forEach((h, n2) => {
        const r = Math.max(0, j.collections.indexOf(h.source))
        const at = fill.get(h.source) ?? 0
        fill.set(h.source, at + 1)
        const perLine = Math.max(1, Math.floor((cw - 12) / (sq + gap)))
        items.push({ k: `h${i}-${n2}`, t: 'box', x: cx + 6 + (at % perLine) * (sq + gap), y: rowY(r) + 22 + Math.floor(at / perLine) * (sq + gap), w: sq, h: sq, fill: 'ink', a: 1 })
      })
    })
    return items
  }

  if (step === 4) {
    // candidates beside their piece; the pick in magenta, with the colour read from its photo
    const big2 = Math.min(22, (W - cx - pad) / 6 - 5)
    j.pieces.forEach((p, i) => {
      const pp = piecePos(i)
      p.hits.forEach((h, n2) => {
        const x = cx + n2 * (big2 + 5)
        items.push({ k: `h${i}-${n2}`, t: 'box', x, y: pp.y + (pieceH - big2) / 2, w: big2, h: big2, fill: h.picked ? 'mag' : undefined, stroke: h.picked ? 'mag' : 'z4', a: h.picked ? 1 : 0.9 })
      })
      const k = p.hits.findIndex((h) => h.picked)
      const colour = j.picks.find((x) => x.kind === p.kind)?.colour
      if (k >= 0) items.push({ k: `col${i}`, t: 'text', x: cx + k * (big2 + 5), y: pp.y + pieceH / 2 + big2 / 2 + 18, s: colour ? `picked · ${colour}` : 'picked', size: 13, tone: 'ink', a: 1 })
    })
    return items
  }

  // step 6: one print holding the picks
  const m = j.picks.length || 1
  const pw = Math.min(W - cx - pad, m * 64 + 20), ph = 112
  const px = cx, py = top + (area - ph) / 2
  items.push({ k: 'print', t: 'box', x: px, y: py, w: pw, h: ph, fill: 'white', stroke: 'z6', a: 1 })
  items.push({ k: 'print-l', t: 'text', x: px, y: py + ph + 22, s: 'One outfit', size: 13, tone: 'ink', caps: true, bold: true, a: 1 })
  j.pieces.forEach((p, i) => {
    p.hits.forEach((h, n2) => {
      if (!h.picked) return
      const slot = j.picks.findIndex((x) => x.id === h.id)
      const x = px + 10 + Math.max(slot, 0) * 64
      items.push({ k: `h${i}-${n2}`, t: 'box', x, y: py + 12, w: 54, h: 54, fill: 'mag', stroke: 'mag', a: 1 })
      items.push({ k: `ok${i}`, t: 'text', x, y: py + 86, s: p.kind, size: 13, tone: 'ink', caps: true, bold: true, a: 1, max: 58 })
    })
  })
  return items
}

/** What the current frame shows, in words, for screen readers. */
function frameLabel(step: number, j: Journey): string {
  const kinds = j.pieces.map((p) => p.kind).join(', ')
  const from = (p: Journey['pieces'][number]) => [...new Set(p.hits.map((h) => SOURCE_LABEL[h.source] ?? h.source))].join(' and ')
  switch (step) {
    case 0: return `Drawing: the sentence "${j.prompt}" passes the safety check (${j.guard === 'allow' ? 'allowed' : j.guard.replace(/_/g, ' ')}).`
    case 1: return `Drawing: the sentence becomes ${j.pieces.length} piece${j.pieces.length === 1 ? '' : 's'} to search: ${kinds}.`
    case 2: return `Drawing: the clothes map ${j.usages.length ? `reads the occasion as ${j.usages.join(', ')}` : 'recognises no occasion'} and adds ${j.added || 'nothing'}.`
    case 3: return `Drawing: each piece is sent to the product collections. ${j.pieces.map((p) => `${p.kind}: ${p.hits.length} matches from ${from(p)}`).join('. ')}.`
    case 4: return `Drawing: the closest products line up beside each piece; the pick for each is marked. ${j.picks.map((p) => `${p.kind}: ${p.colour ?? 'colour unknown'}`).join(', ')}.`
    default: return `Drawing: the ${j.picks.length} picks form one outfit: ${j.picks.map((p) => p.kind).join(', ')}.`
  }
}

export function JourneyCanvas({ step, journey, height = 320 }: { step: number; journey: Journey; height?: number }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const st = useRef({ shown: [] as Item[], from: [] as Item[], to: [] as Item[], t0: 0, raf: 0, visible: true, step: -1, w: 0 })

  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const s = st.current
    const ctx = cv.getContext('2d')
    if (!ctx) return
    const css = getComputedStyle(document.documentElement)
    const tone = (t: Tone) => (t === 'white' ? css.getPropertyValue('--white') : css.getPropertyValue(t === 'mag' ? '--mag' : `--${t}`)).trim() || '#000'

    const size = () => {
      const w = cv.clientWidth, dpr = window.devicePixelRatio || 1
      cv.width = Math.round(w * dpr); cv.height = Math.round(height * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      s.w = w
    }
    const paint = (items: Item[]) => {
      ctx.clearRect(0, 0, s.w, height)
      for (const it of items) {
        if (it.a <= 0.01) continue
        ctx.globalAlpha = Math.min(1, it.a)
        if (it.t === 'box') {
          if (it.fill) { ctx.fillStyle = tone(it.fill); ctx.fillRect(it.x, it.y, it.w, it.h) }
          if (it.stroke) { ctx.setLineDash(it.dash ? [2, 3] : []); ctx.lineWidth = 1.5; ctx.strokeStyle = tone(it.stroke); ctx.strokeRect(it.x + 0.75, it.y + 0.75, it.w - 1.5, it.h - 1.5) }
        } else if (it.t === 'line') {
          ctx.setLineDash(it.dash ? [3, 4] : []); ctx.lineWidth = 1.25; ctx.strokeStyle = tone(it.tone)
          ctx.beginPath(); ctx.moveTo(it.x, it.y); ctx.lineTo(it.x2, it.y2); ctx.stroke()
        } else {
          ctx.font = `${it.bold ? 700 : it.size > 15 ? 500 : 400} ${it.size}px ${SANS}`
          ctx.fillStyle = tone(it.tone)
          let txt = it.caps ? it.s.toUpperCase() : it.s
          if (it.max) while (txt.length > 2 && ctx.measureText(txt).width > it.max) txt = `${txt.slice(0, -2)}…`
          ctx.fillText(txt, it.x, it.y)
        }
      }
      ctx.globalAlpha = 1; ctx.setLineDash([])
    }
    /** The frame between two layouts: shared keys glide, new ones fade in, old ones fade out. */
    const mix = (from: Item[], to: Item[], t: number): Item[] => {
      const old = new Map(from.map((i) => [i.k, i]))
      const out: Item[] = []
      for (const b of to) {
        const a = old.get(b.k)
        if (!a || a.t !== b.t) { out.push({ ...b, a: b.a * t }); continue }
        old.delete(b.k)
        if (b.t === 'box' && a.t === 'box') out.push({ ...(t < 0.5 ? a : b), x: lerp(a.x, b.x, t), y: lerp(a.y, b.y, t), w: lerp(a.w, b.w, t), h: lerp(a.h, b.h, t), a: lerp(a.a, b.a, t) } as Item)
        else if (b.t === 'line' && a.t === 'line') out.push({ ...b, x: lerp(a.x, b.x, t), y: lerp(a.y, b.y, t), x2: lerp(a.x2, b.x2, t), y2: lerp(a.y2, b.y2, t), a: lerp(a.a, b.a, t) })
        else if (b.t === 'text' && a.t === 'text') out.push({ ...(t < 0.5 ? a : b), x: lerp(a.x, b.x, t), y: lerp(a.y, b.y, t), size: lerp(a.size, b.size, t), a: lerp(a.a, b.a, t) } as Item)
      }
      for (const a of old.values()) out.push({ ...a, a: a.a * (1 - t) })
      return out
    }
    const frame = (now: number) => {
      s.raf = 0
      const t = Math.min(1, (now - s.t0) / 700)
      s.shown = mix(s.from, s.to, ease(t))
      paint(s.shown)
      if (t < 1 && s.visible && !document.hidden) s.raf = requestAnimationFrame(frame)
      else if (t < 1) { s.shown = s.to; paint(s.to) }   // stopped part-way (off-screen or hidden): settle on the still frame
    }
    const go = (instant: boolean) => {
      cancelAnimationFrame(s.raf); s.raf = 0
      s.to = scene(step, journey, s.w, height, ctx)
      if (instant || calm() || !s.visible || document.hidden || s.shown.length === 0) { s.shown = s.to; paint(s.to); return }
      s.from = s.shown; s.t0 = performance.now()
      s.raf = requestAnimationFrame(frame)
    }

    size()
    go(s.step === -1)
    s.step = step

    const io = new IntersectionObserver(([e]) => { s.visible = e.isIntersecting; if (!s.visible) { cancelAnimationFrame(s.raf); s.raf = 0; s.shown = s.to; paint(s.to) } })
    io.observe(cv)
    const ro = new ResizeObserver(() => { if (Math.abs(cv.clientWidth - s.w) > 0.5) { size(); go(true) } })
    ro.observe(cv)
    const onVis = () => { if (document.hidden) { cancelAnimationFrame(s.raf); s.raf = 0; s.shown = s.to; paint(s.to) } }
    document.addEventListener('visibilitychange', onVis)
    // the fonts may arrive after the first frame: draw again once they are in
    document.fonts?.ready.then(() => { if (s.w) go(true) })
    return () => { cancelAnimationFrame(s.raf); s.raf = 0; io.disconnect(); ro.disconnect(); document.removeEventListener('visibilitychange', onVis) }
  }, [step, journey, height])

  const label = frameLabel(step, journey)
  return <canvas ref={ref} className="jr-canvas" style={{ height }} role="img" aria-label={label}>{label}</canvas>
}
