import { selectBars, useStore } from "@/lib/store";
import type { ServerMessage } from "@/lib/ws/types";

const columns = [
  "ts_ms",
  "open",
  "high",
  "low",
  "close",
  "volume",
  "buy_volume",
  "trade_count",
  "spread_bps",
  "microprice",
  "imbalance_w",
  "ofi",
  "velocity",
  "volatility_bps",
  "vwap",
  "spread_z",
  "ofi_z",
  "vol_z",
];
const row = (ts: number, close: number) => [ts, close, close, close, close, 1, 0.5, 3, 0.01, close, 0, 0, 1, 2, close, null, null, null];

function snapshot(rows: (number | null)[][]): ServerMessage {
  return {
    type: "snapshot",
    ts: 0,
    symbol: "BTCUSDT",
    data: {
      symbol: "BTCUSDT",
      features: { symbol: "BTCUSDT", ts_ms: 0, source: "synthetic", warmed_up: false } as never,
      book: null,
      bars: { columns, rows },
      trades: [],
      regime: {
        symbol: "BTCUSDT",
        label: "calm",
        direction: 0,
        trend: "flat",
        trend_t: 0,
        probs: {},
        source: "fallback",
        model_version: 0,
        bars_seen: 0,
      },
      signals: [],
      prediction: null,
      source_status: { symbol: "BTCUSDT", status: "connected", detail: "", source: "synthetic" },
      heat: [],
    },
  };
}

describe("store.applyFrame", () => {
  beforeEach(() => useStore.getState().resetMarket());

  it("hands readers an empty bar table until the head moves, so hydration matches the server", () => {
    const s = useStore.getState();
    s.bars.pushRow({ ts_ms: 1000, close: 100 }); // mutated in place, before any React-visible update
    expect(selectBars(useStore.getState()).bars.length).toBe(0);
    s.applyFrame(snapshot([row(1000, 100), row(2000, 101)]));
    const { bars, head } = selectBars(useStore.getState());
    expect(head).toBeGreaterThan(0);
    expect(bars.length).toBe(2);
  });

  it("hydrates bars from a snapshot and appends only newer bars", () => {
    const s = useStore.getState();
    s.applyFrame(snapshot([row(1000, 100), row(2000, 101)]));
    expect(useStore.getState().hydrated).toBe(true);
    expect(useStore.getState().bars.length).toBe(2);
    expect(useStore.getState().lastBarTs).toBe(2000);

    const arrived = useStore.getState().lastBarAt;
    expect(arrived).toBeGreaterThan(0);
    s.applyFrame({ type: "bar", ts: 0, symbol: "BTCUSDT", data: { columns, rows: [row(2000, 101)] } });
    expect(useStore.getState().bars.length).toBe(2); // duplicate ignored
    expect(useStore.getState().lastBarAt).toBe(arrived); // …and doesn't count as fresh data
    s.applyFrame({ type: "bar", ts: 0, symbol: "BTCUSDT", data: { columns, rows: [row(3000, 102)] } });
    expect(useStore.getState().bars.length).toBe(3);
    expect(useStore.getState().bars.latest("close")).toBe(102);
    expect(useStore.getState().barsHead).toBe(3);
  });

  it("hydrates from a backend that predates heatmap history (frontend and backend deploy separately)", () => {
    const old = snapshot([row(1000, 100)]);
    delete (old.data as { heat?: unknown }).heat;
    useStore.getState().applyFrame(old);
    expect(useStore.getState().hydrated).toBe(true);
    expect(useStore.getState().heat.head).toBe(0);
  });

  it("raises toasts for alerts and high-priority signal activations", () => {
    const s = useStore.getState();
    s.applyFrame({
      type: "alert",
      ts: 0,
      symbol: "BTCUSDT",
      data: {
        id: 1,
        rule_id: 1,
        rule_name: "Wide",
        symbol: "BTCUSDT",
        priority: "high",
        message: "m",
        field: "spread_z",
        value: 3,
        threshold: 2,
        triggered_at: "t",
      },
    });
    s.applyFrame({
      type: "signals",
      ts: 0,
      symbol: "BTCUSDT",
      data: {
        symbol: "BTCUSDT",
        active: [],
        transitions: [
          {
            ts_ms: 1,
            kind: "activated",
            duration_s: null,
            rule_id: "x",
            name: "X",
            priority: "high",
            message: "",
            action: "",
            impact: "",
            tags: [],
            activated_at_ms: 1,
            seconds_active: 0,
            values: {},
          },
        ],
      },
    });
    const st = useStore.getState();
    expect(st.alerts).toHaveLength(1);
    expect(st.signalFeed).toHaveLength(1);
    expect(st.ui.toasts.map((t) => t.tone)).toEqual(["serious", "serious"]); // high-priority alert, high-priority signal
  });

  it("records hello metadata and connection channels", () => {
    useStore.getState().applyFrame({
      type: "hello",
      ts: 0,
      symbol: null,
      data: {
        version: "3.0.0",
        symbols: ["BTCUSDT", "ETHUSDT"],
        default_symbol: "BTCUSDT",
        source: "replay",
        time_scale: 2,
        channels: ["features"],
        subscribed: ["features", "bars"],
        bar_columns: columns,
        server_time_ms: Date.now() + 500,
      },
    });
    const c = useStore.getState().connection;
    expect(c.symbols).toEqual(["BTCUSDT", "ETHUSDT"]);
    expect(c.source).toBe("replay");
    expect(c.channels).toEqual(["features", "bars"]);
    expect(Math.abs(c.serverOffsetMs - 500)).toBeLessThan(200);
  });
});

describe("store trade dedupe", () => {
  it("drops trades that were already delivered (overlapping frames)", () => {
    const s = useStore.getState();
    s.resetMarket();
    const t = (id: number) => ({ ts_ms: id, price: 1, qty: 1, side: "buy" as const, trade_id: id });
    s.applyFrame({ type: "trades", ts: 0, symbol: "BTCUSDT", data: [t(1), t(2), t(3)] });
    s.applyFrame({ type: "trades", ts: 0, symbol: "BTCUSDT", data: [t(2), t(3), t(4)] });
    expect(useStore.getState().trades.map((x) => x.trade_id)).toEqual([1, 2, 3, 4]);
    expect(useStore.getState().lastTradeId).toBe(4);
  });

  it("keeps the tape moving when a source restarts its id sequence", () => {
    const s = useStore.getState();
    s.resetMarket();
    const t = (id: number, ts: number) => ({ ts_ms: ts, price: 1, qty: 1, side: "sell" as const, trade_id: id });
    s.applyFrame({ type: "trades", ts: 0, symbol: "BTCUSDT", data: [t(500, 1_000), t(501, 1_100)] });
    // same ids again, but later in time: a replay that looped, a simulator that restarted
    s.applyFrame({ type: "trades", ts: 0, symbol: "BTCUSDT", data: [t(500, 21_000), t(501, 21_100)] });
    expect(useStore.getState().trades.map((x) => x.ts_ms)).toEqual([1_000, 1_100, 21_000, 21_100]);
  });
});
