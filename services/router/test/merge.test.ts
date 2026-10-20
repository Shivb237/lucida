import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { mergeRoute, byScoreThenId } from "../src/merge.ts";
import type { Cand } from "../src/merge.ts";

const c = (source: string, id: string, score: number, cluster: number): Cand => ({ source, id, score, cluster, title: `t${id}` });

test("a strong general match stays in the general catalogue", () => {
  const out = mergeRoute([{ marqo: [c("marqo", "10", 0.14, 1)], kaggle: [c("kaggle", "5", 0.2, 9)] }], 4, 0.098);
  assert.deepEqual(out.map((x) => x.id), ["10"]);
});

test("a weak general match falls back to specialists, best first", () => {
  const out = mergeRoute([{ marqo: [c("marqo", "10", 0.05, 1)], kaggle: [c("kaggle", "5", 0.11, 9)], myntra2: [c("myntra2", "200001", 0.12, 8)] }], 4, 0.098);
  assert.deepEqual(out.map((x) => x.id), ["200001", "5"]);
});

test("copies of one product are merged and exact ties go to the smaller id, whichever shard they came from", () => {
  const a = { marqo: [c("marqo", "18446616839184971986", 0.15, 7)] };
  const b = { marqo: [c("marqo", "9223372036854775809", 0.15, 7), c("marqo", "42", 0.1, 3)] };
  const out = mergeRoute([a, b], 4, 0.098);
  assert.deepEqual(out.map((x) => x.id), ["9223372036854775809", "42"]);
  assert.equal(byScoreThenId(c("m", "2", 0.1, 1), c("m", "10", 0.1, 2)), -1);
});

test("the same item in two specialist catalogues (one cluster) is shown once", () => {
  const out = mergeRoute([{ marqo: [c("marqo", "10", 0.05, 1)], kaggle: [c("kaggle", "5", 0.12, 9)], myntra2: [c("myntra2", "200001", 0.11, 9), c("myntra2", "200002", 0.1, 4)] }], 4, 0.098);
  assert.deepEqual(out.map((x) => x.id), ["5", "200002"]);
});

test("nothing from any shard gives an empty answer", () => {
  assert.deepEqual(mergeRoute([{}, {}], 4, 0.098), []);
});

const FIXTURE = new URL("../../../data/fixtures/router_cases.json", import.meta.url);
test("identical to the Python reference and to the single process on real cases", { skip: existsSync(FIXTURE) ? false : "run scripts/make_router_fixtures.py first" }, () => {
  const cases = JSON.parse(readFileSync(FIXTURE, "utf8"));
  let same = 0;
  for (const k of cases) {
    const got = mergeRoute(k.shards, k.k, 0.098);
    assert.deepEqual(got.map((x) => x.id), k.expected.map((x: { id: string }) => x.id), `${k.text} / ${k.gender}`);
    assert.deepEqual(got.map((x) => x.source), k.expected.map((x: { source: string }) => x.source));
    assert.deepEqual(got.map((x) => x.id), k.single_process.map((x: { id: string }) => x.id));
    same++;
  }
  assert.ok(same > 100, `only ${same} cases`);
});

// Committed, so it always runs (CI included): synthetic cases with the Python reference's answer, made by
// `.venv/bin/python scripts/make_router_fixtures.py --synthetic` (no data/ needed). Each shard candidate is [id, score, cluster].
const SYNTHETIC = new URL("./fixtures/merge_cases.json", import.meta.url);
test("identical to the Python reference (merge_route) on the committed synthetic cases: ties, big ids, cross-catalogue copies, k 1..12, theta edges", () => {
  type Case = { k: number; theta: number; shards: Record<string, [string, number, number][]>[]; expected: { source: string; id: string; score: number; cluster: number }[] };
  const cases: Case[] = JSON.parse(readFileSync(SYNTHETIC, "utf8"));
  assert.ok(cases.length >= 100, `only ${cases.length} cases`);
  const ks = new Set<number>();
  for (const [n, k] of cases.entries()) {
    const shards = k.shards.map((sh) => Object.fromEntries(Object.entries(sh).map(([src, cs]) => [src, cs.map(([id, score, cluster]) => c(src, id, score, cluster))])));
    const got = mergeRoute(shards, k.k, k.theta);
    assert.deepEqual(got.map(({ source, id, score, cluster }) => ({ source, id, score, cluster })), k.expected, `case ${n} (k ${k.k}, theta ${k.theta})`);
    ks.add(k.k);
  }
  assert.equal(ks.size, 12, "every k from 1 to 12 should be covered");
  assert.ok(cases.some((k) => k.expected.length > 0 && k.expected[0].source !== "marqo"), "no case falls back to the specialists");
});
