// Tells what happened in ONE run (recorded or live), step by step, in plain words, using only what that run's trace contains.
import type { RecordedRun } from '../recorded'
import type { ComposePayload, ExpandPayload, OutfitPayload, RequestPayload, SearchPayload, StageId, StepEvent, StepState, UnderstandPayload } from '../trace'

/** headline: one short sentence for the step's closed card; lines: the full account. */
export type Happened = { seconds: number | null; status: string; headline: string; lines: string[] }

const s2 = (x: number | null | undefined) => (x == null ? '—' : x.toFixed(2))
const GUARD: Record<string, string> = { allow: 'it was allowed', personal_data_redacted: 'personal details were removed first, then it was allowed', not_reviewed: 'it was allowed, but the AI reviewer was off, so unclear wording was not reviewed' }

const IDS: StageId[] = ['request', 'understand', 'expand', 'search', 'compose', 'outfit']

export function narrate(run: RecordedRun): Record<StageId, Happened> {
  const done = (stage: StageId): StepEvent | undefined =>
    run.events.find((e): e is StepEvent => e.kind === 'step' && e.stage === stage && e.status !== 'started')
  const steps = {} as Partial<Record<StageId, StepState>>
  for (const id of IDS) { const e = done(id); if (e) steps[id] = { status: e.status, seconds: e.seconds, payload: e.payload } }
  return narrateSteps(steps, 'This step did not run in this recording.')
}

/** The same account for the page's own step states (a live run, or a replay in progress). Steps still waiting or running get a short word. */
export function narrateSteps(steps: Partial<Record<StageId, StepState>>, notRun = 'Not reached yet.'): Record<StageId, Happened> {
  const out = {} as Record<StageId, Happened>
  for (const id of IDS) {
    const e = steps[id]
    if (!e || e.status === 'waiting') { out[id] = { seconds: null, status: 'not run', headline: notRun, lines: [notRun] }; continue }
    if (e.status === 'started') { out[id] = { seconds: null, status: 'started', headline: 'Running now.', lines: ['Running now.'] }; continue }
    const p = e.payload
    const lines: string[] = []
    let headline = ''
    if (id === 'request') {
      const r = p as RequestPayload
      if (e.status === 'failed') { headline = 'Not searched: the safety check stopped it.'; lines.push(r.message ?? headline) }
      else {
        headline = r.guard === 'personal_data_redacted' ? 'Passed the safety check, after removing personal details.' : 'Passed the safety check.'
        lines.push(`You typed: "${r.query}". Safety check: ${GUARD[r.guard ?? 'allow'] ?? r.guard}.`)
      }
      if (r.note) lines.push(r.note)
    } else if (id === 'understand') {
      const u = p as unknown as UnderstandPayload
      if (e.status === 'failed' || u.fell_back || !u.plan) { headline = 'No usable plan, so your words were searched as typed.'; lines.push('The model gave no usable plan, so the whole sentence was searched as typed.') }
      else {
        const pl = u.plan
        headline = `Split your words into ${pl.pieces.length} piece${pl.pieces.length === 1 ? '' : 's'}: ${pl.pieces.map((x) => x.kind).join(', ')}.`
        lines.push(`The model understood: for ${pl.gender}${pl.occasion ? `, occasion "${pl.occasion}"` : ''}${pl.season ? `, ${pl.season}` : ''}.`)
        lines.push(`Pieces to find: ${pl.pieces.map((x) => `${x.kind} "${x.search_text}"`).join('; ') || 'none'}.`)
        if (pl.already_has.length) lines.push(`You already own: ${pl.already_has.join(', ')}.`)
      }
    } else if (id === 'expand') {
      const x = p as ExpandPayload
      if (e.status === 'skipped') { headline = 'Skipped.'; lines.push(x.reason ?? 'Skipped.') }
      else if (e.status === 'failed') { headline = 'Failed, so nothing was added.'; lines.push(x.error ?? headline) }
      else {
        headline = x.notes?.length ? `Added ${x.notes.length} idea${x.notes.length === 1 ? '' : 's'} from the clothes map.` : 'Nothing to add: the pieces already fit.'
        lines.push(x.usages?.length ? `The map recognised the occasion as: ${x.usages.join(', ')}.` : 'The map did not recognise an occasion.')
        lines.push(x.notes?.length ? x.notes.join(' ') : 'It changed nothing: the pieces already fit.')
      }
    } else if (id === 'search') {
      const x = p as unknown as SearchPayload
      if (e.status === 'failed') { headline = 'Search failed.'; lines.push(`Search failed: ${x.error ?? 'unknown'}.`) }
      else {
        const found = x.pieces.reduce((n, pc) => n + pc.hits.length, 0)
        headline = `Found ${found} close products for ${x.pieces.length} piece${x.pieces.length === 1 ? '' : 's'}.`
        for (const piece of x.pieces) {
          const best = piece.hits[0]
          const sources = [...new Set(piece.hits.map((h) => h.source))].join(' and ')
          lines.push(`${piece.kind} "${piece.text}": ${piece.hits.length} products found${sources ? ` (from ${sources})` : ''}${best ? `, closest match (similarity ${best.score.toFixed(3)}, higher is closer)` : ''}, ${s2(piece.seconds)} s.`)
        }
        if (x.backend === 'router') {
          const rq = (x.info as { requests: { shards: { total: number; hedged: number; failovers: number }; timings_ms: { encode: number; shards: number; total: number } }[] }).requests
          const r0 = rq[0]
          if (r0) lines.push(`Each piece went to ${r0.shards.total} slices of the product list at once and took about ${Math.round(r0.timings_ms.total)} ms: ${Math.round(r0.timings_ms.encode)} ms turning words into numbers, ${Math.round(r0.timings_ms.shards)} ms looking up.${r0.shards.hedged ? ` For ${r0.shards.hedged} slices a backup copy was asked too, because the first was slow.` : ''}${r0.shards.failovers ? ` ${r0.shards.failovers} switched to a backup copy.` : ''}`)
        } else lines.push('Searched inside the server itself, without the split system.')
      }
    } else if (id === 'compose') {
      const x = p as ComposePayload
      if (e.status === 'skipped') { headline = 'Skipped: nothing to match.'; lines.push(x.reason ?? 'Skipped.') }
      else {
        headline = x.changed ? `Swapped ${x.changed} of ${x.pieces ?? 0} picks so the colours go together.` : `Kept the closest pick for each piece: the colours already go together.`
        lines.push(`${x.harmony ? `Colours go together: ${x.harmony.coherent.toFixed(2)} out of 1 (${x.harmony.baseline.toFixed(2)} before the check). ` : ''}${x.changed ?? 0} of ${x.pieces ?? 0} picks were swapped for a better colour match.${x.colours ? ` Colours seen in the photos: ${x.colours.map((c) => c ?? 'unknown').join(', ')}.` : ''}`)
      }
    } else if (id === 'outfit') {
      const x = p as OutfitPayload
      if (e.status === 'skipped') { headline = 'No outfit could be built.'; lines.push(`No outfit could be built: ${x.reason ?? 'no reason given'}.`) }
      else headline = `Picked ${(x.items ?? []).length} piece${(x.items ?? []).length === 1 ? '' : 's'}, one for each part of the plan.`
      if (e.status !== 'skipped') for (const it of x.items ?? []) lines.push(`${it.kind}: ${it.pick.title || it.piece} (from ${it.pick.source}, closest-match rank ${it.rank}).`)
    }
    out[id] = { seconds: e.seconds, status: e.status, headline: headline || lines[0] || '', lines }
  }
  return out
}

/** The pieces of one run that the "journey of one request" draws: the plan, where each match came from, and the picks. All read from the run's trace. */
export type Journey = {
  prompt: string
  guard: string
  pieces: { kind: string; text: string; hits: { id: string; source: string; score: number; picked: boolean }[] }[]
  usages: string[]
  added: number
  colours: (string | null)[]
  picks: { kind: string; id: string; source: string; colour: string | null }[]
  /** Collections a piece's matches could come from: the general one always, the specialists when its matches came from them too. */
  collections: string[]
}

export const COLLECTIONS = ['marqo', 'kaggle', 'myntra2', 'mens3']

export function journey(run: RecordedRun): Journey {
  const pay = <T>(stage: StageId) => run.events.find((e): e is StepEvent => e.kind === 'step' && e.stage === stage && e.status === 'done')?.payload as T | undefined
  const req = pay<RequestPayload>('request')
  const ex = pay<ExpandPayload>('expand')
  const se = pay<SearchPayload>('search')
  const co = pay<ComposePayload>('compose')
  const ou = pay<OutfitPayload>('outfit')
  const picked = new Set((ou?.items ?? []).map((i) => i.pick.id))
  const pieces = (se?.pieces ?? []).map((p) => ({ kind: p.kind, text: p.text, hits: p.hits.map((h) => ({ id: h.id, source: h.source, score: h.score, picked: picked.has(h.id) })) }))
  const colours = co?.colours ?? []
  return {
    prompt: run.prompt,
    guard: req?.guard ?? 'allow',
    pieces,
    usages: ex?.usages ?? [],
    added: ex?.notes?.length ?? 0,
    colours,
    // the colour each pick's own reason names (read from its photo); the compose list as a fallback
    picks: (ou?.items ?? []).map((i, k) => ({ kind: i.kind, id: i.pick.id, source: i.pick.source, colour: i.reasons.map((r) => r.match(/Colour read from the photo: ([^.(]+)/)?.[1]?.trim()).find(Boolean) ?? colours[k] ?? null })),
    collections: COLLECTIONS,
  }
}
