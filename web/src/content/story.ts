// Tells what happened in ONE recorded run, step by step, in plain words, using only what that run's trace contains.
import type { RecordedRun } from '../recorded'
import type { ComposePayload, ExpandPayload, OutfitPayload, RequestPayload, SearchPayload, StageId, StepEvent, UnderstandPayload } from '../trace'

export type Happened = { seconds: number | null; status: string; lines: string[] }

const s2 = (x: number | null | undefined) => (x == null ? '—' : x.toFixed(2))
const GUARD: Record<string, string> = { allow: 'it was allowed', personal_data_redacted: 'personal details were removed first, then it was allowed', not_reviewed: 'it was allowed, but the AI reviewer was off, so unclear wording was not reviewed' }

export function narrate(run: RecordedRun): Record<StageId, Happened> {
  const done = (stage: StageId): StepEvent | undefined =>
    run.events.find((e): e is StepEvent => e.kind === 'step' && e.stage === stage && e.status !== 'started')
  const out = {} as Record<StageId, Happened>
  const ids: StageId[] = ['request', 'understand', 'expand', 'search', 'compose', 'outfit']
  for (const id of ids) {
    const e = done(id)
    if (!e) { out[id] = { seconds: null, status: 'not run', lines: ['This step did not run in this recording.'] }; continue }
    const p = e.payload
    const lines: string[] = []
    if (id === 'request') {
      const r = p as RequestPayload
      lines.push(`You typed: "${r.query}". Safety check: ${GUARD[r.guard ?? 'allow'] ?? r.guard}.`)
      if (r.note) lines.push(r.note)
    } else if (id === 'understand') {
      const u = p as unknown as UnderstandPayload
      if (e.status === 'failed' || u.fell_back) lines.push('The model gave no usable plan, so the whole sentence was searched as typed.')
      else {
        const pl = u.plan
        lines.push(`The model understood: for ${pl.gender}${pl.occasion ? `, occasion "${pl.occasion}"` : ''}${pl.season ? `, ${pl.season}` : ''}.`)
        lines.push(`Pieces to find: ${pl.pieces.map((x) => `${x.kind} "${x.search_text}"`).join('; ') || 'none'}.`)
        if (pl.already_has.length) lines.push(`You already own: ${pl.already_has.join(', ')}.`)
      }
    } else if (id === 'expand') {
      const x = p as ExpandPayload
      if (e.status === 'skipped') lines.push(x.reason ?? 'Skipped.')
      else {
        lines.push(x.usages?.length ? `The map recognised the occasion as: ${x.usages.join(', ')}.` : 'The map did not recognise an occasion.')
        lines.push(x.notes?.length ? x.notes.join(' ') : 'It changed nothing: the pieces already fit.')
      }
    } else if (id === 'search') {
      const x = p as unknown as SearchPayload
      if (e.status === 'failed') lines.push(`Search failed: ${x.error ?? 'unknown'}.`)
      else {
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
      if (e.status === 'skipped') lines.push(x.reason ?? 'Skipped.')
      else lines.push(`${x.harmony ? `Colours go together: ${x.harmony.coherent.toFixed(2)} out of 1 (${x.harmony.baseline.toFixed(2)} before the check). ` : ''}${x.changed ?? 0} of ${x.pieces ?? 0} picks were swapped for a better colour match.${x.colours ? ` Colours seen in the photos: ${x.colours.map((c) => c ?? 'unknown').join(', ')}.` : ''}`)
    } else if (id === 'outfit') {
      const x = p as OutfitPayload
      if (e.status === 'skipped') lines.push(`No outfit could be built: ${x.reason ?? 'no reason given'}.`)
      else for (const it of x.items ?? []) lines.push(`${it.kind}: ${it.pick.title || it.piece} (from ${it.pick.source}, closest-match rank ${it.rank}).`)
    }
    out[id] = { seconds: e.seconds, status: e.status, lines }
  }
  return out
}
