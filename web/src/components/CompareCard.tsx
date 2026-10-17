// "Did the plan help?": plain search of the sentence as typed, next to the outfit the plan built, with the time each took and (in the Viewer) the author's blind rating of each.
import evidence from 'virtual:evidence'
import type { Rating } from '../recorded'
import type { Hit, OutfitItem } from '../trace'
import { Picture, SourceChip } from './Sheet'

const sec = (x: number) => (x < 0.095 ? `${x.toFixed(2)} s` : `${x.toFixed(1)} s`)
const sg = (x: number) => `${x >= 0 ? '+' : '−'}${Math.abs(x).toFixed(2)}`

export type Plain = { seconds: number; hits: Hit[] }

export function CompareCard({ plain, outfit, planSeconds, ratings }: { plain: Plain | null | 'loading'; outfit: OutfitItem[]; planSeconds: number; ratings?: { plain: Rating; plan: Rating } }) {
  const b5 = evidence.blind5
  const ready = plain && plain !== 'loading'
  const slower = ready && plain.seconds > 0 ? planSeconds / plain.seconds : null
  return (
    <section id="compare" aria-label="Plain search against the plan" className="cmp">
      <h2 className="cmp-h">Did the AI step help? Plain search against the plan</h2>
      <p className="cmp-lead">Same sentence, two ways. <strong>Plain search</strong> looks up your words as typed. <strong>The plan</strong> first has an AI split them into pieces (shirt, trousers, shoes). Judge for yourself.</p>
      <div className="cmp-cols">
        <div className="cmp-col">
          <h3>Plain search: your sentence as typed</h3>
          <p className="cmp-meta mono">{ready ? sec(plain.seconds) : plain === 'loading' ? 'searching…' : 'not available'}{ratings?.plain ? ` · rated ${ratings.plain} by the author, who did not know which was which` : ''}</p>
          {ready ? (
            <div className="cmp-tiles">
              {plain.hits.slice(0, 6).map((h) => (
                <figure key={h.id}><div className="positive"><Picture hit={h} /></div><figcaption>{h.title && h.source === 'marqo' ? h.title : <SourceChip source={h.source} />}</figcaption></figure>
              ))}
            </div>
          ) : <p className="cmp-wait">{plain === 'loading' ? 'Searching your sentence as typed…' : 'Plain search is not available for this run.'}</p>}
        </div>
        <div className="cmp-col">
          <h3>With the plan: the outfit it built</h3>
          <p className="cmp-meta mono">{sec(planSeconds)}{ratings?.plan ? ` · rated ${ratings.plan} by the author, who did not know which was which` : ''}</p>
          <div className="cmp-tiles">
            {outfit.map((it) => (
              <figure key={it.pick.id}><div className="positive"><Picture hit={it.pick} /></div><figcaption>{it.kind}</figcaption></figure>
            ))}
          </div>
        </div>
      </div>
      <p className="cmp-note">
        {slower ? <>Here the plan took about <strong>{slower >= 2 ? `${Math.round(slower)} times longer` : 'the same time'}</strong> ({sec(planSeconds)} against {sec((plain as Plain).seconds)}). </> : null}
        {b5 ? <>On {b5.n_prompts} new requests, rated 0 to 2 by one person who did not know which was which, plain search got <strong>{b5.mean.B.toFixed(2)}</strong> and the plan <strong>{b5.mean.C.toFixed(2)}</strong>. So the plan did not help, and a Claude plan did no better. </> : null}
        What the plan adds by design is an outfit built from several pieces, which one plain search cannot return. We did not measure whether that is worth the wait.
        {b5 ? <details className="cmp-exact"><summary>Exact numbers</summary>Difference plan minus plain: {sg(b5.C_minus_B.mean)} (95% range {sg(b5.C_minus_B.ci95[0])} to {sg(b5.C_minus_B.ci95[1])}); better on {b5.C_minus_B.better}, worse on {b5.C_minus_B.worse}, equal on {b5.C_minus_B.equal} of {b5.n_prompts} requests.</details> : null}
      </p>
    </section>
  )
}
