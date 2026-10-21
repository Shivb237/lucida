// A small, persistent way to rerun the existing search with a natural-language refinement.
import { useState } from 'react'

const MAX_CHARS = 300
// Show the counter whenever the user has typed something; it turns magenta in the last 10 chars.
// aria-hidden keeps it visual-only — maxLength already communicates the limit to screen readers.

export function FollowUp({ busy, canUndo, onFollow, onUndo }: { busy: boolean; canUndo: boolean; onFollow: (text: string) => void; onUndo: () => void }) {
  const [text, setText] = useState('')
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const next = text.trim()
    if (!next || busy) return
    onFollow(next)
    setText('')
  }
  return (
    <form className="follow-up" onSubmit={submit} aria-label="Refine this search">
      <label className="sr-only" htmlFor="follow-up">Refine this search</label>
      <input id="follow-up" value={text} onChange={(e) => setText(e.target.value)} maxLength={MAX_CHARS} autoComplete="off"
        placeholder="Make it more casual" disabled={busy} />
      {text.length > 0 && (
        <span className={`follow-count${text.length >= MAX_CHARS - 10 ? ' follow-count-limit' : ''}`} aria-hidden="true">
          {text.length}/{MAX_CHARS}
        </span>
      )}
      <button type="submit" className="follow-send" disabled={busy || !text.trim()}>{busy ? 'Searching…' : 'Refine'}</button>
      {canUndo && <button type="button" className="follow-undo" onClick={onUndo} disabled={busy} aria-label="Undo last refinement">Undo</button>}
    </form>
  )
}
