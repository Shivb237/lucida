// The one contract between the backend and this page: every pipeline step reports itself as a trace event.
// Mirrors src/genkart/server.py. Product ids are strings because they are larger than JavaScript numbers can hold.

export type StageId = 'request' | 'understand' | 'expand' | 'search' | 'compose' | 'outfit'
export type Status = 'waiting' | 'started' | 'done' | 'failed' | 'skipped'

export type PlanPiece = { kind: string; search_text: string; colours: string[] }
export type Plan = {
  main_query: string
  gender: string
  occasion: string | null
  season: string | null
  budget_inr: number | null
  pieces: PlanPiece[]
  already_has: string[]
  notes: string[]
}

// a demo hit is drawn as a technical flat instead of a photo
export type Hit = { id: string; source: string; title: string; score: number; image: string; flat?: { shape: string; fill: string } }
export type PieceResult = { kind: string; text: string; seconds: number; hits: Hit[] }

export type RouterInfo = {
  requests: { shards: { total: number; ok: number; failed: number; failovers: number; hedged: number }; partial: boolean; failed: string[]; timings_ms: { encode: number; shards: number; merge: number; total: number } }[]
}
export type LocalInfo = { encode_seconds: number; catalogues: string[]; load_seconds?: number }

export type RequestPayload = { query?: string; guard?: string; note?: string | null; refused?: boolean; category?: string; message?: string }
export type UnderstandPayload = { plan: Plan; model?: string; fell_back?: boolean; error?: string; demo?: boolean }
export type ExpandPayload = { usages?: string[]; notes?: string[]; pieces?: PlanPiece[]; reason?: string; error?: string; graph_first_use?: { import_seconds: number; read_seconds: number; build_seconds: number }; waited_for_startup_seconds?: number }
export type SearchPayload = { backend: 'router' | 'in-process'; info: RouterInfo | LocalInfo; pieces: PieceResult[]; error?: string; checks?: string[] }   // checks: what the candidate checks changed (src/genkart/checks.py)
export type ComposePayload = { harmony?: { baseline: number; coherent: number }; changed?: number; pieces?: number; colours?: (string | null)[]; picks?: string[]; reason?: string }
export type OutfitItem = { kind: string; piece: string; pick: Hit; rank: number; reasons: string[] }
export type OutfitPayload = { items?: OutfitItem[]; already_has?: string[]; gender?: string; reason?: string }

export type StepEvent = {
  kind: 'step'
  request_id: string
  stage: StageId
  status: 'started' | 'done' | 'failed' | 'skipped'
  seconds: number | null
  payload: Record<string, unknown>
}
export type EndEvent = { kind: 'end'; request_id: string }
export type TraceEvent = StepEvent | EndEvent

export type StepState = { status: Status; seconds: number | null; payload: Record<string, unknown> }

export const STEPS: { id: StageId; name: string; explain: string }[] = [
  { id: 'request', name: 'Your request', explain: 'What you typed, after a safety check.' },
  { id: 'understand', name: 'Read your sentence', explain: 'An AI model lists what you need: the pieces, who it is for, the occasion.' },
  { id: 'expand', name: 'Add missing ideas', explain: 'A map of how clothes and occasions go together fills gaps.' },
  { id: 'search', name: 'Find products', explain: 'Each piece is matched to product photos in four collections.' },
  { id: 'compose', name: 'Pick an outfit', explain: 'One product per piece, favouring colours that go together.' },
  { id: 'outfit', name: 'Your outfit', explain: 'The picks, each with a reason.' },
]

/** The three stages a newcomer needs, each a group of the six steps above. The front page's "How it works" strip is drawn from these. */
export const STAGES: { name: string; steps: StageId[] }[] = [
  { name: 'Read your words', steps: ['request', 'understand', 'expand'] },
  { name: 'Find products in 4 collections', steps: ['search'] },
  { name: 'Pick one outfit', steps: ['compose', 'outfit'] },
]
export const stageExplain = (st: { steps: StageId[] }) => STEPS.find((s) => st.steps.includes(s.id) && s.id !== 'request')?.explain ?? ''

/** One density mark per step state, the same everywhere: dotted waiting, hatched running, solid done, cross-hatched failed, struck skipped. */
export const MARK_CLASS: Record<Status, string> = { waiting: 'waiting', started: 'hatch started', done: 'done', failed: 'cross', skipped: 'not_built' }
export const STATUS_WORD: Record<Status, string> = { waiting: 'waiting', started: 'running', done: 'done', failed: 'failed', skipped: 'skipped' }

export const emptySteps = (): Record<StageId, StepState> =>
  Object.fromEntries(STEPS.map((s) => [s.id, { status: 'waiting', seconds: null, payload: {} }])) as Record<StageId, StepState>

export const SOURCE_LABEL: Record<string, string> = { marqo: 'Marqo', kaggle: 'Kaggle', myntra2: 'Myntra photos', mens3: "Men's set", demo: 'Demo' }
export const SOURCE_NOTE: Record<string, string> = {
  marqo: 'the big general collection: sharp photos, mostly from US stores',
  kaggle: 'many Indian items, men and women, tiny photos',
  myntra2: "women's ethnic wear, sharp photos, no titles",
  mens3: "men's western basics",
}
