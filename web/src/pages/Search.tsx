// The Search page. Replay (the Viewer) is a short story in three chapters: the problem and the explainer replay (Hero), what we learned, your turn (the run picker).
// Try it live (the Lab): an empty request box with examples. Either way a run shows its result first (the outfit), then "How it got there"
// (six collapsible steps), then "Was each step worth it?" (plain search against the plan, and the folded cost table). The run log is a sticky rail on wide screens.
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { getExamples, getReady, pairedRunId, plainSearch, streamSearch, type Health, type Ready } from '../api'
import { describe, type BrainSetting } from '../brain'
import { HEADLINE } from '../brand'
import { ComposePanel, GraphSheet, LiveStrip, PlanCard, RecordTable, SearchPanel, TimeStrip, type Clock } from '../components/Panels'
import { CostPanel, type Resources } from '../components/CostPanel'
import { CompareCard, type Plain } from '../components/CompareCard'
import { Hero, Learned, SearchBoard, type BoardHit } from '../components/Hero'
import { FollowUp } from '../components/FollowUp'
import { LiveWhy } from '../components/Explain'
import { ContactSheet, Print, type Mode } from '../components/Sheet'
import { Sentence } from '../components/Sentence'
import { Stepper } from '../components/Stepper'
import { DEMO_QUERY, playDemo } from '../demo'
import { bestRun, HOSTED_PHOTO_IDS, PHOTO_BASE, playRecorded, RECORDED, VIEWER_ONLY, wakeHostedLab, withPhotos, type Pace, type RecordedRun } from '../recorded'
import {
  emptySteps, STEPS, type OutfitPayload, type PieceResult, type RequestPayload, type SearchPayload, type StageId, type StepState, type TraceEvent, type UnderstandPayload,
} from '../trace'
import { fmt, openModelDialog, scrollToId } from '../ui'

// "Search again, toward what you liked" only shows after a live run, so it loads then
const RefinePanel = lazy(() => import('../components/Refine').then((m) => ({ default: m.RefinePanel })))

type LiveSnapshot = {
  shown: string; retrievalQuery: string; steps: Record<StageId, StepState>; liked: Set<string>; plainLive: { q: string; value: Plain | null } | null
  resources: Resources | null; rid: string; t0: number | null; endAt: number | null; now: number; startedAt: Partial<Record<StageId, number>>; conversation: string[]; intent: IntentState
}

type IntentPart = { key: string; text: string }
type IntentState = { original: string; active: IntentPart[]; superseded: string[]; latest: string }

const MAX_QUERY_CHARS = 300
const colours = ['black', 'white', 'ivory', 'cream', 'beige', 'tan', 'khaki', 'camel', 'nude', 'brown', 'grey', 'gray', 'red', 'orange', 'yellow', 'green', 'blue', 'teal', 'turquoise', 'purple', 'pink', 'maroon', 'burgundy', 'lavender', 'violet', 'navy', 'olive', 'mustard', 'rust', 'gold', 'silver']
// Mirrors checks.py _KIND_WORDS; kept broad so updateIntent recognises garment changes in follow-up instructions.
// After retrievalText() normalises the user's text (sari→saree, t-shirt normalisation, etc.) these singular forms match well.
const garments = [
  // dresses / full garments
  'dress', 'gown', 'jumpsuit', 'saree', 'sari', 'lehenga', 'anarkali',
  // Indian tops
  'kurta', 'kurti',
  // western tops
  'shirt', 't-shirt', 'tee', 'top', 'blouse',
  // bottoms – western
  'skirt', 'trousers', 'pants', 'jeans', 'shorts', 'legging',
  // bottoms – Indian
  'churidar', 'salwar', 'palazzo', 'dhoti', 'pyjama', 'pajama',
  // outerwear
  'jacket', 'blazer', 'suit', 'cardigan', 'shrug', 'waistcoat', 'coat',
  // footwear
  'shoes', 'heels', 'sneakers', 'sandals', 'boots', 'loafers', 'slippers', 'flats', 'jutti', 'mojari',
]
const formality = ['casual', 'formal', 'smart casual', 'dressy', 'relaxed']

// Maps every garment word to its outfit-slot category, mirroring checks.py _KIND_WORDS.
// Active parts use "piece:<category>" keys so each outfit role is tracked independently,
// allowing "make the top green" to leave the bottom unchanged, and "add a coat" to be
// purely additive without touching an existing top or dress slot.
const garmentCategory: Record<string, string> = {
  dress: 'dress', gown: 'dress', jumpsuit: 'dress', saree: 'dress', sari: 'dress', lehenga: 'dress', anarkali: 'dress',
  kurta: 'top', kurti: 'top', shirt: 'top', top: 'top', blouse: 'top', tee: 'top',
  skirt: 'bottom', trousers: 'bottom', pants: 'bottom', jeans: 'bottom', shorts: 'bottom', legging: 'bottom',
  churidar: 'bottom', salwar: 'bottom', palazzo: 'bottom', dhoti: 'bottom', pyjama: 'bottom', pajama: 'bottom',
  jacket: 'outerwear', blazer: 'outerwear', suit: 'outerwear', cardigan: 'outerwear', shrug: 'outerwear', waistcoat: 'outerwear', coat: 'outerwear',
  shoes: 'footwear', heels: 'footwear', sneakers: 'footwear', sandals: 'footwear', boots: 'footwear',
  loafers: 'footwear', slippers: 'footwear', flats: 'footwear', jutti: 'footwear', mojari: 'footwear',
}

/** Every garment word that occupies a given outfit slot — used for same-category superseding. */
const garmentsInCategory = (cat: string): string[] => garments.filter((g) => garmentCategory[g] === cat)

const cleanText = (text: string) => text.replace(/\s+/g, ' ').replace(/\s+([,.;:])/g, '$1').trim()
// These are catalogue/search spellings, not inferred attributes; the visible conversation keeps the shopper's wording.
const retrievalText = (text: string) => cleanText(text.replace(/\bsaris?\b/gi, 'saree').replace(/\bt[ -]?shirts?\b/gi, 't-shirt').replace(/\btrousers?\b/gi, 'trousers'))
const hasWord = (text: string, word: string) => new RegExp(`\\b${word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'i').test(text)
const wordsIn = (text: string, words: string[]) => words.filter((word) => hasWord(text, word))
const removeText = (text: string, removed: string[]) => cleanText(removed.reduce((value, term) => term ? value.replace(new RegExp(`\\b${term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'gi'), ' ') : value, text))

/**
 * Update the intent state for one follow-up instruction.
 *
 * Active parts use typed slot keys:
 *   piece:<category>  – an outfit piece (top / bottom / dress / outerwear / footwear).
 *                       When the instruction names a colour alongside a garment, the colour
 *                       is embedded in the piece text ("green saree", "blue shirt").
 *   colour            – a global colour constraint when no specific piece is targeted.
 *   formality         – a formality modifier (casual, formal, …).
 *   modifier          – an unkeyed vibe instruction; replaces itself each turn to stay compact.
 *
 * Same-category rule: a new garment ALWAYS supersedes any earlier garment in the same outfit
 * slot — both in active and in the original query — regardless of whether the user said
 * "change" or "show me". This means "show me a saree" silently does not preserve a dress.
 * Cross-category instructions are additive by default: "add a coat" does not touch the top.
 *
 * Undo, stream-recovery, and the 300-char limit are unchanged; standaloneQuery is intact.
 */
const updateIntent = (intent: IntentState, instruction: string): IntentState => {
  const latest = cleanText(instruction)

  // ── Explicit removal: "without X" / "no X" / "not X" / "remove X" / "drop X" ────────
  const removal = latest.match(/^(?:without|no|not|remove|drop)\s+(?:the\s+)?(.+)$/i)
  if (removal?.[1]) {
    const removed = cleanText(removal[1])
    const active = intent.active.flatMap((part) => {
      const text = removeText(part.text, [removed, ...wordsIn(removed, colours), ...wordsIn(removed, garments), ...wordsIn(removed, formality)])
      return text ? [{ ...part, text }] : []
    })
    return { original: intent.original, active, superseded: [...new Set([...intent.superseded, removed].filter(Boolean))], latest }
  }

  // ── Parse structured patterns ────────────────────────────────────────────────────────
  // "change X to Y" / "switch X to Y" / "replace X with Y"
  const replacement = latest.match(/^(?:change|switch|replace)\s+(?:the\s+)?(.+?)\s+(?:to|for|with)\s+(.+)$/i)
  // "blue instead of green" colour shorthand
  const colourSwap = latest.match(new RegExp(`\\b(${colours.join('|')})\\b\\s+instead of\\s+(?:the\\s+)?(${colours.join('|')})\\b`, 'i'))

  const oldText  = replacement?.[1] ? cleanText(replacement[1]) : colourSwap?.[2] ?? ''
  const newText  = replacement?.[2] ? cleanText(replacement[2]) : colourSwap?.[1] ?? latest
  const newColours   = wordsIn(newText, colours)
  const newGarments  = wordsIn(newText, garments)
  const newFormality = wordsIn(newText, formality)
  // Garment explicitly named as the OLD item ("replace the jeans with a saree" → 'jeans')
  const oldGarment = wordsIn(oldText, garments)[0]

  let nextActive = [...intent.active]
  const sup = new Set<string>(intent.superseded)   // accumulates; Set deduplicates automatically

  // ── Group new garments by outfit-slot category ───────────────────────────────────────
  const slotMap = new Map<string, string[]>()   // category → garment words in this instruction
  for (const g of newGarments) {
    const cat = garmentCategory[g]
    if (cat) { const a = slotMap.get(cat) ?? []; a.push(g); slotMap.set(cat, a) }
  }

  // ── Retire the explicitly named old item's slot ──────────────────────────────────────
  // Handles cross-category replacement ("replace the jeans with a saree"):
  // the bottom slot is retired even though the saree occupies the dress slot.
  if (oldGarment) {
    const oldCat = garmentCategory[oldGarment]
    if (oldCat) {
      const existSlot = nextActive.find((p) => p.key === `piece:${oldCat}`)
      if (existSlot) { sup.add(existSlot.text); nextActive = nextActive.filter((p) => p.key !== `piece:${oldCat}`) }
      for (const g of wordsIn(intent.original, garmentsInCategory(oldCat))) sup.add(g)
      for (const c of wordsIn(oldText, colours)) sup.add(c)
    }
  }

  // ── Process each garment slot ────────────────────────────────────────────────────────
  if (slotMap.size > 0) {
    // Retire the global colour key when this instruction embeds a colour in the piece text
    if (newColours.length > 0) {
      const existColour = nextActive.find((p) => p.key === 'colour')
      if (existColour) { sup.add(existColour.text); nextActive = nextActive.filter((p) => p.key !== 'colour') }
    }

    for (const [cat, catGarments] of slotMap) {
      // Same-category rule: retire any earlier same-slot active part
      const existSlot = nextActive.find((p) => p.key === `piece:${cat}`)
      if (existSlot) { sup.add(existSlot.text); nextActive = nextActive.filter((p) => p.key !== `piece:${cat}`) }
      // Same-category rule: retire same-slot garment words from the original query
      for (const g of wordsIn(intent.original, garmentsInCategory(cat))) sup.add(g)
      // Supersede the original's colour only when it unambiguously belonged to this slot:
      // original has exactly one garment AND that garment is the same category as the new piece
      if (newColours.length > 0) {
        const origGarments = garments.filter((g) => hasWord(intent.original, g))
        if (origGarments.length === 1 && garmentCategory[origGarments[0]] === cat) {
          for (const c of wordsIn(intent.original, colours)) sup.add(c)
        } else {
          // Multi-garment original: only retire colours explicitly named in the old reference
          for (const c of wordsIn(oldText, colours)) sup.add(c)
        }
      }
      // Compose: embed colour(s) with garment in a single piece search phrase
      nextActive.push({ key: `piece:${cat}`, text: cleanText([...newColours, ...catGarments].join(' ')) })
    }

  // ── Colour-only change (no garment named in this instruction) ────────────────────────
  } else if (newColours.length > 0) {
    // Retire the global colour key regardless of which path handles the colour
    const existColour = nextActive.find((p) => p.key === 'colour')
    if (existColour) { sup.add(existColour.text); nextActive = nextActive.filter((p) => p.key !== 'colour') }

    const activePieces = nextActive.filter((p) => p.key.startsWith('piece:'))

    if (oldGarment && garmentCategory[oldGarment]) {
      // Attribute change on an explicitly named piece ("change the top colour to blue", "make the dress green")
      const tgt = garmentCategory[oldGarment]!
      const existSlot = nextActive.find((p) => p.key === `piece:${tgt}`)
      if (existSlot) {
        // Replace the embedded colour inside the existing piece text
        const oldEmbedded = wordsIn(existSlot.text, colours)
        for (const c of oldEmbedded) sup.add(c)
        nextActive = nextActive.filter((p) => p.key !== `piece:${tgt}`)
        nextActive.push({ key: `piece:${tgt}`, text: cleanText(`${newColours.join(' ')} ${removeText(existSlot.text, oldEmbedded)}`) })
      } else {
        // Piece not yet in active; create it from the named garment + new colour
        nextActive.push({ key: `piece:${tgt}`, text: cleanText(`${newColours.join(' ')} ${oldGarment}`) })
        for (const g of wordsIn(intent.original, garmentsInCategory(tgt))) sup.add(g)
      }
      for (const c of wordsIn(oldText, colours)) sup.add(c)

    } else if (activePieces.length === 1) {
      // Unambiguous: update the single active piece's embedded colour
      const [p] = activePieces
      const oldEmbedded = wordsIn(p.text, colours)
      for (const c of oldEmbedded) sup.add(c)
      for (const c of wordsIn(intent.original, colours)) sup.add(c)
      nextActive = nextActive.filter((x) => x.key !== p.key)
      nextActive.push({ key: p.key, text: cleanText(`${newColours.join(' ')} ${removeText(p.text, oldEmbedded)}`) })

    } else {
      // Multiple active pieces or no active pieces: apply as a global colour constraint
      for (const c of wordsIn(intent.original, colours)) sup.add(c)
      nextActive.push({ key: 'colour', text: newColours.join(' ') })
    }
  }

  // ── Formality change ─────────────────────────────────────────────────────────────────
  if (newFormality.length > 0) {
    const existFmt = nextActive.find((p) => p.key === 'formality')
    if (existFmt) { sup.add(existFmt.text); nextActive = nextActive.filter((p) => p.key !== 'formality') }
    for (const f of wordsIn(intent.original, formality)) sup.add(f)
    nextActive.push({ key: 'formality', text: newFormality.join(' ') })
  }

  // ── Unkeyed modifier: replaces itself each turn to keep the query compact ─────────────
  if (newColours.length === 0 && slotMap.size === 0 && newFormality.length === 0) {
    nextActive = nextActive.filter((p) => p.key !== 'modifier')
    nextActive.push({ key: 'modifier', text: latest })
  }

  return { original: intent.original, active: nextActive, superseded: [...sup].filter(Boolean), latest }
}

/** Build a standalone query from the current intent. Concatenates the original (minus
 *  superseded terms) with each active part's text. Returns null when the result would
 *  exceed the 300-character backend limit rather than silently truncating a constraint. */
const standaloneQuery = (intent: IntentState): string | null => {
  const query = cleanText([removeText(intent.original, intent.superseded), ...intent.active.map((part) => part.text)].filter(Boolean).join('; '))
  return query && query.length <= MAX_QUERY_CHARS ? query : null
}

/** Move focus to the result's heading without a scroll jump (the page scrolls there on its own), so keyboard and screen reader users land on the outfit. */
const focusResult = () => window.setTimeout(() => document.getElementById('result-h')?.focus({ preventScroll: true }), 140)

const dismissed = new Set<string>()   // notes a visitor closed: kept while the page is open, so changing page does not bring them back
/** The tape-coloured note, with a way out: a 44px close button. */
function Notice({ id, style, children }: { id: string; style?: React.CSSProperties; children: React.ReactNode }) {
  const [, again] = useState(0)
  if (dismissed.has(id)) return null
  return (
    <div className="notice" style={style}>
      {children}
      <button type="button" className="notice-x" aria-label="Dismiss this note" onClick={() => { dismissed.add(id); again((n) => n + 1) }}>
        <svg aria-hidden="true" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M2 2l10 10M12 2L2 12" /></svg>
      </button>
    </div>
  )
}

export function SearchPage({ health, viewer, brain }: { health: Health | null | undefined; viewer: boolean; brain: BrainSetting }) {
  const [query, setQuery] = useState('')
  const [shown, setShown] = useState('')
  const [retrievalQuery, setRetrievalQuery] = useState('')
  const [conversation, setConversation] = useState<string[]>([])
  const [intent, setIntent] = useState<IntentState>({ original: '', active: [], superseded: [], latest: '' })
  const [history, setHistory] = useState<LiveSnapshot[]>([])
  const [mode, setMode] = useState<Mode>('idle')
  const [steps, setSteps] = useState<Record<StageId, StepState>>(emptySteps)
  const [running, setRunning] = useState(false)
  const [hint, setHint] = useState(false)          // an empty search was pressed: show what to write
  const [liked, setLiked] = useState<Set<string>>(new Set())   // products the visitor liked in a live run; forgotten with the next run
  const [photoWait, setPhotoWait] = useState(false)     // the Viewer asked the hosted Lab for photos and none has arrived yet
  const [error, setError] = useState<string | null>(null)
  const [announce, setAnnounce] = useState('')
  const [rid, setRid] = useState('')
  const [t0, setT0] = useState<number | null>(null)       // the stopwatch: starts when a run starts, ticks while it runs, stops at its end
  const [endAt, setEndAt] = useState<number | null>(null)
  const [now, setNow] = useState(0)
  const [startedAt, setStartedAt] = useState<Partial<Record<StageId, number>>>({})
  useEffect(() => {
    if (!running) return
    const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches   // a stopwatch is motion: once a second for people who asked for less
    const t = window.setInterval(() => setNow(performance.now()), calm ? 1000 : 100)
    return () => window.clearInterval(t)
  }, [running])
  const [examples, setExamples] = useState<string[]>([])
  const [pace, setPace] = useState<Pace>('recorded')
  const [picked_run, setPickedRun] = useState<RecordedRun | null>(null)
  const [ready, setReady] = useState<Ready | null>(null)      // what the server is still loading (GET /api/ready); null: not asked or no answer
  const stop = useRef<(() => void) | null>(null)
  const paired = useRef('')                                   // one id for a live search and its paired plain search
  const activeRun = useRef(0)                                 // ignores a late event from a stopped or superseded stream

  useEffect(() => { if (health) getExamples().then(setExamples) }, [health])
  // the Lab asks the server whether it is still loading, every 2 s until it is ready: no guessing "the first search loads it"
  useEffect(() => {
    if (!health || viewer) return
    let alive = true
    let t = 0
    const ask = () => getReady().then((r) => { if (!alive) return; setReady(r); if (r && !r.ready) t = window.setTimeout(ask, 2000) })
    ask()
    return () => { alive = false; window.clearTimeout(t) }
  }, [health, viewer])
  const photos = useRef<Record<string, string>>({})
  const [plainLive, setPlainLive] = useState<{ q: string; value: Plain | null } | null>(null)   // plain search of the same sentence, for the comparison
  const [resources, setResources] = useState<Resources | null>(null)   // what this computer is holding in memory, read after a live run
  const [photosReady, setPhotosReady] = useState(false)
  // the explainer's runs, made once: the best one (all its photos showable) first, then the rest in their recorded order
  const heroRuns = useMemo(() => {
    if (!viewer || !photosReady) return []
    const first = bestRun()
    return [first, ...RECORDED.runs.filter((r) => r.id !== first.id)].map((r) => withPhotos(r, photos.current))
  }, [viewer, photosReady])
  // a Viewer (the public build, or ?mode=viewer) asks no server of its own; Marqo photos come from the hosted Lab when its address is set.
  // Only a computer that has the photos answers /api/recorded-photos.
  useEffect(() => {
    if (VIEWER_ONLY) { photos.current = HOSTED_PHOTO_IDS; setPhotosReady(true); return }
    fetch('/api/recorded-photos').then((r) => (r.ok ? r.json() : {})).then((m) => { photos.current = m }).catch(() => {}).finally(() => setPhotosReady(true))
  }, [])
  useEffect(() => {
    if (!photoWait) return
    const done = () => setPhotoWait(false)
    window.addEventListener('genkart-photo', done, { once: true })
    const t = window.setTimeout(done, 90000)       // never stay up for ever: after 90 s the tiles are sketches and that is that
    return () => { window.removeEventListener('genkart-photo', done); window.clearTimeout(t) }
  }, [photoWait])
  const auto = useRef(false)
  // on a real unmount (and on React's development-mode test unmount) stop the replay and allow a link-started run to start again
  useEffect(() => () => { stop.current?.(); auto.current = false }, [])

  // a link can start a run: ?demo=1 plays the demo replay, ?run=<id> a recorded run, ?q=some+request runs that request (sent as a POST) once the server answers
  useEffect(() => {
    if (auto.current || health === undefined || !photosReady) return
    const params = new URLSearchParams(window.location.search)
    const wanted = RECORDED.runs.find((r) => r.id === params.get('run'))
    if (params.has('demo')) { auto.current = true; runDemo() }
    else if (wanted && viewer) { auto.current = true; runRecorded(wanted) }
    else if (params.get('q') && health && !viewer) { auto.current = true; setQuery(params.get('q')!); runLive(params.get('q')!) }
    // a link starts its run once: drop ?demo / ?run / ?q from the address (the #/route stays), so coming back to Search does not start it again
    if (auto.current && (params.has('demo') || params.has('run') || params.has('q'))) {
      for (const k of ['demo', 'run', 'q']) params.delete(k)
      const rest = params.toString()
      window.history.replaceState(window.history.state, '', `${window.location.pathname}${rest ? `?${rest}` : ''}${window.location.hash}`)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [health, photosReady])

  useEffect(() => {
    if (mode !== 'live' || running || steps.request.status === 'waiting') return
    const run = activeRun.current
    if (!health?.hosted) fetch('/api/resources').then((r) => (r.ok ? r.json() : null)).then((v) => { if (run === activeRun.current) setResources(v) }).catch(() => { if (run === activeRun.current) setResources(null) })
    if (steps.request.status === 'done') {
      const asked = retrievalQuery
      const pair = paired.current
      plainSearch(asked, pair).then((v) => { if (run === activeRun.current && pair === paired.current) setPlainLive({ q: asked, value: v }) })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, running])

  const apply = (e: TraceEvent, run?: number) => {
    if (run !== undefined && run !== activeRun.current) return
    setRid(e.request_id)
    if (e.kind === 'end') { setEndAt(performance.now()); setRunning(false); return }
    if (e.status === 'started') setStartedAt((s) => ({ ...s, [e.stage]: performance.now() }))
    setSteps((s) => ({ ...s, [e.stage]: { status: e.status, seconds: e.seconds, payload: e.payload } }))
    const name = STEPS.find((s) => s.id === e.stage)?.name
    if (e.status === 'done') setAnnounce(e.seconds != null && e.seconds > 0 ? `${name} finished in ${fmt(e.seconds, 2)} seconds` : `${name} finished`)
    if (e.status === 'failed') setAnnounce(`${name} failed`)
  }

  // Stop and Skip unmount themselves (they show only while a run is running): if one held focus, focus goes to the result heading, not to the page top
  const keepFocus = () => { const a = document.activeElement; if (a instanceof HTMLElement && a.closest('.run-controls, .live-strip, .why-live')) focusResult() }
  const stopRun = () => { keepFocus(); activeRun.current += 1; stop.current?.(); stop.current = null; setRunning(false); setEndAt(performance.now()) }   // a way out of any run, however long it is taking
  const skipToResult = () => {                                                                  // a replay at its recorded pace takes seconds: show the end now
    if (!picked_run) return
    keepFocus()
    stop.current?.()
    const run = activeRun.current
    withPhotos(picked_run, photos.current).events.forEach((e) => apply(e, run))
  }

  const start = (m: Mode, q: string, display = q) => {
    stop.current?.()
    const run = ++activeRun.current
    const t = performance.now()
    // the result (the outfit) is the scroll target, not step 1
    window.setTimeout(() => scrollToId('result'), 120)
    setPlainLive(null); setLiked(new Set())
    setMode(m); setShown(display); setRetrievalQuery(q); setSteps(emptySteps()); setRunning(true); setError(null); setT0(t); setNow(t); setEndAt(null); setStartedAt({})
    return run
  }
  const runLive = (q: string) => {
    if (!q.trim()) { setHint(true); document.getElementById('req')?.focus(); return }      // nothing typed: say what to write, send nothing
    setHint(false)
    if (!health) { setError('The server is not running, so nothing was searched. Start it, or watch a recorded run.'); return }
    const original = cleanText(q)
    const retrieval = retrievalText(original)
    if (retrieval.length > MAX_QUERY_CHARS) { setError(`Searches can be at most ${MAX_QUERY_CHARS} characters. Shorten this request without dropping a needed constraint.`); return }
    const nextIntent: IntentState = { original: retrieval, active: [], superseded: [], latest: retrieval }
    setConversation([q.trim()]); setIntent(nextIntent); setHistory([])
    paired.current = pairedRunId()       // made before start(): if it threw after, the page would show a run that never began
    const run = start('live', retrieval, original)
    stop.current = streamSearch(retrieval, (e) => apply(e, run), (msg) => { if (run === activeRun.current) { setError(msg); setRunning(false); setEndAt(performance.now()) } }, brain, paired.current)
  }
  const restore = (snapshot: LiveSnapshot) => {
    setShown(snapshot.shown); setRetrievalQuery(snapshot.retrievalQuery); setSteps(snapshot.steps); setLiked(snapshot.liked); setPlainLive(snapshot.plainLive)
    setResources(snapshot.resources); setRid(snapshot.rid); setT0(snapshot.t0); setEndAt(snapshot.endAt); setNow(snapshot.now); setStartedAt(snapshot.startedAt); setConversation(snapshot.conversation); setIntent(snapshot.intent); setMode('live'); setRunning(false)
  }
  const followUp = (turn: string) => {
    if (running || !conversation.length) return
    const nextIntent = updateIntent(intent, retrievalText(turn))
    const nextQuery = standaloneQuery(nextIntent)
    if (!nextQuery) { setError(`This refinement cannot fit within the ${MAX_QUERY_CHARS}-character search limit without dropping a constraint.`); return }
    const snapshot: LiveSnapshot = { shown, retrievalQuery, steps, liked, plainLive, resources, rid, t0, endAt, now, startedAt, conversation, intent }
    setHistory((all) => [...all, snapshot]); setConversation((all) => [...all, turn.trim()]); setIntent(nextIntent)
    paired.current = pairedRunId()
    const run = start('live', nextQuery, turn)
    stop.current = streamSearch(nextQuery, (e) => apply(e, run), (msg) => { if (run === activeRun.current) { restore(snapshot); setError(msg); setEndAt(performance.now()) } }, brain, paired.current)
  }
  const undoFollowUp = () => {
    const snapshot = history.at(-1)
    if (!snapshot || running) return
    stop.current?.(); stop.current = null
    setHistory((all) => all.slice(0, -1)); restore(snapshot); setError(null)
  }
  const runRecorded = (run: RecordedRun) => {
    setPickedRun(run)
    if (wakeHostedLab()) setPhotoWait(true)
    const runId = start('recorded', run.prompt)
    focusResult()
    stop.current = playRecorded(withPhotos(run, photos.current), pace, (e) => apply(e, runId), () => { if (runId === activeRun.current) setRunning(false) })
  }
  const runDemo = () => {
    const run = start('demo', DEMO_QUERY)
    stop.current = playDemo((e) => apply(e, run), () => { if (run === activeRun.current) setRunning(false) })
  }

  const clock: Clock = { t0, endAt: endAt ?? (running ? null : now || null), now, startedAt }
  const demo = mode === 'demo'
  const live = mode === 'live'
  const recorded = mode === 'recorded'
  const under = steps.understand.status === 'done' || steps.understand.status === 'failed' ? (steps.understand.payload as unknown as UnderstandPayload) : null
  const search = steps.search.status === 'done' ? (steps.search.payload as unknown as SearchPayload) : null
  const outfit = steps.outfit.status === 'done' ? (steps.outfit.payload as OutfitPayload) : null
  const items = outfit?.items ?? []
  const picked = new Set<string>(items.map((i) => i.pick.id))
  const plan = under && !under.fell_back ? under.plan : null
  const req = steps.request.payload as RequestPayload
  const refused = steps.request.status === 'failed' && req.refused === true
  const finished = !running && mode !== 'idle'
  const hasFollowUp = live && ((finished && !!search && !refused) || history.length > 0)
  const examplesShown = examples.length ? examples : RECORDED.runs.map((r) => r.prompt)
  const hosted = !!health?.hosted
  const reader = hosted && brain.kind === 'local' ? 'no AI here, so your words are searched as typed' : describe(brain)
  // The first-screen board is a real recorded contact sheet until this search has returned its own candidates.
  const recordedSearch = withPhotos(RECORDED.runs.find((r) => r.id === 't5-p17') ?? bestRun(), photos.current).events.find((e): e is Extract<TraceEvent, { kind: 'step' }> => e.kind === 'step' && e.stage === 'search' && e.status === 'done')
  const recordedPieces = recordedSearch?.payload as unknown as { pieces?: PieceResult[] } | undefined
  const boardHits: BoardHit[] = (search?.pieces ?? recordedPieces?.pieces ?? []).flatMap((piece) => piece.hits.map((hit) => ({ hit, kind: piece.kind }))).slice(0, 4)

  const detail: Partial<Record<StageId, React.ReactNode>> = {
    understand: <><Sentence text={shown} plan={plan} animate={steps.understand.status === 'done'} /><PlanCard step={steps.understand} demo={demo} head={false} /></>,
    expand: <GraphSheet step={steps.expand} head={false} />,
    search: <>
      <SearchPanel step={steps.search} head={false} />
      {search && search.pieces.length > 0 && <ContactSheet inStep pieces={search.pieces} picked={picked} mode={mode} liked={liked}
        onLike={live && !running ? (id) => setLiked((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n }) : undefined} />}
    </>,
    compose: <ComposePanel step={steps.compose} head={false} />,
  }

  return (
    <main id="main" tabIndex={-1} className={`wrap search-page${hasFollowUp ? ' has-follow-up' : ''}`}>
      {mode !== 'idle' && <LiveStrip steps={steps} mode={mode} clock={clock} running={running} onStop={stopRun} />}
      <p className="sr-only" aria-live="polite">{announce}</p>

      {viewer ? (<>
        <Hero runs={heroRuns} onWatch={(r) => runRecorded(RECORDED.runs.find((x) => x.id === r.id) ?? r)} />
        <Learned />
        <section className="picker chapter" aria-labelledby="picker-h">
          <h2 id="picker-h" className="sec-h">Your turn</h2>
          <p className="sec-lead">Pick a real request and watch it step by step. Recorded on {RECORDED.recorded_at}, replayed.</p>
          <div className="run-list">
            {RECORDED.runs.map((r) => (
              <button key={r.id} type="button" className="run-item" aria-pressed={picked_run?.id === r.id && mode === 'recorded'} onClick={() => runRecorded(r)}>
                <span className="run-prompt">{r.prompt}</span>
                <span className="mono dim run-sec">{r.wall_seconds.toFixed(1)} s</span>
              </button>
            ))}
          </div>
          {photoWait && <p className="lg dim" role="status" style={{ marginTop: 14 }}>Fetching photos from the sleeping hosted Lab. Sketches show until they arrive.</p>}
          <details className="fold picker-more">
            <summary>Replay speed{PHOTO_BASE ? '' : ' and photos'}</summary>
            <div className="fold-body">
              <div className="chip-row" role="group" aria-label="Replay speed">
                <span className="lg dim" style={{ marginRight: 4 }}>Replay at</span>
                <button type="button" className="chip" aria-pressed={pace === 'recorded'} onClick={() => setPace('recorded')}>the recorded pace</button>
                <button type="button" className="chip" aria-pressed={pace === 'fast'} onClick={() => setPace('fast')}>fast</button>
              </div>
              {!PHOTO_BASE && <p className="dim" style={{ margin: '12px 0 0', fontSize: 16 }}>No photo host is linked to this copy, so products show as labelled frames.</p>}
            </div>
          </details>
          <p className="picker-live">
            {health ? <>Your own words? Choose <strong>Try it live</strong> at the top.</>
              : PHOTO_BASE ? <>Your own words? <a href="#/wake">Try it live</a> wakes a server in about 45 s.</>
              : <>Your own words? Try it live needs the server running: <a href="#/docs">see How it works</a>.</>}
          </p>
        </section>
      </>) : (
        <section className="lab-hero" aria-labelledby="lab-h">
          <div className="lab-top">
            <h1 id="lab-h" className="voice lab-h">{HEADLINE}</h1>
            {hosted && brain.kind === 'local' && (
              <Notice id="hosted"><span className="lg">Hosted Lab</span><span className="notice-text">This Lab has no AI model of its own. Add your own key under AI model.</span></Notice>
            )}
            {health && !hosted && !health.ollama && (
              <Notice id="ollama"><span className="lg">Ollama off</span><span className="notice-text">Start Ollama with <code>qwen3:4b-instruct</code>. Until then your words are searched as typed.</span></Notice>
            )}
            <form className="req" onSubmit={(e) => { e.preventDefault(); if (running && live) stopRun(); else runLive(query) }}>
              <label htmlFor="req" className="lg dim" style={{ width: '100%', marginBottom: 4 }}>What do you need to wear?</label>
              <p id="req-help" className="req-help">Name the occasion, a garment, a colour, the season, or a piece you own. Up to 300 characters.</p>
              <input id="req" type="text" value={query} maxLength={300} onChange={(e) => { setQuery(e.target.value); setHint(false) }} autoComplete="off"
                placeholder="A men's outfit for Diwali with a black kurta and ivory trousers" aria-describedby={hint ? 'req-help req-hint' : 'req-help'} aria-invalid={hint || undefined} />
              <button type="submit" className="btn-expose">{running && live ? 'Stop' : 'Search outfit'}</button>
              {hint && <p id="req-hint" role="alert" className="req-hint"><span className="tile cross" aria-hidden="true" />Write one sentence first, for example the occasion and the garment. Nothing was searched.</p>}
            </form>
            <div className="chip-row" style={{ marginTop: 14 }} role="group" aria-labelledby="ex-h">
              <span id="ex-h" className="lg dim" style={{ marginRight: 4 }}>Examples: tap to fill, then edit</span>
              {examplesShown.map((s) => <button key={s} type="button" className="chip" onClick={() => { setQuery(s); setHint(false); document.getElementById('req')?.focus() }}>{s}</button>)}
              <button type="button" className="chip" style={{ borderStyle: 'dashed' }} onClick={runDemo}>Play the demo replay</button>
            </div>
            {health && (
              <p className="lab-status">
                <span className="lg dim">Reads your words with</span> {reader}
                {' · '}<button type="button" className="text-btn" onClick={openModelDialog}>change</button>
                {ready && !ready.ready && <><br /><span className="lg dim">Still loading</span> {ready.loading.join(', ') || 'the search model'} · <span className="mono">{ready.seconds.toFixed(0)} s</span> so far. Searches wait until it is done.</>}
              </p>
            )}
          </div>
          <SearchBoard hits={boardHits} live={live && !!search} />
        </section>
      )}

      {mode === 'live' && running && <LiveWhy steps={steps} startedAt={startedAt} now={now} who={describe(brain)} onStop={stopRun} />}
      {running && !live && (
        <div className="run-controls" role="group" aria-label="Control this run">
          <button type="button" className="btn-line" onClick={stopRun}>Stop</button>
          {recorded && <button type="button" className="btn-line" onClick={skipToResult}>Skip to the result</button>}
        </div>
      )}
      {error && <p role="alert" className="err-line"><span className="tile cross" aria-hidden="true" />{error}</p>}

      {mode !== 'idle' && (
        <div className="results">
          <aside className="rail" aria-label="Run log">
            <RecordTable steps={steps} mode={mode} rid={rid} clock={clock} />
          </aside>
          <div className="results-main">
            {demo && (
              <Notice id="demo"><span className="lg">Demo data</span><span className="notice-text">A made-up replay, drawn as sketches. No number here is a result.</span></Notice>
            )}
            <section id="result" aria-labelledby="result-h" className="result">
              <p className="lg dim layer-label">What a shopper sees</p>
              <h2 id="result-h" tabIndex={-1} className="sec-h">Your outfit{demo ? ' (demo)' : recorded ? ' (recorded)' : ''}</h2>
              <p className="voice result-q">“{shown}”</p>
              {recorded && picked_run && (
                <p className="dim result-note">Recorded on {RECORDED.where} with <span className="mono">{RECORDED.understand_model}</span>. The author's blind score ({picked_run.author_rating_of_raw_search ?? 'none'}) rates plain search of this request, not this outfit.</p>
              )}
              {refused ? (
                <div role="alert" className="notice" style={{ marginTop: 18, transform: 'none' }}>
                  <span className="lg">Not searched</span><span className="notice-text">{req.message}</span>
                  <span className="mono" style={{ display: 'block', marginTop: 6, fontSize: 13 }}>reason: {req.category}</span>
                </div>
              ) : items.length > 0 ? (
                <>
                  <Print items={items} alreadyHas={outfit?.already_has ?? []} mode={mode} />
                  {/* Surface any gender-inference note from the search step so users understand
                      why they received women's or men's products when no gender was stated. */}
                  {live && (() => {
                    const genderNote = search?.checks?.find((c) => c.includes('kept to') && c.includes("'s products"))
                    return genderNote ? (
                      <p className="lg dim" style={{ marginTop: 10 }} role="status">{genderNote}</p>
                    ) : null
                  })()}</>
              ) : steps.outfit.status === 'skipped' ? (
                <>
                  <p className="err-line"><span className="tile not_built" aria-hidden="true" />No outfit could be built: {(steps.outfit.payload as OutfitPayload).reason}.</p>
                  {search?.checks && search.checks.length > 0 && (
                    <div className="checks-note" role="note" aria-label="Why the outfit could not be built">
                      <strong>Why no outfit was built</strong> — these checks on the search results explain the gap:
                      <ul>{search.checks.map((c, i) => <li key={i}>{c}</li>)}</ul>
                      <p style={{ margin: '8px 0 0', color: 'var(--z4)', fontSize: 15 }}>
                        If the item you requested is not in the catalogue under that name, try a broader term — for example "ethnic dress" instead of a specific garment name — or use the Follow Up box below to refine.
                      </p>
                    </div>
                  )}
                </>
              ) : (
                <div className="result-wait"><span className={`tile ${running ? 'hatch started' : 'waiting'}`} aria-hidden="true" />{running ? 'Your outfit appears here when the six steps finish.' : 'This run stopped before an outfit was picked.'}</div>
              )}
              {!refused && req.note && <p className="lg dim" style={{ marginTop: 14 }}>{req.note}</p>}
              {/* When the AI reading step was unavailable the whole sentence was searched as typed,
                  which may miss garments the user named explicitly. Show this only for live runs. */}
              {live && under?.fell_back && !refused && (
                <p className="lg dim" style={{ marginTop: 12 }} role="status">
                  The AI reading step was unavailable — your words were searched as typed.
                  {' '}If you asked for multiple garments, some may be missing.
                  {hasFollowUp && ' Use the Follow Up box below to add a missing piece.'}
                </p>
              )}
            </section>

            {!refused && (
              <Stepper steps={steps} detail={detail} demo={demo} after={
                <details className="fold">
                  <summary>Timing: where the seconds went</summary>
                  <div className="fold-body"><TimeStrip steps={steps} mode={mode} clock={clock} /></div>
                </details>
              } />
            )}

            {(live || recorded) && finished && items.length > 0 && (
              <section className="worth" aria-labelledby="worth-h">
                <h2 id="worth-h" className="sec-h">Was each step worth it?</h2>
                <CompareCard
                  plain={recorded ? withPhotos(picked_run!, photos.current).plain ?? null : plainLive && plainLive.q === retrievalQuery ? plainLive.value : 'loading'}
                  outfit={items} planSeconds={STEPS.reduce((n, s) => n + (steps[s.id].status === 'done' ? steps[s.id].seconds ?? 0 : 0), 0)}
                  ratings={recorded && picked_run ? { plain: picked_run.author_rating_of_raw_search, plan: picked_run.author_rating_of_plan } : undefined} />
                {steps.search.status === 'done' && (live || RECORDED.resources) && (
                  <details className="fold">
                    <summary>What this run cost: time, memory and money</summary>
                    <div className="fold-body"><CostPanel steps={steps} mode={live ? 'live' : 'recorded'} brain={brain} live={resources} recorded={RECORDED.resources} /></div>
                  </details>
                )}
              </section>
            )}
            {live && finished && search && search.pieces.length > 0 && (
              <Suspense fallback={null}><RefinePanel query={retrievalQuery} liked={liked} gender={plan?.gender ?? null} /></Suspense>
            )}
          </div>
        </div>
      )}

      {hasFollowUp && <FollowUp busy={running} canUndo={history.length > 0} onFollow={followUp} onUndo={undoFollowUp} />}

    </main>
  )
}
