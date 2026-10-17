// The page frame: routes (Search, Evidence, System, Docs, Words), the server health check, and the Viewer-only switch.
import { useEffect, useState } from 'react'
import { getHealth, type Health } from './api'
import { LOCAL, type BrainSetting } from './brain'
import { LabHint } from './components/LabHint'
import { ModeMenu } from './components/ModeMenu'
import { BackToTop, ErrorNet } from './components/Safety'
import { NAME } from './brand'
import { PHOTO_BASE } from './recorded'
import { DocsPage } from './pages/Docs'
import { EvidencePage } from './pages/Evidence'
import { SearchPage } from './pages/Search'
import { SystemPage } from './pages/System'
import { WakePage } from './pages/Wake'

type Route = 'search' | 'evidence' | 'system' | 'docs' | 'words' | 'wake'
const routeOf = (hash: string): Route =>
  hash.startsWith('#/evidence') ? 'evidence' : hash.startsWith('#/system') ? 'system' : hash.startsWith('#/docs') ? 'docs' : hash.startsWith('#/words') ? 'words' : hash.startsWith('#/wake') ? 'wake' : 'search'
// A static build (VITE_VIEWER=1) or ?mode=viewer never looks for a server: it shows recorded evidence only.
const VIEWER_ONLY = import.meta.env.VITE_VIEWER === '1' || new URLSearchParams(window.location.search).get('mode') === 'viewer'

export default function App() {
  const [route, setRoute] = useState<Route>(routeOf(window.location.hash))
  const [health, setHealth] = useState<Health | null | undefined>(VIEWER_ONLY ? null : undefined) // undefined = still checking, null = server off
  const [wantViewer, setWantViewer] = useState(false)        // someone in Lab chose to look at the Viewer
  const [brain, setBrain] = useState<BrainSetting>(LOCAL)      // their own model, in memory only

  useEffect(() => {
    const onHash = () => setRoute(routeOf(window.location.hash))
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    let alive = true
    if (VIEWER_ONLY) return
    const check = () => getHealth().then((h) => alive && setHealth(h))
    check()
    const t = window.setInterval(check, 8000)
    return () => { alive = false; window.clearInterval(t) }
  }, [])

  useEffect(() => {
    if (route === 'words') requestAnimationFrame(() => document.getElementById('words')?.scrollIntoView())
    else window.scrollTo(0, 0)
  }, [route])

  const viewer = VIEWER_ONLY || wantViewer || health === null     // Viewer unless a Lab server answers and nobody chose otherwise
  const detail = health ? `${health.hosted ? 'hosted Lab' : health.ollama ? 'Ollama on' : 'Ollama off'}, ${health.backend === 'router' ? 'searching through the router cluster' : 'searching in one process'}` : ''

  return (
    <div className="page">
      <a className="skip" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus() }}>Skip to content</a>
      <header className="frame-bar">
        <div className="wrap">
          <div style={{ display: 'flex', alignItems: 'center', gap: 40, flexWrap: 'wrap' }}>
            <a href="#/" className="wordmark">{NAME.toUpperCase()}</a>
            <nav className="nav" aria-label="Main">
              <a href="#/" className="lg" aria-current={route === 'search' ? 'page' : undefined}>Search</a>
              <a href="#/evidence" className="lg" aria-current={route === 'evidence' ? 'page' : undefined}>Evidence</a>
              <a href="#/system" className="lg" aria-current={route === 'system' ? 'page' : undefined}>System</a>
              <a href="#/docs" className="lg" aria-current={route === 'docs' ? 'page' : undefined}>Docs</a>
              <a href="#/words" className="lg" aria-current={route === 'words' ? 'page' : undefined}>Words</a>
            </nav>
          </div>
          <ModeMenu key={health?.hosted ? 'hosted' : 'own'} lab={!viewer && !!health} serverFound={!!health} detail={detail} canByo={!!health?.byo} hosted={!!health?.hosted} viewerOnly={VIEWER_ONLY} brain={brain} onBrain={setBrain}
            onMode={(m) => setWantViewer(m === 'viewer')} />
        </div>
      </header>
      {viewer && PHOTO_BASE && route !== 'wake' && <LabHint />}
      <ErrorNet key={route}>
      {route === 'wake' ? <WakePage /> : route === 'search' ? <SearchPage health={health} viewer={viewer} brain={brain} /> : route === 'system' ? <SystemPage health={health} viewer={viewer} /> : route === 'docs' ? <DocsPage /> : <EvidencePage />}
      </ErrorNet>
      <BackToTop />
    </div>
  )
}
