import test from "node:test";
import assert from "node:assert/strict";
import { LatencyWindow, hedgeDelay } from "../src/hedge.ts";

test("the window says nothing until it has enough answers, then gives the p90", () => {
  const w = new LatencyWindow(200, 20);
  for (let i = 1; i <= 19; i++) w.record(i);
  assert.equal(w.quantile(0.9), undefined);
  w.record(20);
  assert.equal(w.quantile(0.9), 18);            // nearest rank: the 18th of 1..20
});

test("the window keeps only the newest answers", () => {
  const w = new LatencyWindow(10, 1);
  for (let i = 0; i < 10; i++) w.record(1000);
  for (let i = 0; i < 10; i++) w.record(5);
  assert.equal(w.count, 10);
  assert.equal(w.quantile(0.9), 5);             // the slow old answers have all dropped out
});

test("bad samples are ignored", () => {
  const w = new LatencyWindow(10, 1);
  w.record(NaN); w.record(-1); w.record(Infinity);
  assert.equal(w.count, 0);
});

test("the hedge delay is the larger of HEDGE_MS and the shard's p90; HEDGE_MS=0 keeps hedging off", () => {
  const w = new LatencyWindow(200, 20);
  assert.equal(hedgeDelay(40, w), 40);          // no history yet: the floor
  for (let i = 0; i < 50; i++) w.record(10);
  assert.equal(hedgeDelay(40, w), 40);          // a fast shard: still the floor, never less
  for (let i = 0; i < 200; i++) w.record(120);
  assert.equal(hedgeDelay(40, w), 120);         // a slow shard: wait for its usual slow answer before doubling its load
  assert.equal(hedgeDelay(0, w), 0);
  assert.equal(hedgeDelay(40), 40);
});
