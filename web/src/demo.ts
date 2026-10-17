// The demo replay: a made-up run, emitted in the same event shape as the real server, so the same screen renders both.
// Every screen that shows it carries the DEMO DATA label. No number here is a result.
import type { FlatName } from './flats'
import type { Hit, OutfitItem, Plan, StageId, TraceEvent } from './trace'

export const DEMO_QUERY = 'a light linen outfit for a beach wedding in June'

export const C = { sand: '#D8C7A6', stone: '#C9C2B2', white: '#F4F2EC', sky: '#BCD3E0', navy: '#2E3A55', olive: '#77805A',
  jute: '#CDB58A', tan: '#A9744F', black: '#2A2A2C', straw: '#E0C989', brown: '#7A5135' }

const f = (shape: FlatName, fill: string, rank: number, score: number, title: string, n: number): Hit =>
  ({ id: `demo-${n}-${rank}`, source: 'demo', title, score, image: '', flat: { shape, fill } })

const PLAN: Plan = {
  main_query: 'light linen outfit for a beach wedding', gender: 'unknown', occasion: 'beach wedding', season: 'summer', budget_inr: null,
  pieces: [{ kind: 'top', search_text: 'linen shirt', colours: [] }, { kind: 'bottom', search_text: 'linen trousers', colours: [] },
           { kind: 'footwear', search_text: 'espadrilles', colours: [] }, { kind: 'accessory', search_text: 'straw hat', colours: [] }],
  already_has: [], notes: [],
}

const ROWS: { kind: string; text: string; hits: Hit[] }[] = [
  { kind: 'top', text: 'linen shirt', hits: [f('camp', C.sand, 1, 0.34, 'Camp-collar shirt, sand linen', 1), f('longsl', C.white, 2, 0.33, 'Linen shirt, white', 1), f('tee', C.white, 3, 0.31, 'Linen tee, white', 1), f('camp', C.sky, 4, 0.3, 'Camp-collar shirt, sky', 1), f('longsl', C.olive, 5, 0.29, 'Linen shirt, olive', 1), f('tee', C.navy, 6, 0.27, 'Tee, navy', 1)] },
  { kind: 'bottom', text: 'linen trousers', hits: [f('wide', C.stone, 1, 0.32, 'Wide trousers, stone linen', 2), f('chino', C.sand, 2, 0.31, 'Chinos, sand', 2), f('shorts', C.stone, 3, 0.3, 'Linen shorts, stone', 2), f('wide', C.white, 4, 0.29, 'Wide trousers, white', 2), f('chino', C.olive, 5, 0.27, 'Chinos, olive', 2), f('shorts', C.navy, 6, 0.25, 'Shorts, navy', 2)] },
  { kind: 'footwear', text: 'espadrilles', hits: [f('loafer', C.black, 1, 0.29, 'Loafer, black leather', 3), f('espa', C.jute, 2, 0.28, 'Espadrille, natural jute', 3), f('loafer', C.tan, 3, 0.27, 'Loafer, tan suede', 3), f('sandal', C.brown, 4, 0.26, 'Sandal, brown', 3), f('sneaker', C.white, 5, 0.24, 'Canvas sneaker, white', 3), f('espa', C.navy, 6, 0.23, 'Espadrille, navy', 3)] },
  { kind: 'accessory', text: 'straw hat', hits: [f('hat', C.straw, 1, 0.31, 'Straw hat', 4), f('bag', C.jute, 2, 0.29, 'Woven bag', 4), f('belt', C.tan, 3, 0.26, 'Belt, tan', 4), f('shades', C.black, 4, 0.25, 'Sunglasses', 4), f('bag', C.navy, 5, 0.22, 'Woven bag, navy', 4), f('belt', C.black, 6, 0.21, 'Belt, black', 4)] },
]

const PICK = [0, 0, 1, 0]
const WHY = ['Loose and light for June heat, and the collar still reads smart at a wedding.', 'Same fabric family as the shirt, one shade cooler.',
  'Chosen over the closer black loafer so the colours go together: hard black soles sink in sand.', 'Sun cover, added by the graph; texture without a new colour.']

const ITEMS: OutfitItem[] = ROWS.map((r, i) => ({ kind: r.kind, piece: r.text, pick: r.hits[PICK[i]], rank: PICK[i] + 1, reasons: [WHY[i]] }))

const SECONDS: Record<StageId, number> = { request: 0, understand: 1.8, expand: 0.3, search: 0.9, compose: 0.2, outfit: 0 }
const PAYLOAD: Record<StageId, Record<string, unknown>> = {
  request: { query: DEMO_QUERY },
  understand: { plan: PLAN, model: 'demo', demo: true },
  expand: { usages: ['Casual'], notes: ['graph: added accessory \'straw hat\' (beach context)'], pieces: PLAN.pieces },
  search: { backend: 'in-process', info: { encode_seconds: 0.1, catalogues: ['demo'] }, pieces: ROWS.map((r) => ({ ...r, seconds: 0.2 })) },
  compose: { harmony: { baseline: 0.95, coherent: 1.0 }, changed: 1, pieces: 4, colours: ['neutral', 'neutral', 'neutral', 'neutral'], picks: ITEMS.map((i) => i.pick.id) },
  outfit: { items: ITEMS, already_has: [], gender: 'unknown' },
}

/** Plays the made-up run as trace events, one step every 750 ms. Returns a function that stops it. */
export function playDemo(onEvent: (e: TraceEvent) => void, onDone: () => void): () => void {
  const order: StageId[] = ['request', 'understand', 'expand', 'search', 'compose', 'outfit']
  const timers: number[] = []
  order.forEach((stage, i) => {
    timers.push(window.setTimeout(() => onEvent({ kind: 'step', request_id: 'demo', stage, status: 'started', seconds: null, payload: {} }), i * 750))
    timers.push(window.setTimeout(() => onEvent({ kind: 'step', request_id: 'demo', stage, status: 'done', seconds: SECONDS[stage], payload: PAYLOAD[stage] }), i * 750 + 600))
  })
  timers.push(window.setTimeout(() => { onEvent({ kind: 'end', request_id: 'demo' }); onDone() }, order.length * 750))
  return () => timers.forEach((t) => window.clearTimeout(t))
}
