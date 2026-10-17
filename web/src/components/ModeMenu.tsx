// The mode control at the top right of the navigation: says which mode you are in, explains both, and is where your own model key is entered.
// A disclosure (a button that opens a panel), not a menu: the panel holds a form, so Escape closes it and Tab moves through it normally.
import { useEffect, useRef, useState } from 'react'
import { loadModels } from '../api'
import { PHOTO_BASE } from '../recorded'
import { describe, LOCAL, PROVIDERS, providerOf, usable, withProvider, type BrainSetting } from '../brain'

const START = [
  { cmd: 'scripts/setup_env.sh', what: 'Once: set up Python and the libraries.' },
  { cmd: 'ollama pull qwen3:4b-instruct', what: 'Once: download the AI model (skip it if you will use your own key).' },
  { cmd: '.venv/bin/uvicorn genkart.server:app --app-dir src --port 8000', what: 'Start the server and keep it running.' },
  { cmd: 'cd web && npm ci && npm run dev', what: 'Start this site. It will find the server.' },
]

function Copy({ text }: { text: string }) {
  const [done, setDone] = useState(false)
  return (
    <button type="button" className="mp-copy" onClick={() => { navigator.clipboard?.writeText(text).then(() => { setDone(true); window.setTimeout(() => setDone(false), 1500) }).catch(() => {}) }}>
      {done ? 'Copied' : 'Copy'}
    </button>
  )
}

export function ModeMenu({ lab, serverFound, detail, canByo, hosted = false, viewerOnly, brain, onBrain, onMode }: {
  lab: boolean              // you are in Lab now
  serverFound: boolean      // a Lab server answers at this address
  detail: string            // what that server reports (model, router)
  canByo: boolean           // that server can use a key
  hosted?: boolean          // that server is a public host: no built-in model, so a key is the only way to use the AI step
  viewerOnly: boolean       // a public Viewer build: it never looks for a server
  brain: BrainSetting
  onBrain: (b: BrainSetting) => void
  onMode: (m: 'viewer' | 'lab') => void
}) {
  const [open, setOpen] = useState(false)
  const [models, setModels] = useState<string[] | null>(null)       // the names the provider says this key can use (null: not asked yet)
  const [modelState, setModelState] = useState<{ loading: boolean; error: string | null }>({ loading: false, error: null })
  const [typing, setTyping] = useState(false)                         // chose "Other": type a name by hand
  const [draft, setDraft] = useState<BrainSetting>(() => (hosted && brain.kind === 'local' ? withProvider({ ...LOCAL, provider: 'anthropic' }, 'anthropic') : brain))
  const root = useRef<HTMLDivElement>(null)
  const btn = useRef<HTMLButtonElement>(null)

  const closeBtn = useRef<HTMLButtonElement>(null)
  const panel = useRef<HTMLDivElement>(null)
  const close = () => { setOpen(false); btn.current?.focus() }   // always hand focus back to the button that opened it

  // While open this is a modal sheet: the page behind cannot scroll, Escape and the dimmed backdrop close it, a page change closes it,
  // Tab stays inside it, and focus starts on Close so a keyboard or screen-reader user always has a way out.
  useEffect(() => {
    if (!open) return
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeBtn.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); close(); return }
      if (e.key !== 'Tab' || !panel.current) return
      const items = [...panel.current.querySelectorAll<HTMLElement>('button, a[href], input, select, summary, [tabindex]:not([tabindex="-1"])')].filter((el) => !(el as HTMLButtonElement).disabled && el.offsetParent !== null)
      if (items.length === 0) return
      const first = items[0], last = items[items.length - 1]
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
    const onHash = () => setOpen(false)
    document.addEventListener('keydown', onKey)
    window.addEventListener('hashchange', onHash)
    return () => { document.body.style.overflow = prevOverflow; document.removeEventListener('keydown', onKey); window.removeEventListener('hashchange', onHash) }
  }, [open])

  const kind = draft.kind
  const needsKey = kind !== 'local'
  const ready = usable(draft)
  const prov = providerOf(draft.provider)
  const host = (() => { try { return new URL(draft.baseUrl).host } catch { return '' } })()
  const using = brain.kind !== 'local'
  const set = (patch: Partial<BrainSetting>) => setDraft((d) => ({ ...d, ...patch }))
  const forgetModels = () => { setModels(null); setTyping(false); setModelState({ loading: false, error: null }) }      // a new key or provider: the old list no longer applies
  const fetchModels = () => {
    setModelState({ loading: true, error: null })
    loadModels({ kind: draft.kind, key: draft.key.trim(), baseUrl: draft.baseUrl }).then((names) => {
      setModels(names); setTyping(false); setModelState({ loading: false, error: null })
      if (!names.includes(draft.model)) set({ model: names.find((n) => /flash|haiku|mini|chat|small|instruct/i.test(n)) ?? names[0] })       // a sensible first pick; the visitor can change it
    }).catch((e: Error) => setModelState({ loading: false, error: e.message }))
  }
  const canLoad = draft.key.trim().length >= 8 && (draft.provider !== 'custom' || /^https?:\/\//.test(draft.baseUrl.trim())) && !modelState.loading

  return (
    <div className="mode-wrap" ref={root}>
      <button ref={btn} type="button" className="mode-btn" aria-expanded={open} aria-controls="mode-panel" onClick={() => setOpen((o) => !o)}>
        <svg aria-hidden="true" width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          {lab
            ? <path d="M7 2h4M8 2v5L3.5 14.5A1.2 1.2 0 0 0 4.6 16h8.8a1.2 1.2 0 0 0 1.1-1.5L10 7V2" />          /* a flask: Lab */
            : <><path d="M1.5 9S4.2 4 9 4s7.5 5 7.5 5-2.7 5-7.5 5S1.5 9 1.5 9Z" /><circle cx="9" cy="9" r="2.2" /></>}  {/* an eye: Viewer */}
        </svg>
        <span className="mode-name">{lab ? 'Lab' : 'Viewer'}</span>
        <span className="mode-sub">{lab ? (using ? 'your key' : hosted ? 'hosted' : 'this computer') : 'recorded runs'}</span>
        <svg aria-hidden="true" width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={open ? 'flip' : ''}><path d="M2 4l4 4 4-4" /></svg>
      </button>

      {open && <div className="mode-scrim" onClick={close} aria-hidden="true" />}
      {open && (
        <div id="mode-panel" className="mode-panel" role="dialog" aria-modal="true" aria-labelledby="mp-title" ref={panel}>
          <div className="mp-top">
            <h2 id="mp-title" className="mp-h">Two ways to use Lucida</h2>
            <button type="button" className="mp-close" ref={closeBtn} onClick={close}>
              <svg aria-hidden="true" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M2 2l10 10M12 2L2 12" /></svg>
              Close
            </button>
          </div>
          <div className="mp-body">
          <div className="mp-cards">
            <section className="mp-card" aria-current={!lab ? 'true' : undefined}>
              <h3>Viewer {!lab && <span className="mp-here">you are here</span>}</h3>
              <p>Watch real runs that were recorded, and the recording from AWS. Nothing is searched, nothing is installed, and no key is needed.</p>
              {lab && <button type="button" className="btn-line" onClick={() => { onMode('viewer'); close() }}>Switch to Viewer</button>}
            </section>
            <section className="mp-card" aria-current={lab ? 'true' : undefined}>
              <h3>Lab {lab && <span className="mp-here">you are here</span>}</h3>
              {hosted && serverFound
                ? <p>Search your own words live on this hosted Lab. It has no built-in AI model: the whole sentence is searched as typed, or read first by the AI you choose with your own API key (below). All four catalogues are searched.</p>
                : <p>Search your own words, live, on your own computer, with the model on it or with your own API key. Lab is for people who can run the project themselves. If that is not you, stay in Viewer: you miss nothing needed to judge the work.</p>}
              {serverFound && <p className="mp-note">{hosted ? 'The hosted Lab is running' : 'Your own server is running'} ({detail}).</p>}
              {serverFound
                ? (!lab && <button type="button" className="btn-line" onClick={() => { onMode('lab'); close() }}>Switch to Lab</button>)
                : (
                  <>
                    {viewerOnly && PHOTO_BASE ? (
                      <>
                        <p className="mp-note">Try the hosted Lab: search your own words live (all four catalogues; add your own API key to use the AI step). It sleeps when nobody is using it, so the first visit takes about 45 seconds.</p>
                        <a className="btn-live" href="#/wake" onClick={close}>
                          <span className="btn-live-main"><i className="live-dot" aria-hidden="true" />Open the live Lab<svg aria-hidden="true" width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9h11M10 4.5 14.5 9 10 13.5" /></svg></span>
                          <span className="btn-live-sub">Wakes a sleeping server · about 45 s</span>
                        </a>
                      </>
                    ) : (
                      <p className="mp-note">{viewerOnly ? 'This public page cannot start Lab for you.' : 'No Lab server answers at this address.'} Lab runs on <strong>your</strong> computer. With the built-in model, nothing leaves it. With your own key, your sentence goes to the provider you chose.</p>
                    )}
                    <details className="mp-start">
                      <summary>How to start Lab</summary>
                      <ol>
                        {START.map((s) => (
                          <li key={s.cmd}><code>{s.cmd}</code><span>{s.what}</span><Copy text={s.cmd} /></li>
                        ))}
                      </ol>
                      <p className="mp-note">Then open <code>http://localhost:5173</code>. This menu will say "Lab server found" and let you switch.</p>
                    </details>
                  </>
                )}
            </section>
          </div>

          <section className="mp-model" aria-labelledby="mp-model-h">
            <h3 id="mp-model-h">Your model</h3>
            {!lab ? (
              <p className="mp-note">The AI step that reads your sentence can use the model on your computer or your own API key. Choose it here once you are in Lab.</p>
            ) : !canByo ? (
              <p className="mp-note">This server is too old to use a key. Update it, or use the model on this computer.</p>
            ) : (
              <form onSubmit={(e) => { e.preventDefault(); if (ready) { onBrain({ ...draft, key: draft.key.trim() }); close() } }}>
                <fieldset className="mp-kinds">
                  <legend className="sr-only">Which model reads your sentence</legend>
                  {([[false, 'On this computer', 'A free AI program (Ollama) on your computer. Nothing leaves it.'], [true, 'With an API key (a password for a paid AI service)', 'Claude, Gemini, DeepSeek, OpenAI, Groq, Mistral, OpenRouter, Together, or any service that works like OpenAI\'s']] as [boolean, string, string][]).filter(([withKey]) => withKey || !hosted).map(([withKey, name, sub]) => (
                    <label key={name} className="mp-kind" data-on={needsKey === withKey}>
                      <input type="radio" name="brain-kind" checked={needsKey === withKey} onChange={() => setDraft(withKey ? withProvider(draft.kind === 'local' ? { ...LOCAL, provider: 'anthropic' } : draft, draft.kind === 'local' ? 'anthropic' : draft.provider) : LOCAL)} />
                      <span><strong>{name}</strong><span className="dim">{sub}</span></span>
                    </label>
                  ))}
                </fieldset>
                {needsKey && (
                  <div className="mp-fields">
                    <label>Provider
                      <select value={draft.provider} onChange={(e) => { setDraft(withProvider(draft, e.target.value)); forgetModels() }}>
                        {PROVIDERS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                      </select>
                    </label>
                    <label>API key
                      <input type="password" value={draft.key} onChange={(e) => { set({ key: e.target.value }); forgetModels() }} autoComplete="off" spellCheck={false} placeholder="paste your key" />
                    </label>
                    <p className="mp-assure"><svg aria-hidden="true" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><rect x="2.5" y="6" width="9" height="6.5" rx="1" /><path d="M4.5 6V4.2a2.5 2.5 0 0 1 5 0V6" /></svg> Not saved anywhere. Your key lives in this tab until you close or reload it.</p>
                    <details className="mp-safe">
                      <summary>Is my key safe? What happens to it</summary>
                      <ul>
                        <li><strong>In your browser:</strong> held in this tab's memory only. No cookie, no browser storage, never in the address. Reload or close the tab and it is gone.</li>
                        <li><strong>At {hosted ? 'this hosted server' : 'the server'}:</strong> it arrives over HTTPS in the body of the request, is used for that one call (or for loading the model list), then dropped. It is never written to a file or a database, and it is kept out of logs and error messages. The code that does this is public in the repository; you cannot check the copy that is running from here.</li>
                        <li><strong>At your provider:</strong> it is forwarded only to the provider you chose, and only to that provider's fixed address from a short list. Your provider bills you for what it runs.</li>
                        <li><strong>What I cannot promise:</strong> the key does pass through this server on its way. So use a key you can revoke, ideally with a spend limit, and revoke it afterwards if you feel unsure.</li>
                      </ul>
                    </details>
                    <div className="mp-models">
                      <button type="button" className="btn-line" disabled={!canLoad} onClick={fetchModels}>{modelState.loading ? 'Asking your provider…' : models ? 'Reload my models' : 'Load my models'}</button>
                      <span className="mp-note">{models ? `${models.length} models your key can use` : draft.key.trim().length < 8 ? 'Paste your key first, then load the names it can use.' : 'Asks your provider which model names your key can use, so you do not have to guess one.'}</span>
                    </div>
                    {modelState.error && <p role="alert" className="mp-err">{modelState.error}</p>}
                    {models && !typing ? (
                      <label>Model
                        <select value={models.includes(draft.model) ? draft.model : ''} onChange={(e) => (e.target.value === '__other' ? (setTyping(true), set({ model: '' })) : set({ model: e.target.value }))}>
                          {models.map((m) => <option key={m} value={m}>{m}</option>)}
                          <option value="__other">Other: type a name…</option>
                        </select>
                      </label>
                    ) : (
                      <label>Model name{kind === 'anthropic' ? ' (optional)' : ''}
                        <input type="text" value={draft.model} onChange={(e) => set({ model: e.target.value })} autoComplete="off" spellCheck={false} placeholder={prov.modelHint} />
                      </label>
                    )}
                    {draft.provider === 'custom' && (
                      <label>Server address
                        <input type="text" value={draft.baseUrl} onChange={(e) => set({ baseUrl: e.target.value })} autoComplete="off" spellCheck={false} placeholder="https://your-server.example/v1" />
                      </label>
                    )}
                    <div className="mp-prices">
                      <label>Price per million input tokens, $ (optional)
                        <input type="text" inputMode="decimal" value={draft.priceIn} onChange={(e) => set({ priceIn: e.target.value })} autoComplete="off" placeholder="to show money" />
                      </label>
                      <label>per million output tokens, $
                        <input type="text" inputMode="decimal" value={draft.priceOut} onChange={(e) => set({ priceOut: e.target.value })} autoComplete="off" placeholder="to show money" />
                      </label>
                    </div>
                    <p className="mp-note">Prices only show what a run cost you (a token is roughly three quarters of a word). Known Claude models fill themselves in. Your key will be sent to <strong>{kind === 'anthropic' ? 'api.anthropic.com' : host || 'the address you type'}</strong> and nowhere else.</p>
                  </div>
                )}
                <p className="mp-note">
                  {needsKey
                    ? <>Your key stays in this tab's memory and is gone when you reload. {hosted ? 'It goes to this hosted server for the one request, then only to the provider you chose.' : 'It goes only to the server on your computer, then only to the provider you chose.'} It is never saved or logged. Your provider bills you.{hosted ? '' : ' This server stops after 100 searches with a key.'}</>
                    : <>Nothing leaves your computer: the model runs here.</>}
                </p>
                <div className="mp-actions">
                  <button type="submit" className="btn-line" disabled={!ready}>{needsKey ? 'Use this model' : 'Use the model on this computer'}</button>
                  {using && <button type="button" className="mp-forget" onClick={() => { onBrain(LOCAL); setDraft(LOCAL) }}>Forget the key</button>}
                </div>
                <p className="mp-now" aria-live="polite">In use now: {describe(brain)}</p>
              </form>
            )}
          </section>
          </div>
        </div>
      )}
    </div>
  )
}
