// The first thing a visitor sees: what the project found, in plain words and numbers, before any click. Every number is read from the logged runs.
import evidence from 'virtual:evidence'
import { RECORDED } from '../recorded'

const med = (xs: number[]) => { const s = [...xs].sort((a, b) => a - b); return s.length ? s[Math.floor(s.length / 2)] : 0 }

export function FrontDoor({ viewer, onWatch }: { viewer: boolean; onWatch: () => void }) {
  const d = evidence.drawing
  const b4 = evidence.findings.blind4
  const b5 = evidence.blind5
  const extra = med(RECORDED.runs.flatMap((r) => r.events.filter((e) => e.kind === 'step' && e.stage === 'understand' && e.status === 'done').map((e) => (e.kind === 'step' ? e.seconds ?? 0 : 0))))
  const cards = [
    d.genResnet?.ndcg10 && d.text?.ndcg10 && {
      n: 1, title: 'Drawing the outfit first made search worse.',
      big: `${d.genResnet.ndcg10.mean.toFixed(2)} vs ${d.text.ndcg10.mean.toFixed(2)}`,
      body: 'Match score, 0 to 1 (1 means every right product is at the very top): searching with a picture an AI drew, against searching with your words. I dropped the idea.',
      href: '#/evidence', link: 'See the 20 drawings',
    },
    b4 && {
      n: 2, title: 'Adding Indian-wear collections helped most.',
      big: `${b4.methods.A.mean.toFixed(2)} → ${b4.methods.B.mean.toFixed(2)}`,
      body: `A person rated results 0 to 2 (2 is best), not knowing which method made them, on ${b4.methods.A.n_prompts} requests for Indian festivals and weddings. The first collection had almost no sarees or kurtas. Three more fixed most of that; children's and some men's ethnic wear are still thin.`,
      href: '#/evidence', link: 'See the ratings',
    },
    b5 && {
      n: 3, title: 'The AI step did not beat plain search.',
      big: `${b5.mean.C.toFixed(2)} vs ${b5.mean.B.toFixed(2)}`,
      body: `Same 0 to 2 rating, on ${b5.n_prompts} new requests. An AI splitting the request into pieces rated a little lower than just searching your words (the gap could be chance), and took about ${extra.toFixed(0)} seconds longer. A paid Claude model did no better.`,
      href: '#/docs', link: 'Read why it is still there',
    },
  ].filter(Boolean) as { n: number; title: string; big: string; body: string; href: string; link: string }[]
  return (
    <section className="door" aria-label="What this project found">
      <p className="voice door-h">A fashion search, and an honest test of what each step adds.</p>
      <p className="door-lead">I built this to test whether AI steps really improve outfit search. Type what you need to wear and get products, then see what each step added. What I found:</p>
      <ol className="door-cards">
        {cards.map((c) => (
          <li key={c.n} className="door-card">
            <h2>{c.title}</h2>
            <div className="door-big mono">{c.big}</div>
            <p>{c.body}</p>
            <a href={c.href}>{c.link}</a>
          </li>
        ))}
      </ol>
      <div className="door-actions">
        {viewer && <button type="button" className="btn-expose" onClick={onWatch}>Watch one run</button>}
        <a className="btn-line" href="#/docs">How it works</a>
        <a className="btn-line" href="#/evidence">All the numbers</a>
      </div>
      <p className="door-fine">Rated by one person, the project's author, who did not know which method made which result. Small samples, so treat these as hints. The ranges are on the Evidence page.</p>
    </section>
  )
}
