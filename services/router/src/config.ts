export type Config = {
  host: string;              // 127.0.0.1 = this machine only; on AWS 0.0.0.0, with the security group limiting who can connect
  port: number;
  encoderUrl: string;
  shardGroups: string[][];   // one entry per shard; each entry lists that shard's replicas
  shardTimeoutMs: number;
  encoderTimeoutMs: number;
  theta: number;
  perShard: number;
  hedgeMs: number;           // ask the next replica too when the first has not answered after this long
  maxInflight?: number;      // at most this many searches at once; the next one is answered 429 "busy" at once. 0 or missing = no limit
};

const num = (v: string | undefined, d: number): number => (v !== undefined && v !== "" && Number.isFinite(Number(v)) ? Number(v) : d);

export function loadConfig(env: Record<string, string | undefined> = process.env): Config {
  return {
    host: env.HOST ?? "127.0.0.1",
    port: num(env.PORT, 9100),
    encoderUrl: env.ENCODER_URL ?? "http://127.0.0.1:9000",
    // SHARD_URLS: shards separated by commas, replicas of one shard by |   e.g. "http://a:9101|http://a:9111,http://a:9102|http://a:9112"
    shardGroups: (env.SHARD_URLS ?? "http://127.0.0.1:9101,http://127.0.0.1:9102,http://127.0.0.1:9103,http://127.0.0.1:9104").split(",")
      .map((g) => g.split("|").map((s) => s.trim()).filter(Boolean)).filter((g) => g.length > 0),
    shardTimeoutMs: num(env.SHARD_TIMEOUT_MS, 800),
    encoderTimeoutMs: num(env.ENCODER_TIMEOUT_MS, 5000),
    theta: num(env.THETA, 0.098),
    perShard: num(env.PER_SHARD, 32),
    hedgeMs: num(env.HEDGE_MS, 40),
    maxInflight: num(env.MAX_INFLIGHT, 12),
  };
}
