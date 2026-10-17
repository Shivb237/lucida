// The router's merge and routing rule. Mirrors src/genkart/sharding.py (merge_route) exactly; test/merge.test.ts checks it
// against fixtures produced by the Python reference. Ids are strings: they reach 1.8e19, beyond exact JavaScript numbers.

export type Cand = { source: string; id: string; score: number; cluster: number; title: string };
export type ShardAnswer = Record<string, Cand[]>;

export const SOURCES = ["marqo", "kaggle", "myntra2", "mens3"] as const;
export const GENERAL = "marqo";
export const THETA = 0.098;

// score high to low; equal scores (exact copies of one photo) by the smaller product id, so results never depend on the shard count
export function byScoreThenId(a: Cand, b: Cand): number {
  if (a.score !== b.score) return b.score - a.score;
  const x = BigInt(a.id);
  const y = BigInt(b.id);
  return x < y ? -1 : x > y ? 1 : 0;
}

export function topDistinct(cands: Cand[], k: number): Cand[] {
  const seen = new Set<number>();
  const out: Cand[] = [];
  for (const c of [...cands].sort(byScoreThenId)) {
    if (seen.has(c.cluster)) continue;
    seen.add(c.cluster);
    out.push(c);
    if (out.length === k) break;
  }
  return out;
}

export function mergeRoute(perShard: ShardAnswer[], k = 4, theta = THETA): Cand[] {
  const bySource: Record<string, Cand[]> = {};
  for (const s of SOURCES) bySource[s] = topDistinct(perShard.flatMap((shard) => shard[s] ?? []), k);
  const first = bySource[GENERAL];
  if (first.length > 0 && first[0].score >= theta) return first;
  const pool = SOURCES.filter((s) => s !== GENERAL).flatMap((s) => bySource[s]).sort(byScoreThenId);
  const seen = new Set<string>();
  const out: Cand[] = [];
  for (const c of pool) {
    if (seen.has(c.id)) continue;
    seen.add(c.id);
    out.push(c);
    if (out.length === k) break;
  }
  return out.length > 0 ? out : first;
}
