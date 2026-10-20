// "More like what you liked": the visitor marks products with a thumbs-up, and this panel searches again with the query moved toward them (server: /api/refine).
// The note under the button states what a SIMULATED shopper test measured (runs/feedback-sim.summary.json), so nobody reads more into it than the evidence says.
import { useState } from 'react'
import evidence from 'virtual:evidence-front'
import { refineSearch, type Refined } from '../api'
import { Picture, SourceChip } from './Sheet'

const f2 = (n: number) => (n >= 0 ? '+' : '') + n.toFixed(3)

export function RefinePanel({ query, liked, gender }: { query: string; liked: Set<string>; gender?: string | null }) {
  const [state, setState] = useState<{ status: 'idle' | 'loading' | 'done' | 'error'; result?: Refined; message?: string; forLiked?: string }>({ status: 'idle' })
  const fb = evidence.feedback?.metrics.likes_only
  const key = [...liked].sort().join(',')
  const stale = state.status === 'done' && state.forLiked !== key       // the likes changed since these results were made

  const go = () => {
    setState({ status: 'loading' })
    refineSearch(query, [...liked], gender).then((result) => setState({ status: 'done', result, forLiked: key })).catch((e: Error) => setState({ status: 'error', message: e.message }))
  }

  return (
    <section aria-label="More like what you liked" className="refine">
      <h2 className="h-record" style={{ marginBottom: 6 }}>More like what you liked</h2>
      <p className="refine-lead">Tap Like under the products you like, in step 4. Then search again, nudged toward them. Nothing is saved: your likes are forgotten when you start a new search.</p>
      <button type="button" className="btn-expose refine-go" disabled={liked.size === 0 || state.status === 'loading'} onClick={go}>
        {state.status === 'loading' ? 'Searching…' : liked.size === 0 ? 'Like a product first' : `Find more like these ${liked.size}`}
      </button>
      {state.status === 'error' && <p role="alert" className="err-line"><span className="tile cross" aria-hidden="true" />{state.message}</p>}
      {state.status === 'done' && state.result && (
        <>
          <p className="refine-lead" style={{ marginTop: 16 }}>{stale ? 'Your likes changed: press the button again for new results. ' : ''}Closest products after your likes ({state.result.seconds.toFixed(2)} s):</p>
          <div className="frames refine-frames">
            {state.result.hits.map((h, i) => (
              <figure key={h.id}>
                <div className="positive"><Picture hit={h} /></div>
                <figcaption><span style={{ color: 'var(--z7)' }}>#{i + 1}</span><span>{h.score.toFixed(3)}</span></figcaption>
                <div className="frame-title">{h.title || <span style={{ fontStyle: 'italic' }}>no title in this collection</span>}</div>
                <SourceChip source={h.source} />
              </figure>
            ))}
          </div>
        </>
      )}
      {fb && (
        <p className="refine-note">
          What was measured: a computer pretending to be a shopper (not a person) liked the relevant products among the first {evidence.feedback?.setup.shown_before_feedback} shown, on {evidence.feedback?.setup.test_queries} searches.
          Results beyond those shown improved a little: match score, 0 to 1 (NDCG@10), {f2(fb.paired_difference.mean)} (95% interval {f2(fb.paired_difference.ci95[0])} to {f2(fb.paired_difference.ci95[1])}),
          better on {fb.paired_difference.better} searches, worse on {fb.paired_difference.worse}, unchanged on {fb.paired_difference.equal}. Pushing away from products it did not like made results worse, so only likes are used.
        </p>
      )}
    </section>
  )
}
