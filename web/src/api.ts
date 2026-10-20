// The page's calls to the server: health and readiness, example prompts, the live step stream (a POST read as server-sent events), plain search.
import { providerOf, toBody, type BrainSetting } from './brain'
import type { Hit, TraceEvent } from './trace'

export type RouterHealth = { ok: boolean; encoder: boolean; shards: boolean[]; replicas: boolean[][] }
export type Health = {
  ok: boolean
  byo?: boolean            // this server can use the visitor's own model key
  study?: boolean          // the consented study is running on this server
  hosted?: boolean         // a public host: no built-in model, Marqo catalogue only (the visitor's own key is the only way to read the sentence)
  ollama: boolean
  router: RouterHealth | null
  backend: 'router' | 'in-process'
  catalogue_loaded: boolean
  graph_ready: boolean
}

export async function getHealth(): Promise<Health | null> {
  try {
    const r = await fetch('/api/health', { signal: AbortSignal.timeout(5000), cache: 'no-store' })
    return r.ok ? await r.json() : null
  } catch {
    return null
  }
}

export async function getExamples(): Promise<string[]> {
  try {
    const r = await fetch('/api/examples')
    return r.ok ? (await r.json()).examples : []
  } catch {
    return []
  }
}

/** What the server is still loading (GET /api/ready answers 503 until the search model and catalogues are in memory). null: no answer. */
export type Ready = { ready: boolean; loading: string[]; seconds: number }
export async function getReady(base = ''): Promise<Ready | null> {
  try {
    const r = await fetch(`${base}/api/ready`)
    const d = await r.json().catch(() => null)
    if (!d || typeof d.ready !== 'boolean') return null
    return { ready: d.ready, loading: Array.isArray(d.loading) ? d.loading.map(String) : [], seconds: Number(d.seconds) || 0 }
  } catch {
    return null
  }
}

/** A random id the page sends with a search and with its paired plain search, so the server's rate limit counts the pair once. */
export const pairedRunId = (): string => randomId()

/** A version-4 UUID. crypto.randomUUID only exists on secure pages (https or localhost); a Lab opened at a LAN address (http://192.168...)
 *  has crypto.getRandomValues only, so the id is built from that. */
export function randomId(): string {
  if (typeof crypto.randomUUID === 'function' && window.isSecureContext) return crypto.randomUUID()
  const b = crypto.getRandomValues(new Uint8Array(16))
  b[6] = (b[6] & 0x0f) | 0x40
  b[8] = (b[8] & 0x3f) | 0x80
  const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('')
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`
}

const STOPPED = 'The server stopped answering. Check the terminal running it, then try again.'

/** Opens the step stream for one request. Returns a function that stops it.
 *  Always a POST: the sentence (and a key, if there is one) travels in the body, never in an address. */
export function streamSearch(q: string, onEvent: (e: TraceEvent) => void, onError: (message: string) => void, brain?: BrainSetting | null, pairedRun?: string): () => void {
  if (brain?.kind === 'device') return streamDevice(q, brain, onEvent, onError, pairedRun)
  const body = brain && brain.kind !== 'local' ? toBody(q, brain) : { q }
  return streamPost(body, onEvent, onError, undefined, pairedRun, !!brain && brain.kind !== 'local')
}

/** Plain search of the same sentence as typed, for the comparison card. null when it cannot be had. */
export async function plainSearch(q: string, pairedRun?: string): Promise<{ seconds: number; hits: Hit[] } | null> {
  try {
    const r = await fetch('/api/plain', { method: 'POST', headers: { 'content-type': 'application/json', ...(pairedRun ? { 'x-paired-run': pairedRun } : {}) }, body: JSON.stringify({ q }) })
    return r.ok ? await r.json() : null
  } catch {
    return null
  }
}

function streamPost(body: unknown, onEvent: (e: TraceEvent) => void, onError: (message: string) => void, signal?: AbortSignal, pairedRun?: string, ownModel = false): () => void {
  const ac = new AbortController()
  signal?.addEventListener('abort', () => ac.abort())
  let ended = false
  ;(async () => {
    try {
      const headers: Record<string, string> = { 'content-type': 'application/json' }
      if (pairedRun) headers['x-paired-run'] = pairedRun
      const r = await fetch('/api/search', { method: 'POST', headers, body: JSON.stringify(body), signal: ac.signal })
      if (!r.ok || !r.body) {
        const d = await r.json().catch(() => null)
        const detail = typeof d?.detail === 'string' ? d.detail : Array.isArray(d?.detail) ? d.detail.map((x: { msg: string }) => x.msg).join('; ') : `the server answered ${r.status}`
        onError(r.status === 429 ? `Too many searches just now: ${detail}. Wait a moment, then try again.`
          : r.status === 503 ? `The server is still starting: ${detail}. Try again in a few seconds.`
          : ownModel ? `Your model settings were refused: ${detail}` : `The server refused the search: ${detail}`)
        return
      }
      const reader = r.body.getReader()
      const dec = new TextDecoder()
      let buf = ''
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        let cut: number
        while ((cut = buf.indexOf('\n\n')) >= 0) {
          const line = buf.slice(0, cut).trim()
          buf = buf.slice(cut + 2)
          if (!line.startsWith('data:')) continue
          const e = JSON.parse(line.slice(5)) as TraceEvent
          onEvent(e)
          if (e.kind === 'end') ended = true
        }
      }
      if (!ended) onError(STOPPED)
    } catch (err) {
      if ((err as Error).name !== 'AbortError') onError(STOPPED)
    }
  })()
  return () => ac.abort()
}

/** The model names a key can use, asked of the provider through our server. Throws a plain message on any failure. */
export async function loadModels(b: { kind: string; key: string; baseUrl: string }): Promise<string[]> {
  const r = await fetch('/api/models', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ kind: b.kind, key: b.key, base_url: b.baseUrl || undefined }) })
  const d = await r.json().catch(() => null)
  if (!r.ok) throw new Error(typeof d?.detail === 'string' ? d.detail : `the server answered ${r.status}`)
  return d.models as string[]
}

export type Refined = { hits: Hit[]; seconds: number; info: { liked_found: number; liked_sent: number } }

/** Search again, moved toward the products the visitor liked. Throws a plain message on any failure. */
export async function refineSearch(q: string, liked: string[], gender?: string | null): Promise<Refined> {
  const r = await fetch('/api/refine', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ q, liked, gender: gender ?? null }) })
  if (!r.ok) {
    const d = await r.json().catch(() => null)
    throw new Error(typeof d?.detail === 'string' ? d.detail : `the server answered ${r.status}`)
  }
  return r.json()
}

// ---------------------------------------------------------------- a model on the visitor's own device (Ollama, LM Studio...)
// The page talks to it directly: a server on the internet cannot reach a visitor's computer. Only the resulting plan is sent to the server,
// which puts it through the same checks as its own models' answers.

const DEVICE_HELP = 'Make sure the app is running and allows this page to connect. See “Let this page talk to your app” under AI model for the exact origin and browser permission.'

/** The model names the app on this device has. Throws a plain message on any failure. */
export async function deviceModels(baseUrl: string): Promise<string[]> {
  let r: Response
  try {
    r = await fetch(`${baseUrl.replace(/\/$/, '')}/models`, { signal: AbortSignal.timeout(8000) })
  } catch {
    throw new Error(`Could not reach ${baseUrl}. ${DEVICE_HELP}`)
  }
  if (!r.ok) throw new Error(`The app at ${baseUrl} answered ${r.status}. ${DEVICE_HELP}`)
  const d = await r.json().catch(() => null)
  const names = ((d?.data ?? []) as { id?: string }[]).map((m) => String(m.id ?? '')).filter(Boolean)
  if (!names.length) throw new Error('The app has no models available. Load or download a model in that app, then try again.')
  return names
}

let promptCache: Promise<{ system: string; schema: unknown }> | null = null

/** A small model can overshoot the plan's size limits. The server trims too (understand.Plan); trimming here keeps the request well under the
 *  16 KB body limit: at most 12 pieces of 200 characters, 10 colours and owned items of 120, a 300-character main query; notes dropped. */
function clipPlan(plan: Record<string, unknown>): Record<string, unknown> {
  const str = (v: unknown, n: number) => (typeof v === 'string' ? v.slice(0, n) : v)
  const list = (v: unknown, n: number, each: number) => (Array.isArray(v) ? v.slice(0, n).map((x) => str(x, each)) : v)
  const pieces = Array.isArray(plan.pieces) ? plan.pieces.slice(0, 12).map((p) => (p && typeof p === 'object'
    ? { ...p, search_text: str((p as Record<string, unknown>).search_text, 200), colours: list((p as Record<string, unknown>).colours, 10, 120) } : p)) : plan.pieces
  const { notes: _notes, ...rest } = plan
  return { ...rest, main_query: str(plan.main_query, 300), occasion: str(plan.occasion, 120), season: str(plan.season, 120), pieces, already_has: list(plan.already_has, 10, 120) }
}

/** Ask the device model for a plan, with the server's own instructions and answer shape. Resolves to the plan, or throws a plain message. */
async function askDevice(q: string, b: BrainSetting, signal: AbortSignal): Promise<Record<string, unknown>> {
  promptCache ??= fetch('/api/understand-prompt').then((r) => { if (!r.ok) throw new Error('the server would not give the instructions'); return r.json() })
  const { system, schema } = await promptCache.catch((e) => { promptCache = null; throw e })
  const url = `${b.baseUrl.replace(/\/$/, '')}/chat/completions`
  const body: Record<string, unknown> = { model: b.model, temperature: 0, messages: [
    { role: 'system', content: `${system}\nAnswer with ONE JSON object that matches this JSON schema: ${JSON.stringify(schema)}` },
    { role: 'user', content: `Request: ${q}` }], response_format: { type: 'json_object' } }
  const timeout = AbortSignal.any([signal, AbortSignal.timeout(90000)])        // a local model can be slow, but not for ever
  const call = () => fetch(url, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body), signal: timeout })
  let r: Response
  try {
    r = await call()
    if (r.status === 400) { delete body.response_format; r = await call() }    // some apps do not know JSON mode; the instructions already ask for JSON only
  } catch (e) {
    if ((e as Error).name === 'TimeoutError') throw new Error('it did not answer within 90 seconds')
    if ((e as Error).name === 'AbortError') throw e
    throw new Error(`could not reach ${b.baseUrl}. ${DEVICE_HELP}`)
  }
  if (!r.ok) throw new Error(`the app answered ${r.status}${r.status === 404 ? ` (is "${b.model}" a model it has?)` : ''}`)
  const text = String((await r.json().catch(() => null))?.choices?.[0]?.message?.content ?? '')
  const raw = text.replace(/^```(?:json)?\s*|\s*```$/g, '')
  try { return JSON.parse(raw) } catch { /* fall through: take the first {...} block */ }
  const m = raw.match(/\{[\s\S]*\}/)
  if (!m) throw new Error('it did not answer with JSON')
  try { return JSON.parse(m[0]) } catch { throw new Error('it did not answer with valid JSON') }
}

/** A search whose sentence-reading step runs on the visitor's device. While the device model thinks, the page already shows step 2 as running. */
function streamDevice(q: string, b: BrainSetting, onEvent: (e: TraceEvent) => void, onError: (message: string) => void, pairedRun?: string): () => void {
  const ac = new AbortController()
  let stopStream: (() => void) | null = null
  ;(async () => {
    onEvent({ kind: 'step', request_id: 'device', stage: 'understand', status: 'started', seconds: null, payload: {} } as TraceEvent)
    const t0 = performance.now()
    const model = `${b.model} · ${providerOf(b.provider).label.replace(/ \(.*\)$/, '')}`
    let device: Record<string, unknown>
    try {
      device = { plan: clipPlan(await askDevice(q, b, ac.signal)), model, seconds: (performance.now() - t0) / 1000 }
    } catch (e) {
      if ((e as Error).name === 'AbortError') return
      device = { model, seconds: Math.min((performance.now() - t0) / 1000, 600), error: String((e as Error).message).slice(0, 300) }
    }
    stopStream = streamPost({ q, device }, onEvent, onError, ac.signal, pairedRun, true)
  })()
  return () => { ac.abort(); stopStream?.() }
}
