const price0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const price2 = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function fmtPrice(v: number | null | undefined, decimals: 0 | 2 = 2): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return (decimals === 0 ? price0 : price2).format(v);
}

/** Basis points with precision that follows the magnitude (BTC spreads live below 0.01 bps). */
export function fmtBpsValue(v: number | null | undefined, d = 2): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  return v.toFixed(abs < 0.01 ? 4 : abs < 1 ? 3 : d);
}

export function fmtBps(v: number | null | undefined, d = 2): string {
  const s = fmtBpsValue(v, d);
  return s === "—" ? s : `${s} bps`;
}

/** Signed number with a typographic minus; a value that rounds to zero has no sign (never "−0.000"). */
export function fmtSigned(v: number | null | undefined, d = 2, suffix = ""): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const abs = Math.abs(v).toFixed(d);
  if (Number(abs) === 0) return `${abs}${suffix}`;
  return `${v > 0 ? "+" : "−"}${abs}${suffix}`;
}

export function fmtQty(v: number | null | undefined, d = 3): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(d);
}

export function fmtPct(v: number | null | undefined, d = 0): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${(v * 100).toFixed(d)}%`;
}

export function fmtTime(ms: number | null | undefined): string {
  if (!ms) return "—";
  return new Date(ms).toLocaleTimeString([], { hour12: false });
}

/** A duration in seconds, in the largest unit that keeps it readable: "42 s", "12 min", "1 h 27 min". */
export function fmtDuration(s: number): string {
  if (!Number.isFinite(s)) return "—";
  if (s < 90) return `${Math.round(s)} s`;
  if (s < 5400) return `${Math.round(s / 60)} min`;
  return `${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min`;
}

export function fmtAgo(ms: number, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - ms) / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}
