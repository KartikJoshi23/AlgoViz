import { RingF64, RingTable } from "@/lib/store/rings";

describe("RingF64", () => {
  it("keeps the last N values in order with a monotonic head", () => {
    const r = new RingF64(4);
    expect(r.length).toBe(0);
    expect(Number.isNaN(r.latest)).toBe(true);
    for (let i = 1; i <= 6; i += 1) r.push(i);
    expect(r.head).toBe(6);
    expect(r.length).toBe(4);
    expect(r.toArray()).toEqual([3, 4, 5, 6]);
    expect(r.at(0)).toBe(3);
    expect(r.latest).toBe(6);
    const out = new Float32Array(2);
    expect(r.copyTo(out)).toBe(2);
    expect(Array.from(out)).toEqual([5, 6]);
    r.clear();
    expect(r.length).toBe(0);
    expect(r.head).toBe(0);
  });
});

describe("RingTable", () => {
  it("pushes rows column-wise and maps nulls to NaN", () => {
    const t = new RingTable(["ts_ms", "close"] as const, 3);
    t.pushRow({ ts_ms: 1, close: 10 });
    t.pushRow({ ts_ms: 2, close: null });
    expect(t.length).toBe(2);
    expect(t.latest("ts_ms")).toBe(2);
    expect(Number.isNaN(t.latest("close"))).toBe(true);
    expect(t.head).toBe(2);
  });
});
