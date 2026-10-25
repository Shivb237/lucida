// The page frame: routes, the server health check, and the Replay / Try it live switch.
// Routes live in the hash so a static host can serve them: #/<page>/<sub>. The first segment picks the page; the rest is passed to it
// (#/evidence/<claim-id>, #/docs/<section>), so reviewers can share a link to one claim or one section.
import { lazy, Suspense, useEffect, useState } from 'react'
import { getHealth, type Health } from './api'
import { LOCAL, type BrainSetting } from './brain'
import { PhotoCredits } from './components/PhotoCredits'
import { BackToTop, ErrorNet } from './components/Safety'
import { NAME } from './brand'
import { VIEWER_ONLY } from './recorded'
import { SearchPage } from './pages/Search'
import { ModeSwitch } from './components/ModeSwitch'
// Only the Search page is in the first download; the other pages load when first opened (each is its own file in the build).
// The model menu only exists in Try it live, so the Replay download leaves it out.
const ModeMenu = lazy(() => import('./components/ModeMenu').then((m) => ({ default: m.ModeMenu })))
const DocsPage = lazy(() => import('./pages/Docs').then((m) => ({ default: m.DocsPage })))
const EvidencePage = lazy(() => import('./pages/Evidence').then((m) => ({ default: m.EvidencePage })))
const StudyPage = lazy(() => import('./pages/Study').then((m) => ({ default: m.StudyPage })))
const SystemPage = lazy(() => import('./pages/System').then((m) => ({ default: m.SystemPage })))
const GlossaryPage = lazy(() => import('./pages/Glossary').then((m) => ({ default: m.GlossaryPage })))
const WakePage = lazy(() => import('./pages/Wake').then((m) => ({ default: m.WakePage })))

type Page = 'search' | 'evidence' | 'system' | 'docs' | 'words' | 'wake' | 'study'
const PAGES: Record<string, Page> = { '': 'search', search: 'search', evidence: 'evidence', system: 'system', docs: 'docs', words: 'words', glossary: 'words', wake: 'wake', study: 'study' }
type Route = { page: Page; sub: string }
/** "#/evidence/drawing" -> { page: 'evidence', sub: 'drawing' }. Anything unknown is the Search page. */
const routeOf = (hash: string): Route => {
  const parts = hash.replace(/^#\/?/, '').split('/')
  const page = PAGES[(parts[0] ?? '').toLowerCase()]
  return page ? { page, sub: decodeURIComponent(parts.slice(1).join('/')) } : { page: 'search', sub: '' }
}

const NAV: [Page, string, string][] = [['search', '#/', 'Search'], ['evidence', '#/evidence', 'Evidence'], ['docs', '#/docs', 'How it works'], ['system', '#/system', 'System'], ['words', '#/words', 'Glossary']]

export default function App() {
  const [route, setRoute] = useState<Route>(() => routeOf(window.location.hash))
  const [health, setHealth] = useState<Health | null | undefined>(VIEWER_ONLY ? null : undefined) // undefined = still checking, null = server off
  const [wantViewer, setWantViewer] = useState(false)        // someone in Lab chose to look at the recorded runs
  const [brain, setBrain] = useState<BrainSetting>(LOCAL)      // their own model, in memory only

  useEffect(() => {
    const onHash = () => setRoute(routeOf(window.location.hash))
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  // Health every 8 s while the tab is visible. The state changes only when the answer does, so nothing keyed on it re-runs on every poll;
  // a server that answered is only treated as gone after two failed checks in a row, so one dropped poll never swaps a live run for the Replay;
  // an answer older than one already applied is ignored.
  useEffect(() => {
    if (VIEWER_ONLY) return
    let alive = true, sent = 0, applied = 0, fails = 0
    const check = async () => {
      if (document.hidden) return
      const n = ++sent
      const h = await getHealth()
      if (!alive || n < applied) return
      applied = n
      fails = h ? 0 : fails + 1
      setHealth((prev) => {
        if (!h) return prev && fails < 2 ? prev : null
        return prev && JSON.stringify(prev) === JSON.stringify(h) ? prev : h
      })
    }
    check()
    const t = window.setInterval(check, 8000)
    const onVisible = () => { if (!document.hidden) check() }
    document.addEventListener('visibilitychange', onVisible)
    return () => { alive = false; window.clearInterval(t); document.removeEventListener('visibilitychange', onVisible) }
  }, [])

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [route.page])

  const page = route.page
  const viewer = VIEWER_ONLY || wantViewer || health === null     // Replay unless a live server answers and nobody chose otherwise

  return (
    <div className="page">
      <a className="skip" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById('main')?.focus() }}>Skip to content</a>
      <header className="frame-bar">
        <div className="wrap">
          <div className="bar-left">
            <a href="#/" className="wordmark" aria-label={`${NAME}, start page`}>{NAME}<span className="wm-dot" aria-hidden="true">.</span></a>
            <nav className="nav" aria-label="Main">
              {NAV.map(([p, href, label]) => <a key={p} href={href} className="lg" aria-current={page === p ? 'page' : undefined}>{label}</a>)}
              {health?.study && <a href="#/study" className="lg" aria-current={page === 'study' ? 'page' : undefined}>Study</a>}
            </nav>
          </div>
          <div className="mode-row">
            <ModeSwitch viewer={viewer} canLab={!VIEWER_ONLY && !!health} onMode={(m) => setWantViewer(m === 'viewer')} />
            {!viewer && !!health && <Suspense fallback={null}><ModeMenu key={health.hosted ? 'hosted' : 'own'} canByo={!!health.byo} hosted={!!health.hosted} brain={brain} onBrain={setBrain} /></Suspense>}
          </div>
        </div>
      </header>
      <ErrorNet key={page}>
        <Suspense fallback={<main id="main" tabIndex={-1} className="wrap" style={{ paddingTop: 56 }}><p className="dim" role="status">Loading the page…</p></main>}>
        {page === 'wake' ? <WakePage />
          : page === 'words' ? <GlossaryPage />
          : page === 'study' ? <StudyPage />
          : page === 'search' ? <SearchPage health={health} viewer={viewer} brain={brain} onBrain={setBrain} />
          : page === 'system' ? <SystemPage health={health} viewer={viewer} />
          : page === 'docs' ? <DocsPage sub={route.sub} />
          : <EvidencePage sub={route.sub} />}
        </Suspense>
      </ErrorNet>
      <PhotoCredits />
      <BackToTop />
    </div>
  )
}
