import http from "node:http";
import type { AddressInfo } from "node:net";
import { randomUUID } from "node:crypto";
import type { Config } from "./config.ts";
import { MAX_K } from "./config.ts";
import { LatencyWindow, hedgeDelay } from "./hedge.ts";
import { mergeRoute } from "./merge.ts";
import type { ShardAnswer } from "./merge.ts";

const GENDERS = new Set(["men", "women", "boys", "girls", "unisex"]);

type SearchBody = { text: string; k: number; gender: string | null };

function parseBody(raw: string): SearchBody | string {
  let j: unknown;
  try {
    j = JSON.parse(raw);
  } catch {
    return "body must be JSON";
  }
  if (typeof j !== "object" || j === null) return "body must be an object";
  const o = j as Record<string, unknown>;
  if (typeof o.text !== "string" || o.text.trim().length === 0 || o.text.length > 500) return "text must be a string of 1 to 500 characters";
  const k = o.k === undefined ? 4 : o.k;
  if (typeof k !== "number" || !Number.isInteger(k) || k < 1 || k > MAX_K) return `k must be an integer from 1 to ${MAX_K}`;
  const g = o.gender === undefined || o.gender === null ? null : o.gender;
  if (g !== null && (typeof g !== "string" || !GENDERS.has(g))) return "gender must be one of men, women, boys, girls, unisex or null";
  return { text: o.text, k, gender: g };
}

async function postJson(url: string, body: unknown, timeoutMs: number, extra?: AbortSignal, reqId?: string, deadlineMs?: number, token?: string): Promise<any> {
  const signal = extra ? AbortSignal.any([extra, AbortSignal.timeout(timeoutMs)]) : AbortSignal.timeout(timeoutMs);
  // x-request-id is the search's ticket number: the encoder and every shard write it in their own logs, so one search can be followed across machines
  const headers: Record<string, string> = reqId ? { "content-type": "application/json", "x-request-id": reqId } : { "content-type": "application/json" };
  if (deadlineMs !== undefined) headers["x-deadline-ms"] = String(Math.round(deadlineMs));   // "I stop waiting at this moment": the callee may drop work nobody wants any more
  if (token) headers["x-genkart-token"] = token;   // the shards' shared secret; it is never logged
  const r = await fetch(url, { method: "POST", headers, body: JSON.stringify(body), signal });
  if (!r.ok) throw new Error(`${url} answered ${r.status}`);
  return r.json();
}

export type ShardResult = { value: any; url: string; failovers: number; hedged: boolean };

// A usable /search answer: { candidates: { <source>: [ { source, id, score, cluster, title }, ... ] } }. Anything else (a 200 with an error
// body, a half-written answer, a different program on the port) counts as a FAILED replica, so the next replica is asked; accepted as it
// is, it would pass as a success here and then throw inside mergeRoute, turning the whole search into a 502.
const DIGITS = /^[0-9]{1,20}$/;
export function isShardAnswer(v: unknown): boolean {
  const c = (v as { candidates?: unknown } | null)?.candidates;
  if (typeof c !== "object" || c === null || Array.isArray(c)) return false;
  return Object.values(c).every((list) => Array.isArray(list) && list.every((x) =>
    typeof x === "object" && x !== null && typeof x.source === "string" && typeof x.id === "string" && DIGITS.test(x.id)
    && typeof x.score === "number" && Number.isFinite(x.score) && Number.isInteger(x.cluster) && typeof x.title === "string"));
}

// Ask one shard through its replicas. The replica order is rotated by `start` (spreads load). When a replica fails the next one is
// asked at once (failover); when the current one is merely slow (no answer after hedgeMs) the next one is asked as well and the first
// answer wins (hedging). The hedge delay adapts to the shard (hedge.ts): the larger of HEDGE_MS and the p90 of `stats`, the shard's
// recent successful answer times, which this function also feeds. The whole shard has one deadline. An answer must pass isShardAnswer to
// count. `outer` (the caller hung up) stops every replica request at once.
export function queryShard(group: string[], path: string, body: unknown, cfg: Config, start: number, reqId?: string, stats?: LatencyWindow, outer?: AbortSignal): Promise<ShardResult> {
  const order = group.map((_, i) => group[(start + i) % group.length]);
  return new Promise((resolve, reject) => {
    let next = 0;
    let pending = 0;
    let failovers = 0;
    let hedged = false;
    let done = false;
    const controllers: AbortController[] = [];
    const timers: ReturnType<typeof setTimeout>[] = [];
    const finish = (fn: () => void) => {
      if (done) return;
      done = true;
      timers.forEach(clearTimeout);
      outer?.removeEventListener("abort", hungUp);
      fn();
    };
    const hungUp = () => finish(() => { controllers.forEach((c) => c.abort()); reject(new Error("caller hung up")); });
    const launch = (): boolean => {
      if (next >= order.length) return false;
      const url = order[next++];
      const ac = new AbortController();
      controllers.push(ac);
      pending++;
      const t = performance.now();
      postJson(`${url}${path}`, body, cfg.shardTimeoutMs, ac.signal, reqId, undefined, cfg.shardToken).then((value) => {
        if (!isShardAnswer(value)) throw new Error(`${url}${path} answered 200 without valid candidates`);
        return value;
      }).then(
        (value) => {
          stats?.record(performance.now() - t);   // only answers count: a failure says nothing about how long a good answer takes
          finish(() => { controllers.forEach((c) => c.abort()); resolve({ value, url, failovers, hedged }); });
        },
        (err) => {
          pending--;
          if (done) return;
          failovers++;
          if (!launch() && pending === 0) finish(() => reject(err));
        },
      );
      return true;
    };
    timers.push(setTimeout(() => finish(() => { controllers.forEach((c) => c.abort()); reject(new Error("shard deadline")); }), cfg.shardTimeoutMs));
    if (outer?.aborted) return hungUp();
    outer?.addEventListener("abort", hungUp, { once: true });
    const delay = hedgeDelay(cfg.hedgeMs, stats);
    launch();
    if (order.length > 1 && delay > 0 && delay < cfg.shardTimeoutMs) {
      timers.push(setTimeout(() => { if (!done && next < order.length) { hedged = true; launch(); } }, delay));
    }
  });
}

export function createRouter(cfg: Config): http.Server {
  let counter = 0;   // rotates which replica is asked first
  let inflight = 0;  // searches currently being answered
  const latency = cfg.shardGroups.map(() => new LatencyWindow(200));   // one answer-time window per shard, for the hedge delay
  const send = (res: http.ServerResponse, status: number, body: unknown) => {
    res.writeHead(status, { "content-type": "application/json" });
    res.end(JSON.stringify(body));
  };

  // `signal` fires when the caller hangs up: the encoder call and every shard request are dropped, nobody is waiting for the answer
  async function search(b: SearchBody, reqId: string, signal?: AbortSignal) {
    const t0 = performance.now();
    const enc = await postJson(`${cfg.encoderUrl}/encode`, { texts: [b.text] }, cfg.encoderTimeoutMs, signal, reqId, Date.now() + cfg.encoderTimeoutMs);
    const vector: number[] = enc.vectors[0];
    const t1 = performance.now();
    // scatter: every shard at the same time, each with its own deadline
    const turn = counter++;
    const settled = await Promise.allSettled(cfg.shardGroups.map((g, i) => queryShard(g, "/search", { vector, gender: b.gender, m: cfg.perShard }, cfg, turn, reqId, latency[i], signal)));
    const t2 = performance.now();
    if (signal?.aborted) throw new Error("caller hung up");   // the shards were cut off by the hang-up, not down: no 503 for them
    const answers: ShardAnswer[] = [];
    // the caller learns only which shard numbers failed; the addresses and the reasons go to this router's log alone
    const failed: number[] = [];
    const failedDetail: { shard: number; replicas: string; error: string }[] = [];
    let failovers = 0;
    let hedges = 0;
    settled.forEach((s, i) => {
      if (s.status === "fulfilled") {
        answers.push(s.value.value.candidates as ShardAnswer);
        failovers += s.value.failovers;
        hedges += s.value.hedged ? 1 : 0;
      } else {
        failed.push(i);
        failedDetail.push({ shard: i, replicas: cfg.shardGroups[i].join("|"), error: String(s.reason) });
      }
    });
    if (answers.length === 0) return { status: 503, body: { error: "no shard answered", failed }, detail: failedDetail };
    const merged = mergeRoute(answers, b.k, cfg.theta);
    const t3 = performance.now();
    return {
      status: 200,
      body: {
        results: merged.map((c) => ({ source: c.source, id: c.id, title: c.title, score: c.score })),
        partial: failed.length > 0,
        shards: { total: cfg.shardGroups.length, ok: answers.length, failed: failed.length, failovers, hedged: hedges },
        failed,
        timings_ms: { encode: +(t1 - t0).toFixed(2), shards: +(t2 - t1).toFixed(2), merge: +(t3 - t2).toFixed(2), total: +(t3 - t0).toFixed(2) },
      },
      detail: failedDetail,
    };
  }

  async function health() {
    const probe = async (u: string, token?: string) => {
      try {
        const r = await fetch(`${u}/health`, { signal: AbortSignal.timeout(1000), headers: token ? { "x-genkart-token": token } : {} });
        return r.ok;
      } catch {
        return false;
      }
    };
    const [encoder, ...groups] = await Promise.all([probe(cfg.encoderUrl), ...cfg.shardGroups.map((g) => Promise.all(g.map((u) => probe(u, cfg.shardToken))))]);
    // a shard is available when at least one of its replicas is; replicas lists each replica's state
    const shards = groups.map((g) => g.some(Boolean));
    return { ok: encoder && shards.every(Boolean), encoder, shards, replicas: groups };
  }

  return http.createServer((req, res) => {
    const given = req.headers["x-request-id"];
    const id = typeof given === "string" && /^[A-Za-z0-9_-]{1,32}$/.test(given) ? given : randomUUID().slice(0, 8);   // only plain characters are accepted from outside
    if (req.method === "GET" && req.url === "/health") {
      health().then((h) => send(res, h.ok ? 200 : 503, h));
      return;
    }
    if (req.method === "POST" && req.url === "/search") {
      // load shedding: past the limit, say "busy" in milliseconds instead of queueing the caller into a slow failure (a queue longer than the
      // timeout only produces answers nobody can use). The caller may retry after a moment.
      if (cfg.maxInflight && inflight >= cfg.maxInflight) {
        console.log(JSON.stringify({ req: id, status: 429, shed: true, inflight }));
        res.writeHead(429, { "content-type": "application/json", "retry-after": "1" });
        res.end(JSON.stringify({ error: "busy, try again shortly" }));
        req.resume();
        return;
      }
      // the slot is held for as long as this router works on the search, not for as long as the caller waits: freed exactly once, on the 400 or
      // oversize path, when the caller hangs up before the body is in (no search started), or in the finally after search() has returned.
      // A hang-up during a search aborts it (encoder and shard requests) and the finally frees the slot once those have stopped; freeing it on
      // the hang-up itself would let a new search in while the old one still loads the encoder and the shards.
      inflight++;
      let released = false;
      const release = () => { if (!released) { released = true; inflight--; } };
      const gone = new AbortController();
      let searching = false;
      res.on("close", () => {
        if (res.writableFinished) return;                 // the answer went out: nothing to stop
        if (searching) gone.abort();                      // the caller hung up mid-search: stop it (the finally below frees the slot)
        else release();                                   // hung up while sending the body (or the body was too large): no search to wait for
      });
      const chunks: Buffer[] = [];
      let size = 0;
      let tooBig = false;
      req.on("data", (c: Buffer) => {
        if (tooBig) return;
        size += c.length;
        if (size > 4096) { tooBig = true; release(); req.destroy(); }
        else chunks.push(c);
      });
      req.on("end", async () => {
        if (tooBig) return;
        const parsed = parseBody(Buffer.concat(chunks).toString());
        if (typeof parsed === "string") { release(); return send(res, 400, { error: parsed }); }
        const started = performance.now();   // the caller's whole wait, also for failures (a failed search has no timings of its own)
        searching = true;
        try {
          const out = await search(parsed, id, gone.signal);
          console.log(JSON.stringify({ req: id, status: out.status, partial: (out.body as any).partial ?? null, failovers: (out.body as any).shards?.failovers ?? null, hedged: (out.body as any).shards?.hedged ?? null, ...((out.body as any).timings_ms ?? { total: +(performance.now() - started).toFixed(2) }), ...(out.detail.length ? { failed: out.detail } : {}) }));
          if (!gone.signal.aborted) send(res, out.status, out.body);
        } catch (e) {
          if (gone.signal.aborted) {
            // 499 (nginx's "client closed request"): only in the log, there is nobody to answer
            console.log(JSON.stringify({ req: id, status: 499, error: "caller hung up", total: +(performance.now() - started).toFixed(2) }));
          } else {
            console.log(JSON.stringify({ req: id, status: 502, error: String(e), total: +(performance.now() - started).toFixed(2) }));
            send(res, 502, { error: "encoder or router failure" });   // the full reason (with addresses) is in the log line above, not in the answer
          }
        } finally {
          release();
        }
      });
      return;
    }
    send(res, 404, { error: "not found" });
  });
}

export function listen(server: http.Server, port: number, host = "127.0.0.1"): Promise<number> {
  return new Promise((resolve) => server.listen(port, host, () => resolve((server.address() as AddressInfo).port)));
}
