// "AI model": the dialog at the top right of the navigation, shown only in Lab, where the visitor picks which AI reads their sentence:
// the model on this computer, their own API key, or a model on their own device. The key lives in this tab's memory only (never storage, never an address).
// A modal dialog: Escape and the backdrop close it, Tab stays inside it, focus returns to the button. Other parts of the page open it with openModelDialog() (ui.ts).
import { useEffect, useRef, useState } from 'react'
import { deviceModels, loadModels } from '../api'
import { MODEL_DIALOG_EVENT, type ModelDialogOpen } from '../ui'
import { DEVICE_APPS, describe, LOCAL, PROVIDERS, providerOf, usable, withProvider, type BrainSetting } from '../brain'


function Copy({ text }: { text: string }) {
  const [status, setStatus] = useState<'idle' | 'copied' | 'failed'>('idle')
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setStatus('copied')
      window.setTimeout(() => setStatus('idle'), 1500)
    } catch {
      setStatus('failed')
    }
  }
  return (
    <button type="button" className="mp-copy" onClick={copy} aria-live="polite" title={status === 'failed' ? 'Select the command and copy it manually.' : undefined}>
      {status === 'copied' ? 'Copied' : status === 'failed' ? 'Copy failed' : 'Copy command'}
    </button>
  )
}

function Command({ children }: { children: string }) {
  return <div className="mp-command"><code>{children}</code><Copy text={children} /></div>
}

export function ModeMenu({ canByo, hosted = false, brain, onBrain }: {
  canByo: boolean           // this server can use a key
  hosted?: boolean          // a public host: no built-in model, so a key or a device model is the only way to use the AI step
  brain: BrainSetting
  onBrain: (b: BrainSetting) => void
}) {
  const [open, setOpen] = useState(false)
  const [models, setModels] = useState<string[] | null>(null)       // the names the provider says this key can use (null: not asked yet)
  const [modelState, setModelState] = useState<{ loading: boolean; error: string | null }>({ loading: false, error: null })
  const [typing, setTyping] = useState(false)                         // chose "Other": type a name by hand
  const [draft, setDraft] = useState<BrainSetting>(() => (hosted && brain.kind === 'local' ? withProvider({ ...LOCAL, provider: 'anthropic' }, 'anthropic') : brain))
  const btn = useRef<HTMLButtonElement>(null)
  const closeBtn = useRef<HTMLButtonElement>(null)
  const panel = useRef<HTMLDivElement>(null)
  const opener = useRef<HTMLElement | null>(null)
  const close = () => { setOpen(false); (opener.current?.isConnected ? opener.current : btn.current)?.focus() }   // return keyboard focus to the control that opened the dialog
  const toggle = () => { if (!open) opener.current = btn.current; setOpen((wasOpen) => !wasOpen) }

  useEffect(() => {
    const onOpen = (event: Event) => {
      const d = (event as CustomEvent<ModelDialogOpen>).detail
      opener.current = d.opener
      if (d.kind === 'key') setDraft((cur) => (cur.kind === 'anthropic' || cur.kind === 'openai' ? cur : withProvider({ ...LOCAL, provider: 'anthropic' }, 'anthropic')))
      if (d.kind === 'device') setDraft((cur) => (cur.kind === 'device' ? cur : withProvider({ ...LOCAL, provider: 'ollama' }, 'ollama')))
      if (d.kind) { setModels(null); setTyping(false); setModelState({ loading: false, error: null }) }
      setOpen(true)
    }
    window.addEventListener(MODEL_DIALOG_EVENT, onOpen)
    return () => window.removeEventListener(MODEL_DIALOG_EVENT, onOpen)
  }, [])

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
  const isKey = kind === 'anthropic' || kind === 'openai'
  const isDevice = kind === 'device'
  const ready = usable(draft)
  const prov = providerOf(draft.provider)
  const host = (() => { try { return new URL(draft.baseUrl).host } catch { return '' } })()
  const using = brain.kind !== 'local'
  const set = (patch: Partial<BrainSetting>) => setDraft((d) => ({ ...d, ...patch }))
  const forgetModels = () => { setModels(null); setTyping(false); setModelState({ loading: false, error: null }) }      // a new key or provider: the old list no longer applies
  const fetchModels = () => {
    setModelState({ loading: true, error: null })
    ;(isDevice ? deviceModels(draft.baseUrl.trim()) : loadModels({ kind: draft.kind, key: draft.key.trim(), baseUrl: draft.baseUrl })).then((names) => {
      setModels(names); setTyping(false); setModelState({ loading: false, error: null })
      if (!names.includes(draft.model)) set({ model: names.find((n) => /flash|haiku|mini|chat|small|instruct/i.test(n)) ?? names[0] })       // a sensible first pick; the visitor can change it
    }).catch((e: Error) => setModelState({ loading: false, error: e.message }))
  }
  const canLoad = !modelState.loading && (isDevice ? /^https?:\/\//.test(draft.baseUrl.trim()) : draft.key.trim().length >= 8 && (draft.provider !== 'custom' || /^https?:\/\//.test(draft.baseUrl.trim())))
  const submit = () => { if (ready) { onBrain({ ...draft, key: draft.key.trim() }); close() } }

  return (
    <div className="mode-wrap">
      <button ref={btn} type="button" className="mode-btn" aria-expanded={open} aria-haspopup="dialog" aria-controls="mode-panel" onClick={toggle}>
        <svg aria-hidden="true" width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="9" cy="9" r="2.6" /><path d="M9 1.5v2.2M9 14.3v2.2M1.5 9h2.2M14.3 9h2.2M3.7 3.7l1.5 1.5M12.8 12.8l1.5 1.5M3.7 14.3l1.5-1.5M12.8 5.2l1.5-1.5" />
        </svg>
        <span className="mode-name">AI model</span>
        <span className="mode-sub">{brain.kind === 'device' ? 'your device' : using ? 'your key' : hosted ? 'none set' : 'this computer'}</span>
      </button>

      {open && <div className="mode-scrim" onClick={close} aria-hidden="true" />}
      {open && (
        <div id="mode-panel" className="mode-panel" role="dialog" aria-modal="true" aria-labelledby="mp-title" ref={panel}>
          <div className="mp-top">
            <h2 id="mp-title" className="mp-h">Which AI reads your sentence</h2>
            <button type="button" className="mp-close" ref={closeBtn} onClick={close}>
              <svg aria-hidden="true" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M2 2l10 10M12 2L2 12" /></svg>
              Close
            </button>
          </div>
          <div className="mp-body">
          <section className="mp-model" aria-label="Your model">
            {!canByo ? (
              <p className="mp-note">This server is too old to use a key. Update it, or use the model on this computer.</p>
            ) : (
              <div role="group" aria-label="Choose the model" onKeyDown={(e) => { if (e.key === 'Enter' && (e.target as HTMLElement).tagName === 'INPUT') { e.preventDefault(); submit() } }}>
                <fieldset className="mp-kinds">
                  <legend className="sr-only">Which model reads your sentence</legend>
                  {([['local', 'On this computer', 'A free AI program (Ollama) on your computer. Nothing leaves it.'],
                    ['key', 'With an API key (a password for a paid AI service)', 'Claude, Gemini, DeepSeek, OpenAI, Groq, Mistral, OpenRouter, Together, or any service that works like OpenAI\'s'],
                    ['device', 'On your device (Ollama, LM Studio, or another local server)', 'Use a local OpenAI-compatible model server. Your sentence goes from this page straight to it; no key.']] as ['local' | 'key' | 'device', string, string][])
                    .filter(([k]) => k !== 'local' || !hosted).map(([k, name, sub]) => {
                      const on = k === 'local' ? kind === 'local' : k === 'key' ? isKey : isDevice
                      return (
                        <label key={k} className="mp-kind" data-on={on}>
                          <input type="radio" name="brain-kind" checked={on} onChange={() => { setDraft(k === 'local' ? LOCAL : k === 'key' ? withProvider(isKey ? draft : { ...LOCAL, provider: 'anthropic' }, isKey ? draft.provider : 'anthropic') : withProvider({ ...LOCAL, provider: 'ollama' }, 'ollama')); forgetModels() }} />
                          <span><strong>{name}</strong><span className="dim">{sub}</span></span>
                        </label>
                      )
                    })}
                </fieldset>
                {(isKey || isDevice) && (
                  <div className="mp-fields">
                    {isDevice && (
                      <>
                        <label>App on your device
                          <select value={draft.provider} onChange={(e) => { setDraft(withProvider(draft, e.target.value)); forgetModels() }}>
                            {DEVICE_APPS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                          </select>
                        </label>
                        <label>Its address
                          <input type="text" value={draft.baseUrl} onChange={(e) => { set({ baseUrl: e.target.value }); forgetModels() }} autoComplete="off" spellCheck={false} placeholder="http://localhost:PORT/v1" aria-describedby={draft.provider === 'device-custom' ? 'device-address-help' : undefined} />
                        </label>
                        {draft.provider === 'device-custom' && <p id="device-address-help" className="mp-note">Enter the local server’s OpenAI-compatible address, including <code>/v1</code>. It must provide <code>/models</code> and <code>/chat/completions</code>.</p>}
                        <details className="mp-safe" open>
                          <summary>Let this page talk to your app (once)</summary>
                          <ul>
                            {draft.provider === 'lmstudio'
                              ? <li><strong>LM Studio:</strong> open the Developer tab, start the server, and switch on <em>Enable CORS</em> (it lets a web page call it).</li>
                              : draft.provider === 'ollama' ? <>
                                <li><strong>Ollama:</strong> quit it first. In a macOS or Linux terminal, run:</li>
                                <li className="mp-command-item"><Command>{`OLLAMA_ORIGINS=${window.location.origin} ollama serve`}</Command></li>
                                <li>With the Ollama app on macOS instead, run this in Terminal, then restart the app:</li>
                                <li className="mp-command-item"><Command>{`launchctl setenv OLLAMA_ORIGINS "${window.location.origin}"`}</Command></li>
                                <li>For Windows, use Ollama’s documented environment-variable setup for allowed origins; the commands above are not Windows commands.</li>
                              </> : <>
                                <li><strong>Your local server:</strong> start its OpenAI-compatible API, then enter its address above. The address must end in <code>/v1</code>.</li>
                                <li>Configure that app to allow requests from <code>{window.location.origin}</code>. Its documentation names this CORS or allowed-origins setting.</li>
                              </>}
                            <li><strong>Your browser</strong> may ask whether this page may reach apps on your device or local network. Allow it, or nothing can connect.</li>
                            <li>Then choose <strong>Load models from my device</strong> below. If it still fails, the app is running but is not allowing this page yet.</li>
                            <li><strong>What travels where:</strong> your sentence goes from this page to the app on your device. Only the plan it writes comes to this server, which checks it like any other model's answer.</li>
                          </ul>
                        </details>
                      </>
                    )}
                    {isKey && (<>
                    <label>Provider
                      <select value={draft.provider} onChange={(e) => { setDraft(withProvider(draft, e.target.value)); forgetModels() }}>
                        {PROVIDERS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                      </select>
                    </label>
                    <label>API key
                      <input type="password" name="lucida-api-key" value={draft.key} onChange={(e) => { set({ key: e.target.value }); forgetModels() }} autoComplete="new-password" data-1p-ignore="true" data-lpignore="true" data-bwignore="true" data-form-type="other" spellCheck={false} placeholder="paste your key" />
                    </label>
                    <p className="mp-assure"><svg aria-hidden="true" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><rect x="2.5" y="6" width="9" height="6.5" /><path d="M4.5 6V4.2a2.5 2.5 0 0 1 5 0V6" /></svg> Not saved anywhere. Your key lives in this tab until you close or reload it.</p>
                    <details className="mp-safe">
                      <summary>Is my key safe? What happens to it</summary>
                      <ul>
                        <li><strong>In your browser:</strong> held in this tab's memory only. No cookie, no browser storage, never in the address. Reload or close the tab and it is gone.</li>
                        <li><strong>At {hosted ? 'this hosted server' : 'the server'}:</strong> it arrives over HTTPS in the body of the request, is used for that one call (or for loading the model list), then dropped. It is never written to a file or a database, and it is kept out of logs and error messages. The code that does this is public in the repository; you cannot check the copy that is running from here.</li>
                        <li><strong>At your provider:</strong> it is forwarded only to the provider you chose, and only to that provider's fixed address from a short list. Your provider bills you for what it runs.</li>
                        <li><strong>What I cannot promise:</strong> the key does pass through this server on its way. So use a key you can revoke, ideally with a spend limit, and revoke it afterwards if you feel unsure.</li>
                      </ul>
                    </details>
                    </>)}
                    <div className="mp-models">
                      <button type="button" className="btn-line" disabled={!canLoad} onClick={fetchModels}>{modelState.loading ? (isDevice ? 'Asking your app…' : 'Asking your provider…') : models ? 'Reload my models' : isDevice ? 'Load models from my device' : 'Load my models'}</button>
                      <span className="mp-note">{models ? `${models.length} model${models.length === 1 ? '' : 's'} ${isDevice ? 'on your device' : 'your key can use'}` : isDevice ? 'Asks the app on your device which models it has.' : draft.key.trim().length < 8 ? 'Paste your key first, then load the names it can use.' : 'Asks your provider which model names your key can use, so you do not have to guess one.'}</span>
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
                    {isKey && (<>
                    <div className="mp-prices">
                      <label>Price per million input tokens, $ (optional)
                        <input type="text" inputMode="decimal" value={draft.priceIn} onChange={(e) => set({ priceIn: e.target.value })} autoComplete="off" placeholder="to show money" />
                      </label>
                      <label>per million output tokens, $
                        <input type="text" inputMode="decimal" value={draft.priceOut} onChange={(e) => set({ priceOut: e.target.value })} autoComplete="off" placeholder="to show money" />
                      </label>
                    </div>
                    <p className="mp-note">Prices only show what a run cost you (a token is roughly three quarters of a word). Known Claude models fill themselves in. Your key will be sent to <strong>{kind === 'anthropic' ? 'api.anthropic.com' : host || 'the address you type'}</strong> and nowhere else.</p>
                    </>)}
                  </div>
                )}
                <p className="mp-note">
                  {isDevice
                    ? <>Nothing is saved. Your sentence goes from this page straight to the app on your device; only the plan it writes is sent to this server.</>
                    : isKey
                    ? <>Your key stays in this tab's memory and is gone when you reload. {hosted ? 'It goes to this hosted server for the one request, then only to the provider you chose.' : 'It goes only to the server on your computer, then only to the provider you chose.'} It is never saved or logged. Your provider bills you.{hosted ? '' : ' This server stops after 100 searches with a key.'}</>
                    : <>Nothing leaves your computer: the model runs here.</>}
                </p>
                <div className="mp-actions">
                  <button type="button" className="btn-line" disabled={!ready} onClick={submit}>{isDevice ? 'Use my device model' : isKey ? 'Use this model' : 'Use the model on this computer'}</button>
                  {using && <button type="button" className="mp-forget" onClick={() => { onBrain(LOCAL); setDraft(LOCAL) }}>{brain.kind === 'device' ? 'Stop using it' : 'Forget the key'}</button>}
                </div>
                {!ready && (() => {
                  const why =
                    isKey && draft.key.trim().length < 8 ? 'Paste your API key above first.' :
                    isKey && !draft.model.trim() ? 'Load your models or type a model name above.' :
                    isDevice && !/^https?:\/\//.test(draft.baseUrl.trim()) ? 'Enter a valid server address above.' :
                    isDevice && !draft.model.trim() ? 'Load models or type a model name above.' :
                    isKey && draft.provider === 'custom' && !/^https?:\/\//.test(draft.baseUrl.trim()) ? 'Enter a server address above.' :
                    null
                  return why ? <p className="mp-note" style={{ marginTop: 6, color: 'var(--z3)' }}>{why}</p> : null
                })()}
                <p className="mp-now" aria-live="polite">In use now: {describe(brain)}</p>
              </div>
            )}
          </section>
          </div>
        </div>
      )}
    </div>
  )
}
