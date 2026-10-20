// An inline glossary word: a button in the sentence that opens a short plain definition beside it. Click or Enter opens it, Escape or a
// click elsewhere closes it, and focus goes back to the word. Definitions come from content/glossary.ts (read only); the few words it does
// not hold yet have a local fallback here.
import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { GLOSSARY } from '../content/glossary'

const FALLBACK: Record<string, string> = {
  paired: 'Both ways were run on the same requests, and compared one request at a time. This removes the luck of which requests were picked.',
  blind: 'The rater could not see which way made which result, so the rating could not favour one way.',
  'weighted kappa': 'An agreement score between two raters. 0 means no better than chance and 1 means perfect. Near-misses count partly.',
  bootstrap: 'Re-running the sums on many shuffled copies of the same requests, to see how much the answer could move by luck.',
  wilson: 'A standard way to give a 95% range for a share, such as how many safe prompts were refused.',
  difference: 'One way’s score minus the other’s, on the same requests. Above zero means the first way did better.',
}
/** Short keys used in the text, mapped to the glossary's own headings. */
const ALIAS: Record<string, string> = { 'ndcg@10': 'Match score (NDCG@10)', 'match score': 'Match score (NDCG@10)', '95% range': '95% range', interval: '95% range', range: '95% range',
  'recall@50': 'Found in the top 50 (Recall@50)', 'bm25': 'Keyword search (BM25)' }

export function definition(key: string): { title: string; text: string } | null {
  const k = key.toLowerCase()
  const name = ALIAS[k]
  const hit = GLOSSARY.find(([t]) => (name ? t === name : t.toLowerCase() === k || t.toLowerCase().startsWith(`${k} (`)))
  if (hit) return { title: hit[0], text: hit[1] }
  return FALLBACK[k] ? { title: key, text: FALLBACK[k] } : null
}

export function Term({ k, children }: { k: string; children?: ReactNode }) {
  const def = definition(k)
  const [open, setOpen] = useState(false)
  const [right, setRight] = useState(false)
  const id = useId()
  const btn = useRef<HTMLButtonElement>(null)
  const box = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    if (!open) return
    const r = btn.current?.getBoundingClientRect()
    if (r) setRight(r.left > window.innerWidth / 2)
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') { setOpen(false); btn.current?.focus() } }
    const click = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node) && !btn.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('keydown', key)
    document.addEventListener('mousedown', click)
    return () => { document.removeEventListener('keydown', key); document.removeEventListener('mousedown', click) }
  }, [open])
  if (!def) return <>{children ?? k}</>
  return (
    <span className="evd-term">
      <button ref={btn} type="button" className="evd-term-btn" aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}>{children ?? k}</button>
      <span ref={box} id={id} role="note" className={`evd-term-pop${right ? ' right' : ''}`} hidden={!open}>
        <strong>{def.title}</strong> {def.text}
      </span>
    </span>
  )
}
