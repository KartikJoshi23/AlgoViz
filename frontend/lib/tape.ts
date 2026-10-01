import type { TradePayload } from "@/lib/ws/types";

/** Fills this close on one side are one taker order walking the book. */
export const SWEEP_MS = 100;

export interface Print {
  key: number;
  to: number; // newest fill (ms): the group's anchor
  from: number; // earliest fill (ms)
  side: "buy" | "sell";
  qty: number;
  notional: number;
  fills: number;
  lo: number;
  hi: number;
}

/**
 * Newest-first prints: consecutive same-side fills within `SWEEP_MS` of the
 * group's newest fill merge into one at their VWAP (`notional / qty`).
 * Anchored, not chained, so steady one-sided flow still reads as separate prints.
 */
export function aggregatePrints(trades: TradePayload[]): Print[] {
  const out: Print[] = [];
  for (let i = trades.length - 1; i >= 0; i -= 1) {
    const t = trades[i]!;
    const last = out[out.length - 1];
    if (last && last.side === t.side && last.to - t.ts_ms <= SWEEP_MS) {
      last.qty += t.qty;
      last.notional += t.qty * t.price;
      last.fills += 1;
      last.from = t.ts_ms;
      last.lo = Math.min(last.lo, t.price);
      last.hi = Math.max(last.hi, t.price);
    } else {
      out.push({
        key: t.trade_id,
        to: t.ts_ms,
        from: t.ts_ms,
        side: t.side,
        qty: t.qty,
        notional: t.qty * t.price,
        fills: 1,
        lo: t.price,
        hi: t.price,
      });
    }
  }
  return out;
}
