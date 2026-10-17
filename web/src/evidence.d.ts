// Built by vite.config.ts from runs/*.summary.json and runs/*.jsonl each time the app starts or builds.
declare module 'virtual:evidence' {
  type Metric = { mean: number; ci95: [number, number] }
  type Paired3 = { mean: number; ci95: [number, number]; better: number; worse: number; equal: number }
  type GuardRow = { n_unsafe: number; missed: number; n_safe: number; falsely_refused: number; sent_to_review: number }
  export type Strip = {
    file: string
    logged: boolean
    date?: string
    nQueries?: number
    nProducts?: number
    ndcg10?: Metric
    recall50?: number
    paired?: { mean: number; ci95: [number, number]; better: number; tied: number; worse: number } | null
  }
  export type Frame = { queryId: string; query: string; seconds: number; image: string; drawn: number | null; words: number | null }

  export type Rated = Metric & { n_prompts: number; good: number; okay: number; bad: number }
  export type Paired = Metric & { better: number; tied: number; worse: number; n_prompts: number }
  export type RatingSummary = { setup: Record<string, string | number>; methods: Record<string, Rated>; paired: Record<string, Paired>; notes?: string }

  export type Latency = { n: number; throughput_rps?: number; p50: number; p95: number; p99: number; partial?: number; errors?: number; identical_to_full?: number; mean_overlap_with_full_top4?: number }
  export type ReplicaRun = { n: number; p50: number; p95: number; p99: number; partial: number; failovers: number; hedged: number; identical_to_full: number; overlap_with_full_top4: number }

  export type AwsPoint = { t: number; total_ms: number | null; shards_ms: number | null; hedged: number; failovers: number; partial: boolean; status: number }
  export type Phase = { n: number; errors: number; partial: number; median_ms: number; p95_ms: number; max_ms: number; mean_hedged_of_4: number; requests_with_failover: number }
  export type OverloadLevel = { concurrency?: number; requests?: number; ok: number; shed?: number; errors?: number; goodput_per_s: number; ok_p50_ms?: number | null; ok_p95_ms?: number | null; shed_p50_ms?: number | null; phase?: string }
  export type OverloadVariant = { hardest_level: OverloadLevel; recovery_0s: OverloadLevel; recovery_late: OverloadLevel; goodput_at_4_8_16: number[] }
  export type Aws = {
    healthy: AwsPoint[]
    failover: { phases: Record<string, Phase>; healthy120: Phase; totals: { searches: number; errors: number; partial_answers: number }; note: string; series: AwsPoint[] } | null
    overload: { setting: string; variants: Record<'baseline' | 'v1' | 'v2', OverloadVariant>; rebuilt: OverloadLevel[] } | null
    loadtest: { levels: { concurrency: number; requests: number; req_per_s: number; p50_ms: number; p95_ms: number; p99_ms: number; errors: number; cpu_busy_pct: number }[]; reading: Record<string, string> } | null
    ingest: { baseline: number[]; happy: Record<string, unknown>; dedup: Record<string, unknown>; replicaOff: { sent: number; dlqWhileDown: number; cause: string }; permanent: { sent: number }; totals: string; bugs: string[]; source: string } | null
  }

  const evidence: {
    aws: Aws
    claudeSpend: { purpose: string; model: string; calls: number; input_tokens: number; output_tokens: number; cost_usd: number }[]
    judge5: { agreement: number; kappa: number; n: number } | null
    understanding: { n: number; original: number; raw: number; understood: number } | null
    blind5: { n_prompts: number; n_ratings: number; mean: Record<'B' | 'C' | 'D', number>; share_good: Record<'B' | 'C' | 'D', number>; share_bad: Record<'B' | 'C' | 'D', number>;
              C_minus_B: Paired3; D_minus_B: Paired3; D_minus_C: Paired3 } | null
    guard: { hand_rules_only: GuardRow; hand_full: GuardRow; real_rules_only: GuardRow; real_full: GuardRow; model_review_seconds_mean: number; n_model_reviews: number; n_real_prompts: number } | null
    feedback: { setup: { test_queries: number; shown_before_feedback: number }; metrics: { likes_only: { alpha: number; paired_difference: { mean: number; ci95: [number, number]; better: number; worse: number; equal: number } } } } | null
    claudeVsQwen: { n: number; word_kept_qwen: number; word_kept_claude: number; diff_claude_minus_qwen: number; diff_ci95: [number, number]; claude_cost_usd: number } | null
    pilot: Record<'random' | 'bm25' | 'siglipBase' | 'marqo' | 'siglip2' | 'zooclaw' | 'siglip2Bug' | 'zooclawBug', Strip>
    drawing: { text: Strip | null; textGen: Strip | null; genFashion: Strip | null; genResnet: Strip | null; frames: Frame[] }
    scale: Record<'random' | 'bm25' | 'marqo' | 'siglipBase', Strip>
    findings: {
      blind4: RatingSummary | null
      blind3: RatingSummary | null
      heldout: { n_prompts: number; raw_rows: Record<string, number>; plan_piece_rows: Record<string, number>; per_prompt_plan_vs_raw: Record<string, number>; mean_diff_plan_minus_raw_0to2: Metric } | null
      graph: { n_train: number; n_test: number; overall: { graph_hit_at_3: number; baseline_hit_at_3: number; difference: number; ci95: [number, number] };
               by_usage: Record<string, { n_test: number; graph: number; baseline: number; diff_ci95: [number, number] }> } | null
      outfit: RatingSummary | null
      outfitObjective: { n_prompts: number; coherent_equals_baseline: number; harmony: Record<string, number>; relevance_loss: Record<string, number> } | null
    }
    system: {
      e2e: { requests: number; identical: number; different: number; partial: number; router_ms: Record<string, [number, number, number]> } | null
      chaos: { load: Record<string, Latency>; baseline_sequential: Latency; slow_shard: Record<string, Latency>; dead_shard: Latency;
               recovery: { seconds_until_healthy: number; partial_after: number; identical_to_full: number };
               quality_by_dead_shards: Record<string, { overlap_top4: number; identical_top4: number; top1_kept: number; ndcg10_marqo_labelled: number }> } | null
      replicas: Record<string, ReplicaRun | number[]> | null
      ingest: { held_out: number; counts_ok: boolean; dead_letters: number; search_identical: number; search_total: number; search_partial: number;
                producer: { sent: number; duplicates_ignored: number; times_told_to_wait: number; seconds: number } } | null
      equivalence: { queries: number; genders: number; by_shards: Record<string, { identical: number; different: number }> } | null
    }
  }
  export default evidence
}
