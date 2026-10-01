import { fmtSigned } from "@/lib/format";

/** How a model feature's value reads: its unit and scale. */
type Kind = "bps" | "sigma" | "ratio" | "share" | "change" | "count" | "typical" | "flag" | "cyclic" | "stat";

/**
 * Readable names for the model's input vector (backend `ml/features.py`,
 * `FEATURE_NAMES`), written from how each one is computed. Windows are in
 * 1-second bars. Quantities are measured against the symbol's own typical
 * size (its rolling 30-minute median), so they read as "× typical".
 */
const MODEL_FEATURES: Record<string, { label: string; kind: Kind }> = {
  ret_1: { label: "Return, 1 s", kind: "bps" },
  ret_5: { label: "Return, 5 s", kind: "bps" },
  ret_10: { label: "Return, 10 s", kind: "bps" },
  ret_30: { label: "Return, 30 s", kind: "bps" },
  ret_60: { label: "Return, 60 s", kind: "bps" },
  accel_5: { label: "Return acceleration, 5 s", kind: "bps" },
  rv_10: { label: "Realised volatility, 10 s", kind: "bps" },
  rv_60: { label: "Realised volatility, 60 s", kind: "bps" },
  rv_ratio: { label: "Volatility ratio, 10 s / 60 s", kind: "ratio" },
  vol_bps: { label: "Volatility (per minute)", kind: "bps" },
  vol_z: { label: "Volatility z-score", kind: "sigma" },
  spread_bps: { label: "Spread", kind: "bps" },
  spread_z: { label: "Spread z-score", kind: "sigma" },
  spread_chg: { label: "Spread vs its 10 s mean", kind: "change" },
  velocity: { label: "Trade velocity vs typical", kind: "typical" },
  velocity_z: { label: "Trade velocity z-score", kind: "sigma" },
  trades_10: { label: "Trades, 10 s, vs typical", kind: "typical" },
  volume_10: { label: "Volume, 10 s, vs typical", kind: "typical" },
  buy_share_10: { label: "Buy share of volume, 10 s", kind: "share" },
  buy_pressure: { label: "Buy pressure", kind: "share" },
  buy_pressure_delta: { label: "Buy pressure change, 10 s", kind: "ratio" },
  imbalance_l1: { label: "Queue imbalance at the touch", kind: "ratio" },
  imbalance_w: { label: "Queue imbalance, depth-weighted", kind: "ratio" },
  imbalance_z: { label: "Queue imbalance z-score", kind: "sigma" },
  imbalance_mom: { label: "Queue imbalance change, 10 s", kind: "ratio" },
  microprice_dev_bps: { label: "Microprice − mid", kind: "bps" },
  liquidity_10bps: { label: "Liquidity within ±10 bps vs typical", kind: "typical" },
  liquidity_z: { label: "Liquidity z-score", kind: "sigma" },
  liq_ratio_5_10: { label: "Liquidity ±5 / ±10 bps", kind: "ratio" },
  book_slope: { label: "Book slope vs typical depth", kind: "typical" },
  ofi_1s: { label: "Order-flow imbalance, 1 s, vs typical volume", kind: "typical" },
  ofi_5s: { label: "Order-flow imbalance, 5 s, vs typical volume", kind: "typical" },
  ofi_30s: { label: "Order-flow imbalance, 30 s, vs typical volume", kind: "typical" },
  ofi_z: { label: "Order-flow imbalance z-score", kind: "sigma" },
  ofi_cum_10: { label: "Order-flow imbalance, 10 s sum, vs typical volume", kind: "typical" },
  vwap_dev_bps: { label: "Price − VWAP", kind: "bps" },
  skew_60: { label: "Return skew, 60 s", kind: "stat" },
  kurt_60: { label: "Return excess kurtosis, 60 s", kind: "stat" },
  consec_up: { label: "Consecutive up bars", kind: "count" },
  consec_down: { label: "Consecutive down bars", kind: "count" },
  regime_calm: { label: "Volatility state is calm", kind: "flag" },
  regime_normal: { label: "Volatility state is normal", kind: "flag" },
  regime_elevated: { label: "Volatility state is elevated", kind: "flag" },
  regime_extreme: { label: "Volatility state is extreme", kind: "flag" },
  hour_sin: { label: "Time of day (sine)", kind: "cyclic" },
  hour_cos: { label: "Time of day (cosine)", kind: "cyclic" },
};

/** A readable name for a model or catalog feature; the raw name when neither knows it. */
export function featureLabel(name: string, catalog?: Record<string, string>): string {
  return MODEL_FEATURES[name]?.label ?? catalog?.[name] ?? name;
}

/** A model feature's value in its own unit. */
export function formatFeatureValue(name: string, v: number): string {
  if (!Number.isFinite(v)) return "—";
  switch (MODEL_FEATURES[name]?.kind) {
    case "bps":
      return `${fmtSigned(v, 2)} bps`;
    case "sigma":
      return `${fmtSigned(v, 2)}σ`;
    case "share":
      return `${(v * 100).toFixed(0)}%`;
    case "change":
      return fmtSigned(v * 100, 0, "%");
    case "count":
      return v.toFixed(0);
    case "typical":
      return `${fmtSigned(v, 2)}×`;
    case "flag":
      return v >= 0.5 ? "yes" : "no";
    case "ratio":
    case "stat":
    case "cyclic":
      return fmtSigned(v, 3);
    default:
      return v.toPrecision(3);
  }
}
