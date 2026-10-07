/**
 * Application store (Zustand).
 *
 * Live market state lives here. High-rate histories (bars) are typed-array
 * rings mutated in place; `barsHead` is the change signal React subscribes
 * to. Everything the WebSocket delivers goes through `applyFrame`.
 */
import { create } from "zustand";
import { createJSONStorage, persist, subscribeWithSelector } from "zustand/middleware";
import { useShallow } from "zustand/react/shallow";

import { DepthRing } from "./depth";
import { HeatRing } from "./heat";
import { RingTable } from "./rings";
import type {
  ActiveSignal,
  AlertPayload,
  BacktestProgress,
  BookPayload,
  Channel,
  FeaturesPayload,
  HelloPayload,
  PredictionPayload,
  RegimePayload,
  ServerMessage,
  SignalTransition,
  StatusPayload,
  TradePayload,
} from "@/lib/ws/types";

export const BAR_COLUMNS = [
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
  "regime", // volatility state, ordinal code: 0 calm … 3 extreme
  "trend", // 0 down, 1 flat, 2 up
] as const;
export type BarCol = (typeof BAR_COLUMNS)[number];

export const BAR_CAPACITY = 600;
/** Bars are contiguous while the engine runs; a longer jump is an outage or restart (mirrors the backend). */
export const SESSION_GAP_MS = 5_000;
export const TRADE_CAPACITY = 1000; // fills; the tape merges sweeps, so it needs depth to fill its rows
export const FEED_CAPACITY = 100;

export type ConnectionStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed";
export type PerfTier = "auto" | "low" | "mid" | "high";
export type MotionPref = "auto" | "full" | "reduced";

export interface Toast {
  id: number;
  tone: "neutral" | "accent" | "good" | "warning" | "serious" | "critical";
  title: string;
  body?: string;
  ttlMs: number;
  createdAt: number;
}

export interface ConnectionState {
  status: ConnectionStatus;
  attempt: number;
  nextRetryAt: number | null;
  latencyMs: number | null;
  serverOffsetMs: number;
  symbol: string;
  symbols: string[];
  source: string;
  timeScale: number;
  channels: Channel[];
  hello: HelloPayload | null;
}

export interface UiPrefs {
  perfTier: PerfTier;
  motion: MotionPref;
  accentIntensity: number; // 0.4 … 1.6
  bookSubscribed: boolean;
  symbol: string | null;
}

export interface AppState {
  connection: ConnectionState;
  features: FeaturesPayload | null;
  featuresHead: number;
  book: BookPayload | null;
  bookHead: number;
  /** Depth-history ring for the terrain (mutated in place; `bookHead` signals updates). */
  depth: DepthRing;
  /** Price × time liquidity history for the heatmap (mutated in place; `bookHead` signals updates). */
  heat: HeatRing;
  trades: TradePayload[];
  tradesHead: number;
  lastTradeId: number;
  bars: RingTable<BarCol>;
  barsHead: number;
  lastBarTs: number;
  /** Local wall-clock time the newest bar arrived. Freshness is judged by arrival, as the
   *  server's feed watchdog does, so replay's historical timestamps don't read as stale. */
  lastBarAt: number;
  regime: RegimePayload | null;
  prediction: PredictionPayload | null;
  signalsActive: ActiveSignal[];
  signalFeed: SignalTransition[];
  alerts: AlertPayload[];
  backtests: Record<number, BacktestProgress>;
  sourceStatus: StatusPayload | null;
  hydrated: boolean;
  ui: {
    paletteOpen: boolean;
    toasts: Toast[];
    detectedTier: Exclude<PerfTier, "auto"> | null;
    reducedMotionOS: boolean;
  };
  prefs: UiPrefs;

  // actions
  applyFrame: (msg: ServerMessage) => void;
  setConnection: (patch: Partial<ConnectionState>) => void;
  resetMarket: () => void;
  addToast: (t: Omit<Toast, "id" | "createdAt" | "ttlMs"> & { ttlMs?: number }) => void;
  dismissToast: (id: number) => void;
  setPaletteOpen: (open: boolean) => void;
  setPrefs: (patch: Partial<UiPrefs>) => void;
  setDetectedTier: (tier: Exclude<PerfTier, "auto">) => void;
  setReducedMotionOS: (v: boolean) => void;
}

let toastSeq = 0;

function rowToRecord(columns: string[], row: (number | null)[]): Partial<Record<BarCol, number | null>> {
  const out: Partial<Record<BarCol, number | null>> = {};
  columns.forEach((c, i) => {
    if ((BAR_COLUMNS as readonly string[]).includes(c)) out[c as BarCol] = row[i] ?? null;
  });
  return out;
}

const initialConnection: ConnectionState = {
  status: "idle",
  attempt: 0,
  nextRetryAt: null,
  latencyMs: null,
  serverOffsetMs: 0,
  symbol: "BTCUSDT",
  symbols: ["BTCUSDT"],
  source: "live",
  timeScale: 1,
  channels: [],
  hello: null,
};

const noopStorage = {
  getItem: () => null,
  setItem: () => undefined,
  removeItem: () => undefined,
};

/**
 * localStorage that only writes when the serialised prefs actually changed.
 * `persist` serialises on *every* `set` (5 Hz market frames included); with
 * two tabs open, the tab that did not change a preference would otherwise keep
 * rewriting its stale copy over the other tab's new value. Cross-tab pickup
 * happens via the `storage` event (see Providers).
 */
let lastWritten: string | null = null;
const prefsStorage = {
  getItem: (k: string) => {
    const v = window.localStorage.getItem(k);
    lastWritten = v;
    return v;
  },
  setItem: (k: string, v: string) => {
    if (v === lastWritten) return;
    lastWritten = v;
    window.localStorage.setItem(k, v);
  },
  removeItem: (k: string) => {
    lastWritten = null;
    window.localStorage.removeItem(k);
  },
};

export const PREFS_STORAGE_KEY = "algoviz.prefs";

export const useStore = create<AppState>()(
  subscribeWithSelector(
    persist(
      (set, get) => ({
        connection: initialConnection,
        features: null,
        featuresHead: 0,
        book: null,
        bookHead: 0,
        depth: new DepthRing(),
        heat: new HeatRing(),
        trades: [],
        tradesHead: 0,
        lastTradeId: 0,
        bars: new RingTable<BarCol>(BAR_COLUMNS, BAR_CAPACITY),
        barsHead: 0,
        lastBarTs: 0,
        lastBarAt: 0,
        regime: null,
        prediction: null,
        signalsActive: [],
        signalFeed: [],
        alerts: [],
        backtests: {},
        sourceStatus: null,
        hydrated: false,
        ui: { paletteOpen: false, toasts: [], detectedTier: null, reducedMotionOS: false },
        prefs: { perfTier: "auto", motion: "auto", accentIntensity: 1, bookSubscribed: true, symbol: null },

        applyFrame: (msg) => {
          const s = get();
          switch (msg.type) {
            case "hello": {
              const d = msg.data;
              set({
                connection: {
                  ...s.connection,
                  hello: d,
                  symbols: d.symbols,
                  source: d.source,
                  timeScale: d.time_scale,
                  channels: d.subscribed as Channel[],
                  serverOffsetMs: d.server_time_ms - Date.now(),
                },
              });
              return;
            }
            case "snapshot": {
              const d = msg.data;
              const bars = s.bars;
              bars.clear();
              s.depth.clear();
              s.heat.clear();
              // the server's last few minutes, so the map starts whole (a backend deployed
              // before this field existed sends none: the map then fills in live, as before)
              s.heat.backfill(d.heat ?? []);
              if (d.book) {
                s.depth.push(d.book);
                s.heat.push(d.book);
              }
              let lastTs = 0;
              for (const row of d.bars.rows) {
                const rec = rowToRecord(d.bars.columns, row);
                bars.pushRow(rec);
                lastTs = rec.ts_ms ?? lastTs;
              }
              set({
                features: d.features,
                featuresHead: s.featuresHead + 1,
                book: d.book ?? null,
                bookHead: s.bookHead + 1,
                trades: d.trades.slice(-TRADE_CAPACITY),
                tradesHead: s.tradesHead + 1,
                lastTradeId: d.trades.length ? Math.max(...d.trades.map((t) => t.trade_id)) : 0,
                barsHead: bars.head,
                lastBarTs: lastTs,
                lastBarAt: lastTs ? Date.now() : 0,
                regime: d.regime,
                prediction: d.prediction ?? null,
                signalsActive: d.signals,
                sourceStatus: d.source_status,
                hydrated: true,
                connection: { ...s.connection, symbol: d.symbol },
              });
              return;
            }
            case "features":
              set({ features: msg.data, featuresHead: s.featuresHead + 1 });
              return;
            case "book":
              s.depth.push(msg.data);
              s.heat.push(msg.data);
              set({ book: msg.data, bookHead: s.bookHead + 1 });
              return;
            case "trades": {
              // Ids are monotonic per symbol, so anything at or below the last id was already
              // seen (snapshot overlap) — unless it is also newer in time: a source that restarted
              // its id sequence must not freeze the tape.
              const lastTs = s.trades.length ? s.trades[s.trades.length - 1]!.ts_ms : 0;
              const fresh = msg.data.filter((t) => t.trade_id > s.lastTradeId || t.ts_ms > lastTs);
              if (fresh.length === 0) return;
              s.heat.addTrades(fresh);
              const merged = s.trades.concat(fresh);
              set({
                trades: merged.length > TRADE_CAPACITY ? merged.slice(-TRADE_CAPACITY) : merged,
                tradesHead: s.tradesHead + 1,
                lastTradeId: fresh[fresh.length - 1]!.trade_id,
              });
              return;
            }
            case "bar": {
              const d = msg.data;
              let lastTs = s.lastBarTs;
              for (const row of d.rows) {
                const rec = rowToRecord(d.columns, row);
                const ts = rec.ts_ms ?? 0;
                if (ts <= lastTs) continue; // duplicate / out of order (snapshot overlap)
                s.bars.pushRow(rec);
                lastTs = ts;
              }
              set({ barsHead: s.bars.head, lastBarTs: lastTs, lastBarAt: lastTs > s.lastBarTs ? Date.now() : s.lastBarAt });
              return;
            }
            case "regime":
              set({ regime: msg.data });
              return;
            case "prediction":
              set({ prediction: msg.data });
              return;
            case "signals": {
              const feed = msg.data.transitions.concat(s.signalFeed);
              set({
                signalsActive: msg.data.active,
                signalFeed: feed.length > FEED_CAPACITY ? feed.slice(0, FEED_CAPACITY) : feed,
              });
              for (const t of msg.data.transitions) {
                if (t.kind === "activated" && t.priority === "high") {
                  get().addToast({ tone: "serious", title: t.name, body: t.message, ttlMs: 6000 });
                }
              }
              return;
            }
            case "alert": {
              const alerts = [msg.data, ...s.alerts];
              set({ alerts: alerts.length > FEED_CAPACITY ? alerts.slice(0, FEED_CAPACITY) : alerts });
              get().addToast({
                tone: msg.data.priority === "critical" ? "critical" : msg.data.priority === "high" ? "serious" : "warning",
                title: `Alert · ${msg.data.rule_name}`,
                body: msg.data.message,
                ttlMs: 8000,
              });
              return;
            }
            case "backtest_progress":
              set({ backtests: { ...s.backtests, [msg.data.backtest_id]: msg.data } });
              return;
            case "status":
              set({ sourceStatus: msg.data });
              return;
            case "subscribed":
              set({
                connection: {
                  ...s.connection,
                  channels: (msg.data as { channels?: Channel[] }).channels ?? s.connection.channels,
                  symbol: (msg.data as { symbol?: string }).symbol ?? s.connection.symbol,
                },
              });
              return;
            case "pong":
            case "error":
              return;
          }
        },

        setConnection: (patch) => set({ connection: { ...get().connection, ...patch } }),

        resetMarket: () => {
          const s = get();
          s.bars.clear();
          s.depth.clear();
          s.heat.clear();
          set({
            features: null,
            book: null,
            trades: [],
            lastTradeId: 0,
            barsHead: 0,
            lastBarTs: 0,
            lastBarAt: 0,
            regime: null,
            prediction: null,
            signalsActive: [],
            signalFeed: [],
            hydrated: false,
          });
        },

        addToast: (t) => {
          const toast: Toast = { id: ++toastSeq, createdAt: Date.now(), ttlMs: t.ttlMs ?? 5000, ...t };
          const toasts = [...get().ui.toasts, toast].slice(-5);
          set({ ui: { ...get().ui, toasts } });
        },
        dismissToast: (id) => set({ ui: { ...get().ui, toasts: get().ui.toasts.filter((t) => t.id !== id) } }),
        setPaletteOpen: (open) => set({ ui: { ...get().ui, paletteOpen: open } }),
        setPrefs: (patch) => set({ prefs: { ...get().prefs, ...patch } }),
        setDetectedTier: (tier) => set({ ui: { ...get().ui, detectedTier: tier } }),
        setReducedMotionOS: (v) => set({ ui: { ...get().ui, reducedMotionOS: v } }),
      }),
      {
        name: PREFS_STORAGE_KEY,
        storage: createJSONStorage(() => (typeof window === "undefined" ? noopStorage : prefsStorage)),
        partialize: (s) => ({ prefs: s.prefs }),
      },
    ),
  ),
);

// ── Selectors ───────────────────────────────────────────────────────

export const useConnection = () => useStore((s) => s.connection);
export const useFeatures = () => useStore((s) => s.features);
export const useBook = () => useStore((s) => s.book);
export const useTrades = () => useStore((s) => s.trades);
export const useRegime = () => useStore((s) => s.regime);
export const usePrediction = () => useStore((s) => s.prediction);
export const useSignals = () => useStore(useShallow((s) => ({ active: s.signalsActive, feed: s.signalFeed })));
export const useAlerts = () => useStore((s) => s.alerts);
export const usePrefs = () => useStore((s) => s.prefs);
export const useHydrated = () => useStore((s) => s.hydrated);

// The bar table is mutated in place, outside React, so frames that land before a subtree
// hydrates would make its first render differ from the server's empty HTML. Readers get an
// empty table until `barsHead` moves; hydration sees the initial head (0), and the head
// change then re-renders them with the real table.
const NO_BARS = new RingTable<BarCol>(BAR_COLUMNS, 1);
export const selectBars = (s: AppState) => ({ bars: s.barsHead === 0 ? NO_BARS : s.bars, head: s.barsHead });

/** The bar ring plus a head counter that changes whenever a bar arrives. */
export const useBars = () => useStore(useShallow(selectBars));

/** Effective motion / perf given OS preference, detection and user override. */
export const selectEffectiveMotion = (s: AppState): boolean => {
  if (s.prefs.motion === "reduced") return false;
  if (s.prefs.motion === "full") return true;
  return !s.ui.reducedMotionOS;
};
export const useEffectiveMotion = () => useStore(selectEffectiveMotion);

/**
 * Imperative motion check for mount-time effects (entrance tweens).
 * During React hydration the hook above returns the *server* snapshot (default
 * prefs), and `reducedMotionOS` is only recorded by a parent effect that runs
 * after children's — so a `[]`-dependency effect would capture stale values.
 * Reading the live store (already rehydrated from localStorage) plus the media
 * query directly avoids both problems.
 */
export const motionAllowed = (): boolean => {
  const s = useStore.getState();
  if (s.prefs.motion === "reduced") return false;
  if (s.prefs.motion === "full") return true;
  if (s.ui.reducedMotionOS) return false;
  return typeof window === "undefined" || !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
};

export const useEffectiveTier = (): Exclude<PerfTier, "auto"> =>
  useStore((s) => (s.prefs.perfTier === "auto" ? (s.ui.detectedTier ?? "mid") : s.prefs.perfTier));
