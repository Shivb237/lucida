// The "waking up" page of the public Viewer: the hosted Lab sleeps when nobody uses it, and a sleeping server cannot show anything itself.
// This page (on the always-on Viewer site) wakes it, runs one warm-up search so the search model is loaded, then opens the Lab.
// The answer cannot be read across sites (no CORS), but a reply of any kind arriving means the server is awake.
import { useEffect, useState } from 'react'
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
          <path d={shirt} transform={`translate(${x} 52)`} fill={i === 1 ? 'var(--mag-film, #c0267a)' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
        </g>
      ))}
    </svg>
  )
}

export function WakePage() {
  const [secs, setSecs] = useState(0)
  const [state, setState] = useState<'waking' | 'ready' | 'failed'>('waking')

  useEffect(() => {
    if (!PHOTO_BASE) return
    const t0 = Date.now()
    const tick = window.setInterval(() => setSecs(Math.floor((Date.now() - t0) / 1000)), 1000)
    let go = 0
    const ctl = new AbortController()
    // a first search (not only /api/health): it loads the search model, so the visitor lands on a Lab that answers at once
    fetch(`${PHOTO_BASE}/api/plain?q=warm%20up`, { mode: 'no-cors', signal: ctl.signal })
      .then(() => { setState('ready'); go = window.setTimeout(() => window.location.assign(PHOTO_BASE), 900) })
      .catch((e) => { if (e?.name !== 'AbortError') setState('failed') })
    return () => { window.clearInterval(tick); window.clearTimeout(go); ctl.abort() }
  }, [])

  if (!PHOTO_BASE) return <main id="main" tabIndex={-1} className="wrap wake"><h1>No live Lab is linked</h1><p>This copy of the site has no hosted Lab address, so there is nothing to wake. Open the mode menu to see how to run the Lab yourself.</p></main>

  const stuck = state === 'waking' && secs >= STUCK_AFTER
  return (
    <main id="main" tabIndex={-1} className="wrap wake">
      <Rail />
      <h1>{state === 'ready' ? 'Ready. Opening the Lab…' : state === 'failed' ? 'The Lab did not answer' : 'Waking up the Lab'}</h1>
      <p role="status" className="wake-line">
        {state === 'ready' ? 'It is awake and warmed up.'
          : state === 'failed' ? 'The network call failed. Check your connection, then try again.'
            : stuck ? 'This is taking longer than the usual 45 seconds or so.'
              : 'The server sleeps when nobody uses it, so the first visit takes about 45 seconds. You will be taken there on your own.'}
      </p>
      {state === 'waking' && <p className="wake-quip" aria-hidden="true">{QUIPS[Math.floor(secs / 4) % QUIPS.length]}… <span className="wake-secs">{secs}s</span></p>}
      <p className="wake-links">
        <a href={PHOTO_BASE}>Open the Lab now</a> · <a href="#/">Back to the Viewer</a>
        {state === 'failed' && <> · <button type="button" className="mp-copy" onClick={() => window.location.reload()}>Try again</button></>}
      </p>
    </main>
  )
}
