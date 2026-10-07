import { cumulative } from "@/components/charts/Strip";
import { HeatRing } from "@/lib/store/heat";
import { aggregatePrints } from "@/lib/tape";
import type { BookPayload, HeatColumn, TradePayload } from "@/lib/ws/types";

const book = (mid: number, bids: number[], asks: number[], ts = 0): BookPayload =>
  ({ mid, ts_ms: ts, profile: { band_bps: 20, bins: bids.length, bids, asks } }) as unknown as BookPayload;
const trade = (id: number, ts: number, side: "buy" | "sell", qty: number, price = 100): TradePayload =>
  ({ trade_id: id, ts_ms: ts, side, qty, price }) as TradePayload;

describe("HeatRing", () => {
  it("stores resting quantity per bin by differencing the cumulative profile", () => {
    const h = new HeatRing(4, 3);
    expect(h.push(book(100, [1, 1, 4], [2, 5, 5]))).toBe(true);
    const s = h.slot(0);
    expect(Array.from(h.qty.subarray(s * 6, s * 6 + 6))).toEqual([1, 0, 3, 2, 3, 0]);
    expect(h.peak).toBe(3); // the first column's largest bin seeds the colour scale
    expect(h.push(book(100, [1], [1]))).toBe(false); // profile with a different bin count
  });

  it("wraps after capacity and addresses columns by age", () => {
    const h = new HeatRing(2, 1);
    for (const mid of [100, 101, 102]) h.push(book(mid, [1], [1]));
    expect(h.head).toBe(3);
    expect(h.mid[h.slot(0)]).toBe(102);
    expect(h.mid[h.slot(1)]).toBe(101);
    expect(h.slot(2)).toBe(-1); // overwritten
  });

  it("folds trades into the newest column and scales bubbles by columns that traded", () => {
    const h = new HeatRing(8, 1);
    h.addTrades([trade(1, 0, "buy", 1)]); // no column yet: ignored
    h.push(book(100, [1], [1]));
    h.addTrades([trade(2, 0, "buy", 2, 100), trade(3, 0, "sell", 1, 99)]);
    h.addTrades([trade(4, 0, "buy", 2, 102)]);
    const c = h.slot(0);
    expect(h.buyQty[c]).toBe(4);
    expect(h.buyNotional[c]! / h.buyQty[c]!).toBe(101); // VWAP of the buys
    expect(h.sellQty[c]).toBe(1);
    h.push(book(100, [1], [1])); // closes the traded column
    expect(h.flow).toBe(5);
    h.push(book(100, [1], [1])); // an empty column must not shrink the reference
    expect(h.flow).toBe(5);
  });

  it("backfills each second of server history as five 5 Hz columns, prints in the middle one", () => {
    const h = new HeatRing(20, 2);
    const second = (ts: number, mid: number, buy: number): HeatColumn => ({
      ts_ms: ts,
      mid,
      profile: { band_bps: 20, bins: 2, bids: [1, 3], asks: [2, 2] },
      buy_qty: buy,
      buy_notional: buy * mid,
      sell_qty: 0,
      sell_notional: 0,
    });
    h.backfill([second(1000, 100, 2), second(2000, 101, 0)]);
    expect(h.head).toBe(10);
    expect(Array.from({ length: 10 }, (_, age) => h.ts[h.slot(9 - age)])).toEqual([200, 400, 600, 800, 1000, 1200, 1400, 1600, 1800, 2000]);
    const s = h.slot(0);
    expect(Array.from(h.qty.subarray(s * 4, s * 4 + 4))).toEqual([1, 2, 2, 0]); // differenced, as live frames are
    const bought = Array.from({ length: 10 }, (_, age) => h.buyQty[h.slot(9 - age)]);
    expect(bought).toEqual([0, 0, 2, 0, 0, 0, 0, 0, 0, 0]);
    expect(h.mid[h.slot(0)]).toBe(101);
  });
});

describe("aggregatePrints", () => {
  it("merges one side's fills within the sweep window, newest first, at their VWAP", () => {
    const prints = aggregatePrints([
      trade(1, 1000, "sell", 1, 100),
      trade(2, 1040, "buy", 1, 101),
      trade(3, 1050, "buy", 3, 102),
      trade(4, 1060, "buy", 1, 103),
    ]);
    expect(prints.map((p) => [p.side, p.fills, p.qty])).toEqual([
      ["buy", 3, 5],
      ["sell", 1, 1],
    ]);
    expect(prints[0]!.notional / prints[0]!.qty).toBeCloseTo(102);
    expect([prints[0]!.lo, prints[0]!.hi]).toEqual([101, 103]);
  });

  it("anchors on the group's newest fill, so steady one-sided flow is not chained into one print", () => {
    const fills = Array.from({ length: 6 }, (_, i) => trade(i, 1000 + i * 60, "buy", 1));
    const prints = aggregatePrints(fills);
    expect(prints.length).toBe(3); // 60 ms apart: pairs merge, chains don't
    expect(prints.every((p) => p.to - p.from <= 100)).toBe(true);
  });
});

describe("cumulative", () => {
  it("runs a sum that starts at the first value and treats later gaps as zero", () => {
    const out = cumulative(new Float64Array([Number.NaN, 1, -2, Number.NaN, 3]));
    expect(Number.isNaN(out[0]!)).toBe(true);
    expect(Array.from(out.subarray(1))).toEqual([1, -1, -1, 2]);
  });
});
