// The consented study: does a drawn preview change how people rate the same search results? (server: src/genkart/study.py)
// Steps: consent -> 20 searches (one rating each; for a random half the AI drawing is shown beside the products) -> thanks, with a code to delete the answers.
// Nothing personal is asked or stored. Answers go to the server one at a time, and one that cannot be saved is kept and retried, never silently lost.
import { useEffect, useRef, useState } from 'react'
import { randomId } from '../api'
import type { Hit } from '../trace'
import { Picture, SourceChip } from '../components/Sheet'

type Item = { query_id: string; query: string; drawing: string; hits: Hit[] }
type Phase = 'loading' | 'off' | 'consent' | 'rating' | 'done' | 'error'

const uuid = randomId
const shuffle = <T,>(a: T[]) => { const b = [...a]; for (let i = b.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [b[i], b[j]] = [b[j], b[i]] } return b }

async function post(path: string, body: unknown): Promise<void> {
  const r = await fetch(path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
  if (!r.ok) { const d = await r.json().catch(() => null); throw new Error(typeof d?.detail === 'string' ? d.detail : `the server answered ${r.status}`) }
}

export function StudyPage() {
  const [phase, setPhase] = useState<Phase>('loading')
  const [items, setItems] = useState<Item[]>([])
  const [version, setVersion] = useState('')
  const [order, setOrder] = useState<{ item: Item; arm: 'with' | 'without' }[]>([])
  const [at, setAt] = useState(0)
  const [agree, setAgree] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [withdrawCode, setWithdrawCode] = useState('')
  const [withdrawn, setWithdrawn] = useState<string | null>(null)
  const [code] = useState(uuid)                 // a random code made once in this browser: the only thing that ties answers together
  const shownAt = useRef(0)
  const pending = useRef<Record<string, unknown>[]>([])      // answers not yet saved: retried before the next one
  const inFlight = useRef(false)                             // a second click before the first answer is sent does nothing (no double answers)

  useEffect(() => {
    let alive = true
    fetch('/api/study/items').then(async (r) => {
      if (!alive) return
      if (r.status === 404) { setPhase('off'); return }
      if (!r.ok) { setMsg('The study could not load. Try again in a moment.'); setPhase('error'); return }
      const d = await r.json()
      setItems(d.items); setVersion(d.consent_version); setPhase('consent')
    }).catch(() => { if (alive) { setMsg('The study could not load. Check your connection.'); setPhase('error') } })
    return () => { alive = false }
  }, [])

  const begin = () => {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(true); setMsg(null)
    post('/api/study/consent', { participant: code, consent_version: version }).then(() => {
      const arms = shuffle([...Array(Math.ceil(items.length / 2)).fill('with'), ...Array(Math.floor(items.length / 2)).fill('without')]) as ('with' | 'without')[]
      setOrder(shuffle(items).map((item, i) => ({ item, arm: arms[i] })))
      setAt(0); shownAt.current = performance.now(); setPhase('rating')
    }).catch((e: Error) => setMsg(e.message)).finally(() => { inFlight.current = false; setBusy(false) })
  }

  const rate = async (rating: number) => {
    if (inFlight.current) return
    inFlight.current = true
    const cur = order[at]
    pending.current = pending.current.filter((a) => a.query_id !== cur.item.query_id)     // a retry replaces the unsaved answer, never adds a second one
    pending.current.push({ participant: code, consent_version: version, query_id: cur.item.query_id, arm: cur.arm, rating, position: at, seconds: (performance.now() - shownAt.current) / 1000 })
    setBusy(true); setMsg(null)
    try {
      while (pending.current.length) { await post('/api/study/answer', pending.current[0]); pending.current.shift() }      // oldest first; a failure leaves the rest queued
    } catch (e) {
      setMsg(`${(e as Error).message} Your answer is kept: press a rating again to retry.`); setBusy(false); inFlight.current = false; return
    }
    setBusy(false); inFlight.current = false
    if (at + 1 >= order.length) { setPhase('done') } else { setAt(at + 1); shownAt.current = performance.now() }
  }

  const withdraw = (who: string) => {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(true); setMsg(null)
    post('/api/study/withdraw', { participant: who.trim().toLowerCase() }).then(() => setWithdrawn(who.trim())).catch((e: Error) => setMsg(e.message)).finally(() => { inFlight.current = false; setBusy(false) })
  }

  const cur = order[at]
  return (
    <main id="main" tabIndex={-1} className="wrap study">
      <h1 className="voice" style={{ fontSize: 'var(--t-h1)', lineHeight: 1.08, margin: '40px 0 12px' }}>A short study: does a drawing help?</h1>
      {phase === 'loading' && <p role="status">Loading the study…</p>}
      {phase === 'off' && <p>The study is not running on this server.</p>}
      {phase === 'error' && <p role="alert" className="err-line"><span className="tile cross" aria-hidden="true" />{msg}</p>}

      {phase === 'consent' && (
        <section aria-label="Consent" className="study-card">
          <p>This is a small personal project, not an ethics-board study. About 5 minutes. You will see 20 clothing searches and rate, from 1 to 5, how well six products match each request. For some searches an AI-made drawing of the request is shown too. I want to know whether the drawing changes how you rate the same products.</p>
          <ul>
            <li><strong>What is saved:</strong> a random code made in your browser, which search it was, whether the drawing was shown, your rating, the order, how many seconds you took, and the time. Nothing else: no name, no email, no text you type.</li>
            <li><strong>Network addresses:</strong> the study database holds none. Google Cloud keeps ordinary server logs for a limited time that do contain them; I do not use them.</li>
            <li><strong>Voluntary:</strong> stop whenever you like. Close the page and unfinished answers are simply fewer answers.</li>
            <li><strong>Delete your answers:</strong> after finishing, you get your code. Enter it below at any time to delete everything saved under it. I cannot find your answers without the code.</li>
            <li><strong>Use:</strong> only to report, honestly and with the uncertainty shown, whether the drawing made a difference.</li>
          </ul>
          <label className="study-check"><input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} /> I am 18 or older and I agree to take part.</label>
          <p><button type="button" className="btn-expose" disabled={!agree || busy} onClick={begin}>{busy ? 'Starting…' : 'Start the study'}</button></p>
          {msg && <p role="alert" className="err-line"><span className="tile cross" aria-hidden="true" />{msg}</p>}
          <details className="study-withdraw">
            <summary>I already took part and want my answers deleted</summary>
            <p><label>Your code <input value={withdrawCode} onChange={(e) => setWithdrawCode(e.target.value)} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" autoComplete="off" spellCheck={false} /></label>{' '}
              <button type="button" className="btn-line" disabled={busy || withdrawCode.trim().length < 36} onClick={() => withdraw(withdrawCode)}>Delete my answers</button></p>
            {withdrawn && <p role="status">Deleted everything saved under that code (if there was anything).</p>}
          </details>
        </section>
      )}

      {phase === 'rating' && cur && (
        <section aria-label={`Search ${at + 1} of ${order.length}`} className="study-card">
          <p className="study-progress" role="status">Search {at + 1} of {order.length}</p>
          <h2 className="study-query">{cur.item.query}</h2>
          <div className="study-grid">
            {cur.arm === 'with' && (
              <figure className="study-drawing">
                <img src={`${import.meta.env.BASE_URL}${cur.item.drawing}`} alt={`An AI drawing made from the request: ${cur.item.query}`} width={512} height={512} />
                <figcaption>An AI drew this from the request.</figcaption>
              </figure>
            )}
            <div className="frames study-hits">
              {cur.item.hits.map((h) => (
                <figure key={h.id}>
                  <div className="positive"><Picture hit={h} /></div>
                  <div className="frame-title">{h.title}</div>
                  <SourceChip source={h.source} />
                </figure>
              ))}
            </div>
          </div>
          <fieldset className="study-rate" disabled={busy}>
            <legend>How well do these products match “{cur.item.query}”?</legend>
            {[1, 2, 3, 4, 5].map((n) => <button key={n} type="button" className="btn-line" onClick={() => rate(n)}>{n}</button>)}
            <span className="study-ends"><span>1 = not at all</span><span>5 = very well</span></span>
          </fieldset>
          {msg && <p role="alert" className="err-line"><span className="tile cross" aria-hidden="true" />{msg}</p>}
        </section>
      )}

      {phase === 'done' && (
        <section aria-label="Thank you" className="study-card">
          <h2>Thank you.</h2>
          <p>Your answers are saved. If you ever want them deleted, use this code on the start page of the study. I cannot recover it for you.</p>
          <p className="study-code"><code>{code}</code></p>
          <p><button type="button" className="btn-line" onClick={() => navigator.clipboard?.writeText(code).catch(() => {})}>Copy the code</button></p>
        </section>
      )}
    </main>
  )
}
