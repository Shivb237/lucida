// Smoke check of the compiled router (dist/), what the machines run: plain JavaScript, so it also covers a Node 22 older than 22.18, which
// cannot run the TypeScript (CI runs it on Node 22; the tests themselves run on Node 24 LTS).
// Starts a fake encoder and one fake shard, runs one search through dist/server.js and checks the answer. Run `npm run build` first.
import http from "node:http";
import assert from "node:assert/strict";
import { createRouter, listen } from "../dist/server.js";
import { loadConfig } from "../dist/config.js";

const fake = (body) => new Promise((resolve) => {
  const s = http.createServer((req, res) => { req.resume(); req.on("end", () => { res.writeHead(200, { "content-type": "application/json" }); res.end(JSON.stringify(body)); }); });
  s.listen(0, "127.0.0.1", () => resolve(s));
});
const url = (s) => `http://127.0.0.1:${s.address().port}`;

const encoder = await fake({ vectors: [[0.1, 0.2]] });
const shard = await fake({ candidates: { marqo: [{ source: "marqo", id: "1", score: 0.5, cluster: 1, title: "t1" }] } });
const cfg = loadConfig({ ENCODER_URL: url(encoder), SHARD_URLS: url(shard), PORT: "0" });
assert.equal(cfg.perShard, 72);
const router = createRouter(cfg);
const port = await listen(router, 0);
const r = await fetch(`http://127.0.0.1:${port}/search`, { method: "POST", body: JSON.stringify({ text: "red gown", k: 1 }) });
const j = await r.json();
assert.equal(r.status, 200);
assert.deepEqual(j.results.map((x) => x.id), ["1"]);
router.closeAllConnections(); router.close(); encoder.close(); shard.close();
console.log(`dist smoke ok on node ${process.version}`);
