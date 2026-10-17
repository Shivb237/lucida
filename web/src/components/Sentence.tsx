import type { Plan } from '../trace'

// Marks the words of the request that the plan was built from. This is only an overlay: the plan card below lists every field exactly.
const STOP = new Set(['a', 'an', 'the', 'for', 'my', 'of', 'in', 'on', 'at', 'to', 'and', 'with', 'is', 'i', 'me', 'that', 'suit', 'goes', 'go'])
const MONTHS = new Set(['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'])
const SEASONS = new Set(['summer', 'winter', 'monsoon', 'rainy', 'rain', 'spring', 'autumn', 'fall', 'snow', 'cold', 'chilly'])
const GENDER_WORDS: Record<string, string> = {}
for (const w of ['men', 'mens', 'man', 'male', 'guy', 'guys', 'boyfriend', 'husband', 'dad', 'father', 'brother', 'groom']) GENDER_WORDS[w] = 'men'
for (const w of ['women', 'womens', 'woman', 'ladies', 'lady', 'female', 'girlfriend', 'wife', 'mom', 'mum', 'mother', 'sister', 'bride', 'her']) GENDER_WORDS[w] = 'women'
for (const w of ['boy', 'boys', 'son']) GENDER_WORDS[w] = 'boys'
for (const w of ['girl', 'girls', 'daughter']) GENDER_WORDS[w] = 'girls'

const clean = (t: string) => t.toLowerCase().replace(/['’]s$/, '').replace(/[^a-z0-9]/g, '')
const tokensOf = (s: string | null | undefined) => (s ? s.split(/\s+/).map(clean).filter((t) => t && !STOP.has(t)) : [])
const singular = (w: string) => (w.endsWith('ies') ? w.slice(0, -3) + 'y' : w.endsWith('s') && !w.endsWith('ss') && w.length > 3 ? w.slice(0, -1) : w)   // not 'dress' -> 'dres'

export type Segment = { text: string; label?: string; value?: string }

export function annotate(text: string, plan: Plan | null): Segment[] {
  const words = text.split(/\s+/).filter(Boolean)
  if (!plan) return words.map((w) => ({ text: w }))
  const owned = new Set(plan.already_has.flatMap(tokensOf))
  const occasion = new Set(tokensOf(plan.occasion))
  const colours = new Set(plan.pieces.flatMap((p) => p.colours.map(clean)))
  const pieceWords = new Set(plan.pieces.map((p) => singular(clean(p.search_text.split(/\s+/).pop() ?? ''))).filter(Boolean))
  const tags = words.map((w): { label?: string; value?: string } => {
    const c = clean(w)
    if (!c) return {}
    if (owned.has(c)) return { label: 'already own', value: plan.already_has.join(', ') }
    if (occasion.has(c)) return { label: 'occasion', value: plan.occasion ?? '' }
    if (plan.season && (MONTHS.has(c) || SEASONS.has(c))) return { label: 'season', value: plan.season }
    if (colours.has(c)) return { label: 'colour', value: c }
    if (plan.gender !== 'unknown' && GENDER_WORDS[c] && GENDER_WORDS[c] === plan.gender) return { label: 'gender', value: plan.gender }
    if (pieceWords.has(singular(c))) return { label: 'piece', value: singular(c) }
    return {}
  })
  const out: Segment[] = []
  words.forEach((w, i) => {
    const t = tags[i]
    const last = out[out.length - 1]
    if (last && t.label && last.label === t.label && last.value === t.value) last.text += ` ${w}`
    else out.push({ text: w, ...t })
  })
  return out
}

export function Sentence({ text, plan, animate }: { text: string; plan: Plan | null; animate: boolean }) {
  return (
    <div className="sentence" aria-label={text}>
      {annotate(text, plan).map((s, i) => (
        <div className="word" key={`${s.text}-${i}`}>
          <span className="voice w">{s.text}</span>
          {s.label && (
            <div className={`tag${animate ? ' dev' : ''}`} style={{ width: '100%' }}>
              <div className="hatch" />
              <div className="leader" />
              <div className="lg dim" style={{ fontSize: 12 }}>{s.label}</div>
              <div className="mono" style={{ fontSize: 14, lineHeight: '20px' }}>{s.value}</div>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
