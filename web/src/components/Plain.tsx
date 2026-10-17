// Two parts of every long section: the answer in plain words (always visible), and the exact numbers (one click away, so no detail is lost).
import type { ReactNode } from 'react'

/** The answer, in everyday words. */
export function Plain({ children }: { children: ReactNode }) {
  return <p className="plain">{children}</p>
}

/** Everything technical for a section: the bars, tables, ranges and sources. Closed by default; the summary says what is inside. */
export function Exact({ label = 'Show the exact numbers', children }: { label?: string; children: ReactNode }) {
  return (
    <details className="exact">
      <summary>{label}</summary>
      <div className="exact-body">{children}</div>
    </details>
  )
}
