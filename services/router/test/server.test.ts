import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import type { AddressInfo } from "node:net";
import { createRouter, listen, queryShard } from "../src/server.ts";
import { loadConfig } from "../src/config.ts";
import type { Config } from "../src/config.ts";
import { LatencyWindow } from "../src/hedge.ts";

type Handler = (body: any, headers?: http.IncomingHttpHeaders) => { status: number; body: unknown; delayMs?: number };

async function fake(handler: Handler): Promise<{ url: string; close: () => Promise<void> }> {
  const server = http.createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on("data", (d: Buffer) => chunks.push(d));
    req.on("end", () => {
      const out = req.url === "/health" ? { status: 200, body: { ok: true } } : handler(chunks.length ? JSON.parse(Buffer.concat(chunks).toString()) : {}, req.headers);
      setTimeout(() => {
        res.writeHead(out.status, { "content-type": "application/json" });
        res.end(JSON.stringify(out.body));
      }, out.delayMs ?? 0);
    });
  });
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", () => r()));
  return { url: `http://127.0.0.1:${(server.address() as AddressInfo).port}`, close: () => new Promise((r) => { server.closeAllConnections(); server.close(() => r()); }) };
}

const cand = (source: string, id: string, score: number, cluster: number) => ({ source, id, score, cluster, title: `t${id}` });
const shardAnswer = (cands: ReturnType<typeof cand>[]): Handler => () => ({ status: 200, body: { candidates: { marqo: cands } } });

async function setup(shardHandlers: Handler[], timeoutMs = 200) {
  return setupGroups(shardHandlers.map((h) => [h]), timeoutMs);
}

// groups[i] = the handlers of the replicas of shard i
async function setupGroups(groups: Handler[][], timeoutMs = 200, hedgeMs = 40) {
  const encoder = await fake(() => ({ status: 200, body: { vectors: [[0.1, 0.2]] } }));
  const shardGroups = await Promise.all(groups.map((g) => Promise.all(g.map(fake))));
  const shards = shardGroups.flat();
  const cfg: Config = { host: "127.0.0.1", port: 0, encoderUrl: encoder.url, shardGroups: shardGroups.map((g) => g.map((s) => s.url)), shardTimeoutMs: timeoutMs, encoderTimeoutMs: 1000, theta: 0.098, perShard: 32, hedgeMs };
  const server = createRouter(cfg);
  const port = await listen(server, 0);
  const call = (path: string, body?: unknown) => fetch(`http://127.0.0.1:${port}${path}`, { method: body === undefined ? "GET" : "POST", body: body === undefined ? undefined : JSON.stringify(body) });
  const stop = async () => { server.closeAllConnections(); server.close(); await encoder.close(); await Promise.all(shards.map((s) => s.close())); };
  return { call, stop };
}

test("merges answers of all shards", async () => {
  const { call, stop } = await setup([shardAnswer([cand("marqo", "1", 0.14, 1)]), shardAnswer([cand("marqo", "2", 0.15, 2)])]);
  const r = await call("/search", { text: "red gown", k: 2 });
  const j: any = await r.json();
  assert.equal(r.status, 200);
  assert.deepEqual(j.results.map((x: any) => x.id), ["2", "1"]);
  assert.equal(j.partial, false);
  assert.deepEqual(j.shards, { total: 2, ok: 2, failed: 0, failovers: 0, hedged: 0 });
  await stop();
});

test("a slow shard is cut off after its deadline and the answer is marked partial", async () => {
  const slow: Handler = () => ({ status: 200, body: { candidates: { marqo: [cand("marqo", "9", 0.5, 9)] } }, delayMs: 600 });
  const { call, stop } = await setup([shardAnswer([cand("marqo", "1", 0.14, 1)]), slow], 150);
  const t = performance.now();
  const j: any = await (await call("/search", { text: "x" })).json();
  assert.ok(performance.now() - t < 450, "the router waited for the slow shard");
  assert.equal(j.partial, true);
  assert.deepEqual([j.shards.total, j.shards.ok, j.shards.failed], [2, 1, 1]);
  assert.deepEqual(j.results.map((x: any) => x.id), ["1"]);
  await stop();
});

test("a shard answering with an error counts as failed", async () => {
  const { call, stop } = await setup([shardAnswer([cand("marqo", "1", 0.14, 1)]), () => ({ status: 500, body: {} })]);
  const j: any = await (await call("/search", { text: "x" })).json();
  assert.equal(j.partial, true);
  assert.equal(j.shards.failed, 1);
  await stop();
});

test("503 when no shard answers", async () => {
  const { call, stop } = await setup([() => ({ status: 500, body: {} }), () => ({ status: 500, body: {} })]);
  assert.equal((await call("/search", { text: "x" })).status, 503);
  await stop();
});

test("bad input is a 400, and unknown paths a 404", async () => {
  const { call, stop } = await setup([shardAnswer([])]);
  assert.equal((await call("/search", { text: "" })).status, 400);
  assert.equal((await call("/search", { text: "ok", k: 99 })).status, 400);
  assert.equal((await call("/search", { text: "ok", gender: "robots" })).status, 400);
  assert.equal((await call("/nope")).status, 404);
  await stop();
});

test("health reports every part", async () => {
  const { call, stop } = await setup([shardAnswer([]), shardAnswer([])]);
  const j: any = await (await call("/health")).json();
  assert.equal(j.ok, true);
  assert.deepEqual(j.shards, [true, true]);
  await stop();
});


const counting = (cands: ReturnType<typeof cand>[], counter: { n: number }, delayMs = 0): Handler => () => { counter.n++; return { status: 200, body: { candidates: { marqo: cands } }, delayMs }; };

test("when the first replica fails the second answers at once: not partial, one failover counted", async () => {
  const good = shardAnswer([cand("marqo", "1", 0.14, 1)]);
  const { call, stop } = await setupGroups([[() => ({ status: 500, body: {} }), good], [good]]);
  const j: any = await (await call("/search", { text: "x" })).json();
  assert.equal(j.partial, false);
  assert.deepEqual(j.shards, { total: 2, ok: 2, failed: 0, failovers: 1, hedged: 0 });
  await stop();
});

test("a slow first replica is hedged: the second is asked after the hedge delay and the faster answer wins", async () => {
  const slow = counting([cand("marqo", "1", 0.14, 1)], { n: 0 }, 400);
  const fast = counting([cand("marqo", "1", 0.14, 1)], { n: 0 });
  const { call, stop } = await setupGroups([[slow, fast]], 1000, 40);
  const t = performance.now();
  const j: any = await (await call("/search", { text: "x" })).json();
  const took = performance.now() - t;
  assert.ok(took < 250, `took ${took} ms: the router waited for the slow replica`);
  assert.equal(j.partial, false);
  assert.equal(j.shards.hedged, 1);
  await stop();
});

test("when both replicas of a shard are down only that shard is missing", async () => {
  const bad: Handler = () => ({ status: 500, body: {} });
  const { call, stop } = await setupGroups([[bad, bad], [shardAnswer([cand("marqo", "1", 0.14, 1)])]]);
  const j: any = await (await call("/search", { text: "x" })).json();
  assert.equal(j.partial, true);
  assert.deepEqual([j.shards.ok, j.shards.failed], [1, 1]);
  await stop();
});

test("replicas share the load: the replica asked first alternates", async () => {
  const a = { n: 0 };
  const b = { n: 0 };
  const { call, stop } = await setupGroups([[counting([cand("marqo", "1", 0.14, 1)], a), counting([cand("marqo", "1", 0.14, 1)], b)]]);
  for (let i = 0; i < 10; i++) await (await call("/search", { text: "x" })).json();
  assert.equal(a.n + b.n, 10);
  assert.ok(a.n >= 4 && b.n >= 4, `uneven: ${a.n} / ${b.n}`);
  await stop();
});

test("health lists replicas and a shard counts as available while one replica lives", async () => {
  const { call, stop } = await setupGroups([[shardAnswer([]), shardAnswer([])]]);
  const j: any = await (await call("/health")).json();
  assert.deepEqual(j.shards, [true]);
  assert.deepEqual(j.replicas, [[true, true]]);
  await stop();
});

test("the search ticket number is forwarded to the encoder and to every shard, and a clean one from the caller is kept", async () => {
  const seen: Record<string, string[]> = { encoder: [], shard: [] };
  const encoder = await fake((_b, h) => { seen.encoder.push(String(h?.["x-request-id"])); return { status: 200, body: { vectors: [[0.1, 0.2]] } }; });
  const shard = await fake((_b, h) => { seen.shard.push(String(h?.["x-request-id"])); return { status: 200, body: { candidates: { marqo: [cand("marqo", "1", 0.5, 1)] } } }; });
  const cfg: Config = { host: "127.0.0.1", port: 0, encoderUrl: encoder.url, shardGroups: [[shard.url]], shardTimeoutMs: 500, encoderTimeoutMs: 1000, theta: 0.098, perShard: 32, hedgeMs: 40 };
  const server = createRouter(cfg);
  const port = await listen(server, 0);
  const call = (id?: string) => fetch(`http://127.0.0.1:${port}/search`, { method: "POST", headers: id ? { "x-request-id": id } : {}, body: JSON.stringify({ text: "x", k: 1 }) });
  await call("trace-abc_1");
  await call("bad id with spaces and \"quotes\"");
  server.closeAllConnections(); server.close(); await encoder.close(); await shard.close();
  assert.equal(seen.encoder[0], "trace-abc_1");
  assert.equal(seen.shard[0], "trace-abc_1");
  assert.match(seen.encoder[1], /^[0-9a-f]{8}$/);          // an unclean ticket number is replaced by a fresh one, never copied into the logs
  assert.equal(seen.encoder[1], seen.shard[1]);
});

test("every search is timed in its log line, also when it fails (a failure's wait must reach the latency chart)", async () => {
  const lines: string[] = [];
  const realLog = console.log;
  console.log = (x: unknown) => { lines.push(String(x)); };
  try {
    const encoder = await fake(() => ({ status: 500, body: { error: "boom" } }));        // the encoder fails -> the router answers 502
    const shard = await fake(() => ({ status: 200, body: { candidates: {} } }));
    const cfg: Config = { host: "127.0.0.1", port: 0, encoderUrl: encoder.url, shardGroups: [[shard.url]], shardTimeoutMs: 500, encoderTimeoutMs: 1000, theta: 0.098, perShard: 32, hedgeMs: 40 };
    const server = createRouter(cfg);
    const port = await listen(server, 0);
    const r = await fetch(`http://127.0.0.1:${port}/search`, { method: "POST", body: JSON.stringify({ text: "x", k: 1 }) });
    server.closeAllConnections(); server.close(); await encoder.close(); await shard.close();
    assert.equal(r.status, 502);
  } finally {
    console.log = realLog;
  }
  const row = JSON.parse(lines.find((l) => l.includes('"status":502'))!);
  assert.equal(typeof row.total, "number");
  assert.ok(row.total >= 0 && row.error);
});

test("past the in-flight limit the router answers 429 at once, and the slot frees up afterwards", async () => {
  const encoder = await fake(() => ({ status: 200, body: { vectors: [[0.1, 0.2]] }, delayMs: 300 }));          // slow encoder: searches pile up
  const shard = await fake(() => ({ status: 200, body: { candidates: { marqo: [cand("marqo", "1", 0.5, 1)] } } }));
  const cfg: Config = { host: "127.0.0.1", port: 0, encoderUrl: encoder.url, shardGroups: [[shard.url]], shardTimeoutMs: 500, encoderTimeoutMs: 2000, theta: 0.098, perShard: 32, hedgeMs: 40, maxInflight: 2 };
  const server = createRouter(cfg);
  const port = await listen(server, 0);
  const search = async () => { const t = performance.now(); const r = await fetch(`http://127.0.0.1:${port}/search`, { method: "POST", body: JSON.stringify({ text: "x", k: 1 }) }); await r.text(); return { status: r.status, ms: performance.now() - t, retry: r.headers.get("retry-after") }; };
  const burst = await Promise.all([search(), search(), search(), search(), search()]);
  const ok = burst.filter((r) => r.status === 200), shed = burst.filter((r) => r.status === 429);
  assert.equal(ok.length, 2);
  assert.equal(shed.length, 3);
  assert.ok(shed.every((r) => r.ms < 150 && r.retry === "1"), "a shed search is answered in milliseconds, with a retry hint");
  assert.equal((await search()).status, 200);                  // the two slots were released
  server.closeAllConnections(); server.close(); await encoder.close(); await shard.close();
});

test("the encoder is told the caller's deadline (an absolute time inside the encoder timeout)", async () => {
  let seen = "";
  const encoder = await fake((_b, h) => { seen = String(h?.["x-deadline-ms"]); return { status: 200, body: { vectors: [[0.1, 0.2]] } }; });
  const shard = await fake(() => ({ status: 200, body: { candidates: { marqo: [cand("marqo", "1", 0.5, 1)] } } }));
  const cfg: Config = { host: "127.0.0.1", port: 0, encoderUrl: encoder.url, shardGroups: [[shard.url]], shardTimeoutMs: 500, encoderTimeoutMs: 3000, theta: 0.098, perShard: 32, hedgeMs: 40 };
  const server = createRouter(cfg);
  const port = await listen(server, 0);
  const before = Date.now();
  await fetch(`http://127.0.0.1:${port}/search`, { method: "POST", body: JSON.stringify({ text: "x", k: 1 }) });
  server.closeAllConnections(); server.close(); await encoder.close(); await shard.close();
  const deadline = Number(seen);
  assert.ok(deadline >= before + 2900 && deadline <= Date.now() + 3000, `deadline ${deadline} should be about now + 3000 ms`);
});

test("k is capped at 12, the range where the merged top k is exact", async () => {
  const { call, stop } = await setup([shardAnswer([cand("marqo", "1", 0.5, 1)])]);
  assert.equal((await call("/search", { text: "ok", k: 12 })).status, 200);
  const r = await call("/search", { text: "ok", k: 13 });
  assert.equal(r.status, 400);
  assert.match(((await r.json()) as any).error, /1 to 12/);
  await stop();
});

test("defaults: 72 candidates per shard, 12 searches in flight, no shard token", () => {
  const c = loadConfig({});
  assert.equal(c.perShard, 72);
  assert.equal(c.maxInflight, 12);
  assert.equal(c.shardToken, undefined);
  assert.equal(loadConfig({ MAX_INFLIGHT: "0" }).maxInflight, 0);
  assert.equal(loadConfig({ SHARD_TOKEN: "s3cret" }).shardToken, "s3cret");
});

test("adaptive hedge: when a shard's recent p90 is above HEDGE_MS the hedge waits for it, so the second replica is not asked", async () => {
  const slowA = { n: 0 }, fastB = { n: 0 };
  const a = await fake(counting([cand("marqo", "1", 0.5, 1)], slowA, 80));
  const b = await fake(counting([cand("marqo", "1", 0.5, 1)], fastB));
  const cfg: Config = { host: "127.0.0.1", port: 0, encoderUrl: "http://unused", shardGroups: [[a.url, b.url]], shardTimeoutMs: 1000, encoderTimeoutMs: 1000, theta: 0.098, perShard: 72, hedgeMs: 20 };
  const usual = new LatencyWindow(200);
  for (let i = 0; i < 200; i++) usual.record(150);           // this shard usually takes about 150 ms
  const adaptive = await queryShard(cfg.shardGroups[0], "/search", {}, cfg, 0, "t1", usual);
  assert.equal(adaptive.hedged, false);
  assert.equal(fastB.n, 0, "the second replica was asked although the first was within its usual time");
  const fixed = await queryShard(cfg.shardGroups[0], "/search", {}, cfg, 0, "t2");   // no history: the 20 ms floor, so it hedges
  assert.equal(fixed.hedged, true);
  assert.equal(fastB.n, 1);
  const fresh = new LatencyWindow(200);
  await queryShard(cfg.shardGroups[0], "/search", {}, { ...cfg, hedgeMs: 0 }, 0, "t3", fresh);
  assert.equal(fresh.count, 1, "a successful answer is recorded in the shard's window");
  await a.close(); await b.close();
});

test("the shard token goes to every shard request (search and health) as x-genkart-token, never to the encoder", async () => {
  const seen = { encoder: [] as (string | undefined)[], shard: [] as (string | undefined)[] };
  const encoder = await fake((_b, h) => { seen.encoder.push(h?.["x-genkart-token"] as string | undefined); return { status: 200, body: { vectors: [[0.1, 0.2]] } }; });
  const shard = await fake((_b, h) => { seen.shard.push(h?.["x-genkart-token"] as string | undefined); return { status: 200, body: { candidates: { marqo: [cand("marqo", "1", 0.5, 1)] } } }; });
  const healthSeen: (string | undefined)[] = [];
  const shardHealth = http.createServer((req, res) => { healthSeen.push(req.headers["x-genkart-token"] as string | undefined); req.resume(); res.end("{}"); });
  await new Promise<void>((r) => shardHealth.listen(0, "127.0.0.1", () => r()));
  const healthUrl = `http://127.0.0.1:${(shardHealth.address() as AddressInfo).port}`;
  const base: Config = { host: "127.0.0.1", port: 0, encoderUrl: encoder.url, shardGroups: [[shard.url]], shardTimeoutMs: 500, encoderTimeoutMs: 1000, theta: 0.098, perShard: 72, hedgeMs: 40 };
  for (const token of ["s3cret", undefined]) {
    const server = createRouter({ ...base, shardToken: token });
    const port = await listen(server, 0);
    await (await fetch(`http://127.0.0.1:${port}/search`, { method: "POST", body: JSON.stringify({ text: "x", k: 1 }) })).text();
    server.closeAllConnections(); server.close();
    const hs = createRouter({ ...base, shardGroups: [[healthUrl]], shardToken: token });
    const hp = await listen(hs, 0);
    await (await fetch(`http://127.0.0.1:${hp}/health`)).text();
    hs.closeAllConnections(); hs.close();
  }
  await encoder.close(); await shard.close(); shardHealth.closeAllConnections(); shardHealth.close();
  assert.deepEqual(seen.shard, ["s3cret", undefined]);
  assert.deepEqual(healthSeen, ["s3cret", undefined]);
  assert.deepEqual(seen.encoder, [undefined, undefined]);
});

test("errors: the caller gets shard numbers and a generic reason only; addresses and the exception go to the router's log", async () => {
  const lines: string[] = [];
  const realLog = console.log;
  console.log = (x: unknown) => { lines.push(String(x)); };
  let bodies: string[] = [];
  let shardUrls: string[] = [];
  let encUrl = "";
  try {
    // 1) partial: shard 1 fails; 2) none answer: 503; 3) the encoder fails: 502
    const good = await fake(() => ({ status: 200, body: { candidates: { marqo: [cand("marqo", "1", 0.5, 1)] } } }));
    const bad = await fake(() => ({ status: 500, body: { error: "disk on fire at 10.0.0.7" } }));
    const encoder = await fake(() => ({ status: 200, body: { vectors: [[0.1, 0.2]] } }));
    const badEncoder = await fake(() => ({ status: 500, body: {} }));
    shardUrls = [good.url, bad.url];
    encUrl = badEncoder.url;
    const base: Config = { host: "127.0.0.1", port: 0, encoderUrl: encoder.url, shardGroups: [[good.url], [bad.url]], shardTimeoutMs: 500, encoderTimeoutMs: 1000, theta: 0.098, perShard: 72, hedgeMs: 40 };
    const run = async (cfg: Config) => {
      const server = createRouter(cfg);
      const port = await listen(server, 0);
      const r = await fetch(`http://127.0.0.1:${port}/search`, { method: "POST", body: JSON.stringify({ text: "x", k: 1 }) });
      const text = await r.text();
      server.closeAllConnections(); server.close();
      return { status: r.status, text };
    };
    const partial = await run(base);
    const none = await run({ ...base, shardGroups: [[bad.url], [bad.url]] });
    const enc = await run({ ...base, encoderUrl: badEncoder.url });
    bodies = [partial.text, none.text, enc.text];
    assert.equal(partial.status, 200);
    assert.deepEqual(JSON.parse(partial.text).failed, [1]);
    assert.equal(none.status, 503);
    assert.deepEqual(JSON.parse(none.text), { error: "no shard answered", failed: [0, 1] });
    assert.equal(enc.status, 502);
    assert.deepEqual(JSON.parse(enc.text), { error: "encoder or router failure" });
    await good.close(); await bad.close(); await encoder.close(); await badEncoder.close();
  } finally {
    console.log = realLog;
  }
  for (const b of bodies) {
    assert.doesNotMatch(b, /127\.0\.0\.1|http:|answered 500|Error/, `a client answer leaks detail: ${b}`);
  }
  const log = lines.join("\n");
  assert.ok(log.includes(shardUrls[1]), "the failed shard's address is missing from the log");
  assert.ok(log.includes(`${encUrl}/encode answered 500`), "the encoder failure is missing from the log");
});

test("a replica answering 200 without usable candidates counts as failed: the next replica is asked, and a shard with no good replica is just missing", async () => {
  const good = shardAnswer([cand("marqo", "1", 0.14, 1)]);
  const noCandidates: Handler = () => ({ status: 200, body: { error: "warming up" } });
  const badCandidate: Handler = () => ({ status: 200, body: { candidates: { marqo: [{ source: "marqo", id: 5, score: "high", cluster: 1, title: "t" }] } } });
  const failover = await setupGroups([[noCandidates, good], [badCandidate, good]]);
  const j: any = await (await failover.call("/search", { text: "x" })).json();
  assert.equal(j.partial, false);
  assert.deepEqual(j.shards, { total: 2, ok: 2, failed: 0, failovers: 2, hedged: 0 });
  await failover.stop();
  const missing = await setupGroups([[noCandidates], [good]]);
  const r = await missing.call("/search", { text: "x" });
  const m: any = await r.json();
  assert.equal(r.status, 200, "one malformed shard must not turn the whole search into a 502");
  assert.deepEqual([m.partial, m.failed], [true, [0]]);
  assert.deepEqual(m.results.map((x: any) => x.id), ["1"]);
  await missing.stop();
});

test("a caller hanging up mid-search aborts the encoder call; every in-flight slot (400, oversize, hang-up, success) is freed exactly once", async () => {
  let encoderCalls = 0;
  let encoderCutOff = 0;
  const encoder = http.createServer((req, res) => {
    encoderCalls++;
    req.resume();
    const t = setTimeout(() => { res.writeHead(200, { "content-type": "application/json" }); res.end(JSON.stringify({ vectors: [[0.1, 0.2]] })); }, 300);
    res.on("close", () => { if (!res.writableFinished) { encoderCutOff++; clearTimeout(t); } });
  });
  await new Promise<void>((r) => encoder.listen(0, "127.0.0.1", () => r()));
  const shard = await fake(shardAnswer([cand("marqo", "1", 0.5, 1)]));
  const cfg: Config = { host: "127.0.0.1", port: 0, encoderUrl: `http://127.0.0.1:${(encoder.address() as AddressInfo).port}`, shardGroups: [[shard.url]], shardTimeoutMs: 500, encoderTimeoutMs: 2000, theta: 0.098, perShard: 32, hedgeMs: 40, maxInflight: 1 };
  const lines: string[] = [];
  const realLog = console.log;
  console.log = (x: unknown) => { lines.push(String(x)); };
  const server = createRouter(cfg);
  const port = await listen(server, 0);
  const post = (body: string, signal?: AbortSignal) => fetch(`http://127.0.0.1:${port}/search`, { method: "POST", body, signal });
  try {
    // the caller gives up after 50 ms; the encoder (300 ms) must see its request dropped, well before it would have answered
    const ac = new AbortController();
    const t0 = performance.now();
    setTimeout(() => ac.abort(), 50);
    await assert.rejects(post(JSON.stringify({ text: "x", k: 1 }), ac.signal));
    while (encoderCutOff === 0 && performance.now() - t0 < 1000) await new Promise((r) => setTimeout(r, 5));
    assert.equal(encoderCutOff, 1, "the encoder call went on after the caller hung up");
    assert.ok(performance.now() - t0 < 250, "the encoder call was not stopped promptly");
    await new Promise((r) => setTimeout(r, 20));
    assert.ok(lines.some((l) => l.includes('"status":499')), "the hang-up is not in the log");
    // 400s and an oversize body free their slot too, and nothing is freed twice
    for (let i = 0; i < 3; i++) assert.equal((await post(JSON.stringify({ text: "" }))).status, 400);
    await post("x".repeat(10000)).then((r) => r.text(), () => null);
    await new Promise((r) => setTimeout(r, 20));
    const calls = encoderCalls;
    const burst = await Promise.all([0, 1, 2].map(() => post(JSON.stringify({ text: "x", k: 1 })).then(async (r) => { await r.text(); return r.status; })));
    assert.deepEqual(burst.sort(), [200, 429, 429], "with a limit of 1 exactly one search runs: a slot was freed twice (or never)");
    assert.equal(encoderCalls, calls + 1);
    assert.equal((await post(JSON.stringify({ text: "x", k: 1 }))).status, 200);
  } finally {
    console.log = realLog;
    server.closeAllConnections(); server.close(); encoder.closeAllConnections(); encoder.close(); await shard.close();
  }
});
