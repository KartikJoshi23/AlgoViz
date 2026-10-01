import { reliability, reliabilityFromCurve } from "@/lib/reliability";

// realised: 0 down, 1 flat, 2 up
const o = (p_down: number, p_up: number, realised: number) => ({ p_down, p_up, realised });

describe("reliability", () => {
  it("is perfect when each probability matches how often its class happens", () => {
    // p_up = 0.8 on five predictions, four of which went up: observed 0.8 in the 0.8 bin
    const outcomes = [o(0.1, 0.8, 2), o(0.1, 0.8, 2), o(0.1, 0.8, 2), o(0.1, 0.8, 2), o(0.1, 0.8, 0)];
    const r = reliability(outcomes, "up");
    const bin = r.bins.find((b) => b.n > 0)!;
    expect([bin.lo, bin.n]).toEqual([0.8, 5]);
    expect(bin.predicted).toBeCloseTo(0.8);
    expect(bin.observed).toBeCloseTo(0.8);
    expect(r.ece).toBeCloseTo(0);
    expect(r.pairs).toBe(5);
  });

  it("pools all three classes and scores the multiclass Brier score", () => {
    // one outcome, [down 0.2, flat 0.3, up 0.5], realised up: Brier = 0.04 + 0.09 + 0.25
    const r = reliability([o(0.2, 0.5, 2)], "all");
    expect(r.pairs).toBe(3);
    expect(r.brier).toBeCloseTo(0.38);
    // each class sits in its own bin with a gap of |hit − p|: ECE = (0.2 + 0.3 + 0.5) / 3
    expect(r.ece).toBeCloseTo(1 / 3);
  });

  it("puts a probability of exactly 1 in the last bin and reports nothing for no data", () => {
    expect(reliability([o(0, 1, 2)], "up").bins[9]!.n).toBe(1);
    const empty = reliability([], "all");
    expect([empty.ece, empty.brier, empty.pairs]).toEqual([null, null, 0]);
  });
});

describe("reliabilityFromCurve", () => {
  const curve = {
    down: [{ n: 30, forecast: 0.12, observed: 0.1 }],
    flat: [{ n: 10, forecast: 0.55, observed: 0.6 }],
    up: [
      { n: 20, forecast: 0.14, observed: 0.2 },
      { n: 40, forecast: 0.82, observed: 0.8 },
    ],
  };

  it("reads one class's held-out bins as they are", () => {
    const r = reliabilityFromCurve(curve, "up");
    expect(r.pairs).toBe(60);
    expect(r.bins[8]).toMatchObject({ n: 40, predicted: 0.82, observed: 0.8 });
    expect(r.ece).toBeCloseTo((20 * 0.06 + 40 * 0.02) / 60);
    expect(r.brier).toBeNull();
  });

  it("pools classes by count in the shared bins", () => {
    const r = reliabilityFromCurve(curve, "all");
    const low = r.bins[1]!; // down 0.12 (30) and up 0.14 (20)
    expect(low.n).toBe(50);
    expect(low.predicted).toBeCloseTo((30 * 0.12 + 20 * 0.14) / 50);
    expect(low.observed).toBeCloseTo((30 * 0.1 + 20 * 0.2) / 50);
    expect(r.pairs).toBe(100);
    expect(reliabilityFromCurve(null, "all").ece).toBeNull();
  });
});
