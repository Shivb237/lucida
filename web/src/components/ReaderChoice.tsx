// "How should your sentence be read?": the one visible choice above the search box in Try it live. It replaces the two notices and the hidden header dialog
// as the first thing a visitor sees. "As typed" always works with no setup; the key and device options open the AI model dialog already on that option.
import { describe, type BrainSetting, LOCAL } from '../brain'
import { openModelDialog } from '../ui'

type Choice = 'plain' | 'key' | 'device'

export function ReaderChoice({ hosted, ollamaUp, canByo, brain, onBrain }: {
  hosted: boolean; ollamaUp: boolean; canByo: boolean; brain: BrainSetting; onBrain: (b: BrainSetting) => void
}) {
  const now: Choice = brain.kind === 'device' ? 'device' : brain.kind === 'local' ? 'plain' : 'key'
  const ownModel = !hosted && ollamaUp           // on your own computer with Ollama running, "plain" is the AI on this computer
  const options: { id: Choice; name: string; sub: string }[] = [
    ownModel ? { id: 'plain', name: 'AI on this computer', sub: 'Ollama, free. Nothing leaves your computer.' }
      : { id: 'plain', name: 'Search as typed', sub: hosted ? 'Works now. No setup, no key.' : 'Works now. Ollama is off; start it to use it here.' },
    ...(canByo ? [
      { id: 'key' as const, name: 'My API key', sub: 'Claude, Gemini, OpenAI and others.' },
      { id: 'device' as const, name: 'AI on my device', sub: 'Ollama or LM Studio. One-time setting, no key.' },
    ] : []),
  ]
  const pick = (id: Choice) => { if (id === 'plain') { if (now !== 'plain') onBrain(LOCAL) } else openModelDialog(id) }
  return (
    <section className="reader" aria-labelledby="reader-h">
      <h2 id="reader-h" className="reader-h">How should your sentence be read?</h2>
      <div className="reader-opts" role="group" aria-labelledby="reader-h">
        {options.map((o) => (
          <button key={o.id} type="button" className="reader-opt" aria-pressed={now === o.id} onClick={() => pick(o.id)}>
            <strong>{o.name}</strong><span className="dim">{o.sub}</span>
          </button>
        ))}
      </div>
      <p className="reader-now" aria-live="polite">
        {now === 'plain' ? <>{ownModel ? 'Using the AI on this computer (Ollama).' : 'The AI step is optional.'} <a href="#/evidence/plan">Does it help?</a></> : <>Using {describe(brain)}. <button type="button" className="text-btn" onClick={() => openModelDialog(now)}>change</button></>}
      </p>
    </section>
  )
}
