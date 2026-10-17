// The page's calls to the local server: health, example prompts, and the live step stream (EventSource).
import { toBody, type BrainSetting } from './brain'
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
    const r = await fetch('/api/health')
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

/** Opens the step stream for one request. Returns a function that stops it.
 *  Without a key: a plain GET (EventSource). With one: a POST, because EventSource cannot send a body and a key must never sit in an address. */
export function streamSearch(q: string, onEvent: (e: TraceEvent) => void, onError: (message: string) => void, brain?: BrainSetting | null): () => void {
  if (brain && brain.kind !== 'local') return streamPost(q, brain, onEvent, onError)
  const source = new EventSource(`/api/search?${new URLSearchParams({ q })}`)
  let ended = false
  source.onmessage = (m) => {
    const e = JSON.parse(m.data) as TraceEvent
    onEvent(e)
    if (e.kind === 'end') {
      ended = true
      source.close()
    }
  }
  source.onerror = () => {
    source.close()
    if (!ended) onError('The server stopped answering. Check the terminal running it, then try again.')
  }
  return () => source.close()
}

function streamPost(q: string, brain: BrainSetting, onEvent: (e: TraceEvent) => void, onError: (message: string) => void): () => void {
  const ac = new AbortController()
  let ended = false
  ;(async () => {
    try {
      const r = await fetch('/api/search', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(toBody(q, brain)), signal: ac.signal })
      if (!r.ok || !r.body) {
        const d = await r.json().catch(() => null)
        const detail = typeof d?.detail === 'string' ? d.detail : Array.isArray(d?.detail) ? d.detail.map((x: { msg: string }) => x.msg).join('; ') : `the server answered ${r.status}`
        onError(`Your model settings were refused: ${detail}`)
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
      if (!ended) onError('The server stopped answering. Check the terminal running it, then try again.')
    } catch (err) {
      if ((err as Error).name !== 'AbortError') onError('The server stopped answering. Check the terminal running it, then try again.')
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
