// Adaptive hedging. A fixed hedge delay (say 40 ms) is too short when a shard is simply slow today: every search would then ask
// both replicas and double the shard load for nothing. So each shard keeps its own recent successful answer times, and the hedge
// waits until that shard's usual slow answer (the 90th percentile) has passed, never less than HEDGE_MS.

export class LatencyWindow {
  private readonly buf: number[] = [];
  private at = 0;
  readonly size: number;
  readonly minSamples: number;
  constructor(size = 200, minSamples = 20) {
    this.size = size;
    this.minSamples = minSamples;
  }

  record(ms: number): void {
    if (!Number.isFinite(ms) || ms < 0) return;
    if (this.buf.length < this.size) this.buf.push(ms);
    else this.buf[this.at] = ms;        // ring buffer: the oldest answer time drops out
    this.at = (this.at + 1) % this.size;
  }

  get count(): number {
    return this.buf.length;
  }

  // the q-quantile of the window (nearest rank), or undefined while there are too few answers to say anything
  quantile(q: number): number | undefined {
    if (this.buf.length < this.minSamples) return undefined;
    const sorted = [...this.buf].sort((a, b) => a - b);
    return sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil(q * sorted.length) - 1))];
  }
}

// how long to wait before asking the next replica too. 0 = hedging off (HEDGE_MS=0 still turns it off)
export function hedgeDelay(floorMs: number, w?: LatencyWindow): number {
  if (floorMs <= 0) return 0;
  const p90 = w?.quantile(0.9);
  return p90 === undefined ? floorMs : Math.max(floorMs, p90);
}
