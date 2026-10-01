import type { BookPayload } from "@/lib/ws/types";

export const DEPTH_SLICES = 96; // time slices kept (≈ 19 s at 5 Hz)
export const DEPTH_BINS = 128; // price bins across the band (64 per side)

/**
 * Depth-history ring for the liquidity terrain.
 *
 * Row-major `Float32Array` of `slices × bins`: each row is one book frame's
 * cumulative depth profile — bids nearest-first to the left of centre, asks
 * nearest-first to the right — so the array uploads straight into an R32F
 * texture. Rows are written at `head % slices`; the shader scrolls with the
 * `head` uniform instead of the CPU shifting memory.
 */
export class DepthRing {
  readonly bins: number;
  readonly slices: number;
  readonly data: Float32Array;
  head = 0;
  bandBps = 20;
  /** Smoothed per-row maximum used to normalise heights (avoids jumpy rescaling). */
  maxDepth = 0;

  constructor(bins = DEPTH_BINS, slices = DEPTH_SLICES) {
    this.bins = bins;
    this.slices = slices;
    this.data = new Float32Array(bins * slices);
  }

  push(book: BookPayload): boolean {
    const p = book.profile;
    if (!p || p.bins * 2 !== this.bins) return false;
    const per = p.bins;
    const base = (this.head % this.slices) * this.bins;
    for (let i = 0; i < per; i += 1) {
      this.data[base + per - 1 - i] = p.bids[i] ?? 0;
      this.data[base + per + i] = p.asks[i] ?? 0;
    }
    const rowMax = Math.max(p.bids[per - 1] ?? 0, p.asks[per - 1] ?? 0);
    this.maxDepth = this.head === 0 ? rowMax : this.maxDepth + 0.08 * (rowMax - this.maxDepth);
    this.bandBps = p.band_bps;
    this.head += 1;
    return true;
  }

  /** Depth at (bin, age) where age 0 is the newest row; NaN if not written yet. */
  at(bin: number, age = 0): number {
    if (age >= this.head || age >= this.slices || bin < 0 || bin >= this.bins) return Number.NaN;
    const row = (this.head - 1 - age) % this.slices;
    return this.data[row * this.bins + bin] ?? Number.NaN;
  }

  /** Signed offset from mid (bps) at the centre of `bin`. */
  binOffsetBps(bin: number): number {
    const per = this.bins / 2;
    const step = this.bandBps / per;
    return bin < per ? -((per - bin - 0.5) * step) : (bin - per + 0.5) * step;
  }

  clear(): void {
    this.data.fill(0);
    this.head = 0;
    this.maxDepth = 0;
  }
}
