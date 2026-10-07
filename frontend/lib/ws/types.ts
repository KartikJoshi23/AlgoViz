/** WebSocket frame types, derived from the generated OpenAPI schema. */
import type { components } from "@/lib/api/schema";

type S = components["schemas"];

export type ServerMessage = S["WSSchema"]["server"];
export type ClientMessage = S["WSSchema"]["client"];
export type Channel = S["SubscribeMessage"]["channels"] extends (infer C)[] | null | undefined ? C : never;

export type HelloPayload = S["HelloPayload"];
export type SnapshotPayload = S["SnapshotPayload"];
export type FeaturesPayload = S["FeaturesPayload"];
export type BookPayload = S["BookPayload"];
export type TradePayload = S["TradePayload"];
export type BarRows = S["BarRows"];
export type RegimePayload = S["RegimePayload"];
export type PredictionPayload = S["PredictionPayload"];
export type SignalsPayload = S["SignalsPayload"];
export type ActiveSignal = S["ActiveSignalPayload"];
export type SignalTransition = S["SignalTransitionPayload"];
export type AlertPayload = S["AlertPayload"];
export type StatusPayload = S["StatusPayload"];
export type BacktestProgress = S["BacktestProgressPayload"];
export type DriftSummary = S["DriftSummary"];
export type HeatColumn = S["HeatColumn"];

export type MessageOf<T extends ServerMessage["type"]> = Extract<ServerMessage, { type: T }>;

export const ALL_CHANNELS = [
  "features",
  "book",
  "trades",
  "bars",
  "regime",
  "prediction",
  "signals",
  "alerts",
  "backtests",
  "status",
] as const satisfies readonly Channel[];

/** Volatility states, calm → extreme (ordinal), and the separate trend. */
export type RegimeLabel = RegimePayload["label"];
export type TrendLabel = RegimePayload["trend"];
export const REGIMES: readonly RegimeLabel[] = ["calm", "normal", "elevated", "extreme"];
export const TRENDS: readonly TrendLabel[] = ["down", "flat", "up"];
