import http from "node:http";
import type { AddressInfo } from "node:net";
import { randomUUID } from "node:crypto";
import type { Config } from "./config.ts";
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
  if (typeof k !== "number" || !Number.isInteger(k) || k < 1 || k > 20) return "k must be an integer from 1 to 20";
  const g = o.gender === undefined || o.gender === null ? null : o.gender;
  if (g !== null && (typeof g !== "string" || !GENDERS.has(g))) return "gender must be one of men, women, boys, girls, unisex or null";
  return { text: o.text, k, gender: g };
}

async function postJson(url: string, body: unknown, timeoutMs: number, extra?: AbortSignal, reqId?: string, deadlineMs?: number): Promise<any> {
  const signal = extra ? AbortSignal.any([extra, AbortSignal.timeout(timeoutMs)]) : AbortSignal.timeout(timeoutMs);
  // x-request-id is the search's ticket number: the encoder and every shard write it in their own logs, so one search can be followed across machines
  const headers: Record<string, string> = reqId ? { "content-type": "application/json", "x-request-id": reqId } : { "content-type": "application/json" };
  if (deadlineMs !== undefined) headers["x-deadline-ms"] = String(Math.round(deadlineMs));   // "I stop waiting at this moment": the callee may drop work nobody wants any more
  const r = await fetch(url, { method: "POST", headers, body: JSON.stringify(body), signal });
  if (!r.ok) throw new Error(`${url} answered ${r.status}`);
  return r.json();
}

export type ShardResult = { value: any; url: string; failovers: number; hedged: boolean };

// Ask one shard through its replicas. The replica order is rotated by `start` (spreads load). When a replica fails the next one is
// asked at once (failover); when the current one is merely slow (no answer after hedgeMs) the next one is asked as well and the first
// answer wins (hedging). The whole shard has one deadline.
export function queryShard(group: string[], path: string, body: unknown, cfg: Config, start: number, reqId?: string): Promise<ShardResult> {
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
      fn();
    };
    const launch = (): boolean => {
      if (next >= order.length) return false;
      const url = order[next++];
      const ac = new AbortController();
      controllers.push(ac);
      pending++;
      postJson(`${url}${path}`, body, cfg.shardTimeoutMs, ac.signal, reqId).then(
        (value) => finish(() => { controllers.forEach((c) => c.abort()); resolve({ value, url, failovers, hedged }); }),
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
    launch();
    if (order.length > 1 && cfg.hedgeMs > 0) {
      timers.push(setTimeout(() => { if (!done && next < order.length) { hedged = true; launch(); } }, cfg.hedgeMs));
    }
  });
}

export function createRouter(cfg: Config): http.Server {
  let counter = 0;   // rotates which replica is asked first
  let inflight = 0;  // searches currently being answered
  const send = (res: http.ServerResponse, status: number, body: unknown) => {
    res.writeHead(status, { "content-type": "application/json" });
    res.end(JSON.stringify(body));
  };

  async function search(b: SearchBody, reqId: string) {
    const t0 = performance.now();
    const enc = await postJson(`${cfg.encoderUrl}/encode`, { texts: [b.text] }, cfg.encoderTimeoutMs, undefined, reqId, Date.now() + cfg.encoderTimeoutMs);
    const vector: number[] = enc.vectors[0];
    const t1 = performance.now();
    // scatter: every shard at the same time, each with its own deadline
    const turn = counter++;
    const settled = await Promise.allSettled(cfg.shardGroups.map((g) => queryShard(g, "/search", { vector, gender: b.gender, m: cfg.perShard }, cfg, turn, reqId)));
    const t2 = performance.now();
    const answers: ShardAnswer[] = [];
    const failed: string[] = [];
    let failovers = 0;
    let hedges = 0;
    settled.forEach((s, i) => {
      if (s.status === "fulfilled") {
        answers.push(s.value.value.candidates as ShardAnswer);
        failovers += s.value.failovers;
        hedges += s.value.hedged ? 1 : 0;
      } else failed.push(cfg.shardGroups[i].join("|"));
    });
    if (answers.length === 0) return { status: 503, body: { error: "no shard answered", failed } };
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
    };
  }

  async function health() {
    const probe = async (u: string) => {
      try {
        const r = await fetch(`${u}/health`, { signal: AbortSignal.timeout(1000) });
        return r.ok;
      } catch {
        return false;
      }
    };
    const [encoder, ...groups] = await Promise.all([probe(cfg.encoderUrl), ...cfg.shardGroups.map((g) => Promise.all(g.map(probe)))]);
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
      inflight++;
      let released = false;
      const release = () => { if (!released) { released = true; inflight--; } };
      res.on("close", release);                         // fires once when the answer is sent or the caller hangs up
      const chunks: Buffer[] = [];
      let size = 0;
      req.on("data", (c: Buffer) => {
        size += c.length;
        if (size > 4096) req.destroy();
        else chunks.push(c);
      });
      req.on("end", async () => {
        const parsed = parseBody(Buffer.concat(chunks).toString());
        if (typeof parsed === "string") return send(res, 400, { error: parsed });
        const started = performance.now();   // the caller's whole wait, also for failures (a failed search has no timings of its own)
        try {
          const out = await search(parsed, id);
          console.log(JSON.stringify({ req: id, status: out.status, partial: (out.body as any).partial ?? null, failovers: (out.body as any).shards?.failovers ?? null, hedged: (out.body as any).shards?.hedged ?? null, ...((out.body as any).timings_ms ?? { total: +(performance.now() - started).toFixed(2) }) }));
          send(res, out.status, out.body);
        } catch (e) {
          console.log(JSON.stringify({ req: id, status: 502, error: String(e), total: +(performance.now() - started).toFixed(2) }));
          send(res, 502, { error: "encoder or router failure", detail: String(e) });
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
