import type { BookPayload, TradePayload } from "@/lib/ws/types";

export const HEAT_COLUMNS = 900; // 3 minutes of book frames at 5 Hz
export const HEAT_BINS_PER_SIDE = 64; // matches the server's BOOK_PROFILE_BINS

/**
 * Liquidity-heatmap history.
 *
 * One column per book frame: the resting quantity in each price bin (the
 * server's cumulative depth profile, differenced), the frame's mid and band
 * (so the bins can be placed at absolute prices), and the trades that printed
 * until the next frame, split by aggressor side. Columns are written at
 * `head % capacity`; nothing shifts in memory.
 */
export class HeatRing {
  readonly capacity: number;
  readonly perSide: number;
  /** capacity × (2 × perSide): bids nearest-first, then asks nearest-first. */
  readonly qty: Float32Array;
  readonly mid: Float64Array;
  readonly bandBps: Float32Array;
  readonly ts: Float64Array;
  readonly buyQty: Float32Array;
  readonly sellQty: Float32Array;
  readonly buyNotional: Float64Array;
  readonly sellNotional: Float64Array;
  head = 0;
  /** Smoothed per-column peak bin quantity: the colour scale's reference. */
  peak = 0;
  /** Smoothed traded quantity of the columns that traded: the bubble scale's reference. */
  flow = 0;

  constructor(capacity = HEAT_COLUMNS, perSide = HEAT_BINS_PER_SIDE) {
    this.capacity = capacity;
    this.perSide = perSide;
    this.qty = new Float32Array(capacity * perSide * 2);
    this.mid = new Float64Array(capacity);
    this.bandBps = new Float32Array(capacity);
    this.ts = new Float64Array(capacity);
    this.buyQty = new Float32Array(capacity);
    this.sellQty = new Float32Array(capacity);
    this.buyNotional = new Float64Array(capacity);
    this.sellNotional = new Float64Array(capacity);
  }

  push(book: BookPayload): boolean {
    const p = book.profile;
    if (!p || p.bins !== this.perSide || !(book.mid > 0)) return false;
    if (this.head > 0) {
      // the previous column is complete: fold its traded quantity into the bubble scale —
      // columns that traded only, or a quiet feed would make every print look huge
      const prev = (this.head - 1) % this.capacity;
      const traded = this.buyQty[prev]! + this.sellQty[prev]!;
      if (traded > 0) this.flow = this.flow === 0 ? traded : this.flow + 0.02 * (traded - this.flow);
    }
    const c = this.head % this.capacity;
    const base = c * this.perSide * 2;
    let colMax = 0;
    const diff = (cum: number[], offset: number) => {
      let prev = 0;
      for (let i = 0; i < this.perSide; i += 1) {
        const v = cum[i] ?? prev;
        const q = Math.max(0, v - prev);
        prev = v;
        this.qty[base + offset + i] = q;
        if (q > colMax) colMax = q;
      }
    };
    diff(p.bids, 0);
    diff(p.asks, this.perSide);
    this.mid[c] = book.mid;
    this.bandBps[c] = p.band_bps;
    this.ts[c] = book.ts_ms;
    this.buyQty[c] = this.sellQty[c] = 0;
    this.buyNotional[c] = this.sellNotional[c] = 0;
    this.peak = this.head === 0 ? colMax : this.peak + 0.02 * (colMax - this.peak);
    this.head += 1;
    return true;
  }

  /** Adds prints to the newest column (they arrived since its book frame). */
  addTrades(trades: TradePayload[]): void {
    if (this.head === 0 || trades.length === 0) return;
    const c = (this.head - 1) % this.capacity;
    let bq = 0;
    let bn = 0;
    let sq = 0;
    let sn = 0;
    for (const t of trades) {
      if (t.side === "buy") {
        bq += t.qty;
        bn += t.qty * t.price;
      } else {
        sq += t.qty;
        sn += t.qty * t.price;
      }
    }
    this.buyQty[c] = this.buyQty[c]! + bq;
    this.buyNotional[c] = this.buyNotional[c]! + bn;
    this.sellQty[c] = this.sellQty[c]! + sq;
    this.sellNotional[c] = this.sellNotional[c]! + sn;
  }

  /** Slot of the column `age` frames back (0 = newest), or -1 if not written. */
  slot(age: number): number {
    if (age < 0 || age >= this.head || age >= this.capacity) return -1;
    return (this.head - 1 - age) % this.capacity;
  }

  clear(): void {
    this.qty.fill(0);
    this.mid.fill(0);
    this.head = 0;
    this.peak = 0;
    this.flow = 0;
  }
}
