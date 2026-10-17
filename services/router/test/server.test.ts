import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import type { AddressInfo } from "node:net";
import { createRouter, listen } from "../src/server.ts";
import type { Config } from "../src/config.ts";

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
