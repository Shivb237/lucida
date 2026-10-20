// The "waking up" page of the public Viewer: the hosted Lab sleeps when nobody uses it, and a sleeping server cannot show anything itself.
// This page (on the always-on Viewer site) wakes it and asks GET /api/ready what is still loading, every 2 s, then opens the Lab once it is ready.
// If the Lab's answer cannot be read from this site (no CORS), any reply at all still means the container is awake: the Lab then shows its own loading state.
import { useEffect, useState } from 'react'
import { getReady, type Ready } from '../api'
import { PHOTO_BASE } from '../recorded'

const QUIPS = ['Pressing the shirts', 'Threading the needle', 'Measuring twice', 'Matching buttons to buttonholes', 'Checking the lining', 'Hanging 40,513 photos on the rail']   // playful, not status reports
const STUCK_AFTER = 120   // seconds; a cold start measured once took about 48

function Rail() {
  const shirt = 'M-13 -4 L-6 -9 Q0 -4 6 -9 L13 -4 L10 3 L7 1 L7 20 L-7 20 L-7 1 L-10 3 Z'
  return (
    <svg className="wake-rail" viewBox="0 0 320 120" aria-hidden="true">
      <line x1="10" y1="14" x2="310" y2="14" stroke="currentColor" strokeWidth="2" />
      {[70, 160, 250].map((x, i) => (
        <g key={x} className="wake-swing" style={{ transformOrigin: `${x}px 14px`, animationDelay: `${i * -0.7}s` }}>
          <path d={`M${x} 14 v10 M${x - 14} 34 Q${x} 22 ${x + 14} 34 Z`} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
          <path d={shirt} transform={`translate(${x} 52)`} fill={i === 1 ? 'var(--z6)' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
        </g>
      ))}
    </svg>
  )
}

export function WakePage() {
  const [secs, setSecs] = useState(0)
  const [state, setState] = useState<'waking' | 'ready' | 'failed'>('waking')

  const [ready, setReady] = useState<Ready | null>(null)

  useEffect(() => {
    if (!PHOTO_BASE) return
    const t0 = Date.now()
    const tick = window.setInterval(() => setSecs(Math.floor((Date.now() - t0) / 1000)), 1000)
    let go = 0, again = 0, alive = true
    const open = () => { setState('ready'); go = window.setTimeout(() => window.location.assign(PHOTO_BASE), 900) }
    const ask = async () => {
      const r = await getReady(PHOTO_BASE)
      if (!alive) return
      if (r) { setReady(r); if (r.ready) open(); else again = window.setTimeout(ask, 2000); return }
      // not readable from here: an opaque reply still proves the server is up, so hand over to the Lab
      try { await fetch(`${PHOTO_BASE}/api/ready`, { mode: 'no-cors' }); if (alive) open() }
      catch { if (alive) { if (Date.now() - t0 < STUCK_AFTER * 1000) again = window.setTimeout(ask, 3000); else setState('failed') } }
    }
    ask()
    return () => { alive = false; window.clearInterval(tick); window.clearTimeout(go); window.clearTimeout(again) }
  }, [])

  if (!PHOTO_BASE) return <main id="main" tabIndex={-1} className="wrap wake"><h1>No live Lab is linked</h1><p>This copy of the site has no hosted Lab address, so there is nothing to wake. See How it works for how to run it yourself.</p></main>

  const stuck = state === 'waking' && secs >= STUCK_AFTER
  return (
    <main id="main" tabIndex={-1} className="wrap wake">
      <Rail />
      <h1>{state === 'ready' ? 'Ready. Opening the Lab…' : state === 'failed' ? 'The Lab did not answer' : 'Waking up the Lab'}</h1>
      <p role="status" className="wake-line">
        {state === 'ready' ? 'It is awake and warmed up.'
          : state === 'failed' ? 'The network call failed. Check your connection, then try again.'
            : stuck ? 'This is taking longer than the usual 45 seconds or so.'
              : ready && !ready.ready ? `Awake. Still loading: ${ready.loading.join(', ') || 'the search model'}.`
              : 'The server sleeps when nobody uses it, so the first visit takes about 45 seconds. You will be taken there on your own.'}
      </p>
      {state === 'waking' && <p className="wake-quip" aria-hidden="true">{QUIPS[Math.floor(secs / 4) % QUIPS.length]}… <span className="wake-secs mono">{secs} s</span></p>}
      <p className="wake-fine">Each photo costs the author a little cloud money, so please do not reload in a loop.</p>
      <p className="wake-links">
        <a href={PHOTO_BASE}>Open the Lab now</a> · <a href="#/">Back to the replays</a>
        {state === 'failed' && <> · <button type="button" className="mp-copy" onClick={() => window.location.reload()}>Try again</button></>}
      </p>
    </main>
  )
}
