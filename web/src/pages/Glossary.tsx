// The Glossary page: every plain-language definition the site uses, with a filter box. Works without any server.
import { useState } from 'react'
import { GLOSSARY } from '../content/glossary'

export function GlossaryPage() {
  const [q, setQ] = useState('')
  const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean)
  const shown = GLOSSARY.filter(([t, d]) => words.every((w) => `${t} ${d}`.toLowerCase().includes(w)))
  return (
    <main id="main" tabIndex={-1} className="wrap" style={{ paddingTop: 56, paddingBottom: 110 }}>
      <h1 className="voice" style={{ margin: 0, fontSize: 'clamp(52px, 7vw, 96px)', lineHeight: 1, letterSpacing: '-.015em', maxWidth: '15ch' }}>Words, in plain English.</h1>
      <p className="plain">Every technical term on this site, in one place. The pages also explain each term where it first appears.</p>
      <label className="gl-filter">Filter the terms
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="for example: score, replica, Ollama" autoComplete="off" />
      </label>
      <p className="lg dim" role="status" style={{ margin: '12px 0 0' }}>{shown.length} of {GLOSSARY.length} terms</p>
      {shown.length === 0 ? (
        <p style={{ marginTop: 20 }}>No term matches “{q}”. Try a shorter word.</p>
      ) : (
        <dl className="ev-glossary" style={{ marginTop: 18 }}>
          {shown.map(([t, d]) => <div key={t}><dt>{t}</dt><dd>{d}</dd></div>)}
        </dl>
      )}
    </main>
  )
}
