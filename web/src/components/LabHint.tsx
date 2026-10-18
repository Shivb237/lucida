// A slim strip under the header of the public Viewer: tells a visitor there is a live Lab to try with their own API key, without opening Settings.
// The arrow points up at the mode control in the top right (where the same choice lives). Dismissed for the browser session.
import { useState } from 'react'

const KEY = 'lucida-lab-hint-dismissed'
const wasDismissed = () => { try { return sessionStorage.getItem(KEY) === '1' } catch { return false } }   // storage can be blocked: then the hint simply shows

export function LabHint() {
  const [gone, setGone] = useState(wasDismissed)
  if (gone) return null
  return (
    <div className="lab-hint" role="note">
      <div className="wrap lab-hint-row">
        <p className="lab-hint-text"><strong>Want to try it yourself?</strong> Open the live Lab and paste your own AI key to have it read your sentence.</p>
        <a className="btn-live btn-live-small" href="#/wake">
          <span className="btn-live-main"><i className="live-dot" aria-hidden="true" />Open the live Lab</span>
        </a>
        <svg className="lab-hint-arrow" aria-hidden="true" viewBox="0 0 48 40" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <title>Settings are up here</title>
          <path d="M6 36 C 8 22, 24 14, 40 6" /><path d="M31 4 L41 5.5 L38 15" />
        </svg>
        <button type="button" className="lab-hint-x" aria-label="Dismiss this hint" onClick={() => { try { sessionStorage.setItem(KEY, '1') } catch { /* nothing to remember it in */ } setGone(true) }}>
          <svg aria-hidden="true" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M2 2l10 10M12 2L2 12" /></svg>
        </button>
      </div>
    </div>
  )
}
