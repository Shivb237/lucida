// Two safety nets so no visitor is ever stuck: a message with a way out when a page breaks, and a way back to the top of a long page.
import { Component, useEffect, useState, type ReactNode } from 'react'

/** If anything below throws while drawing, show this instead of a blank white screen. */
export class ErrorNet extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    if (!this.state.failed) return this.props.children
    return (
      <main id="main" tabIndex={-1} className="wrap" style={{ paddingTop: 64, paddingBottom: 96, maxWidth: 640 }}>
        <h1 style={{ margin: 0, fontSize: 28, lineHeight: '34px' }}>Something on this page broke.</h1>
        <p style={{ margin: '14px 0 0', fontSize: 16, lineHeight: '24px' }}>Nothing you typed was sent anywhere. Reloading usually fixes it; if it does not, the Viewer and the Docs do not depend on the part that failed.</p>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 20 }}>
          <button type="button" className="btn-expose" onClick={() => window.location.reload()}>Reload the page</button>
          <a className="btn-line" style={{ display: 'inline-flex', alignItems: 'center', textDecoration: 'none' }} href="#/" onClick={() => { this.setState({ failed: false }) }}>Back to the start</a>
          <a className="btn-line" style={{ display: 'inline-flex', alignItems: 'center', textDecoration: 'none' }} href="#/docs" onClick={() => { this.setState({ failed: false }) }}>Open the Docs</a>
        </div>
      </main>
    )
  }
}

/** Appears after about two screens of scrolling, so a 14,000 px phone page always has a way back to the menu. */
export function BackToTop() {
  const [show, setShow] = useState(false)
  useEffect(() => {
    const on = () => setShow(window.scrollY > Math.max(1200, window.innerHeight * 1.5))
    on()
    window.addEventListener('scroll', on, { passive: true })
    return () => window.removeEventListener('scroll', on)
  }, [])
  if (!show) return null
  return (
    <button type="button" className="to-top" aria-label="Back to the top of the page" onClick={() => {
      const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches
      window.scrollTo({ top: 0, behavior: calm ? 'auto' : 'smooth' })
      document.getElementById('main')?.focus({ preventScroll: true })
    }}>
      <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M3 10l5-5 5 5" /></svg>
      Top
    </button>
  )
}
