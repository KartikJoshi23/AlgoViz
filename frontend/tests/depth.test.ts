import { describe, expect, it } from "vitest";

import { DepthRing } from "@/lib/store/depth";
import type { BookPayload } from "@/lib/ws/types";

function book(bids: number[], asks: number[], mid = 100): BookPayload {
  return {
    symbol: "TEST",
    ts_ms: 0,
    bids: [[mid - 0.01, 1]],
    asks: [[mid + 0.01, 1]],
    profile: { band_bps: 20, bins: bids.length, bids, asks },
    mid,
    microprice: mid,
    spread_bps: 0.2,
    imbalance_l1: 0,
    imbalance_w: 0,
    ofi_1s: 0,
    liquidity_10bps: 0,
    levels: 2,
    update_id: 1,
  };
}

describe("DepthRing", () => {
  it("lays bids nearest-first left of centre and asks right, and scrolls with head", () => {
    const ring = new DepthRing(4, 3); // 2 bins per side, 3 slices
    expect(ring.push(book([1, 2], [3, 4]))).toBe(true);
    expect(Array.from(ring.data.slice(0, 4))).toEqual([2, 1, 3, 4]);
    expect(ring.at(0)).toBe(2); // farthest bid bin
    expect(ring.at(1)).toBe(1); // nearest bid bin
    expect(ring.at(2)).toBe(3); // nearest ask bin
    expect(ring.binOffsetBps(1)).toBeCloseTo(-5); // half a 10 bps bin from mid
    expect(ring.binOffsetBps(2)).toBeCloseTo(5);

    ring.push(book([5, 6], [7, 8]));
    ring.push(book([9, 10], [11, 12]));
    ring.push(book([13, 14], [15, 16])); // wraps to row 0
    expect(ring.head).toBe(4);
    expect(Array.from(ring.data.slice(0, 4))).toEqual([14, 13, 15, 16]);
    expect(ring.at(1, 0)).toBe(13); // newest
    expect(ring.at(1, 1)).toBe(9); // one frame older
    expect(Number.isNaN(ring.at(1, 3))).toBe(true); // beyond retained slices
  });

  it("rejects payloads without a matching profile and smooths the max", () => {
    const ring = new DepthRing(4, 2);
    expect(ring.push({ ...book([1, 2], [3, 4]), profile: null })).toBe(false);
    expect(ring.push(book([1, 2, 3], [3, 4, 5]))).toBe(false); // wrong bin count
    ring.push(book([1, 10], [1, 20]));
    expect(ring.maxDepth).toBe(20);
    ring.push(book([1, 0], [1, 0]));
    expect(ring.maxDepth).toBeGreaterThan(15); // EWMA, not a jump to 0
    ring.clear();
    expect(ring.head).toBe(0);
    expect(ring.maxDepth).toBe(0);
  });
});
