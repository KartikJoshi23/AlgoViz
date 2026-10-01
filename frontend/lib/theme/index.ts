import type { RegimeLabel } from "@/lib/ws/types";

/**
 * The design tokens for code that draws (canvas, WebGL, lightweight-charts).
 * Mirrors the @theme block in app/globals.css — keep the two in step.
 */
export const COLORS = {
  page: "#060911",
  panel: "#111826",
  raised: "#161e2e",
  ink: "#f2f5fb",
  inkMuted: "#b6c0d2",
  inkFaint: "#949fb4",
  inkDisabled: "#5f6b82",
  bid: "#1fa98f",
  bidText: "#3dd2b1",
  ask: "#cf1940",
  askText: "#ff7a8c",
  mid: "#be871a",
  midText: "#e9ae45",
  accent: "#5b8cff",
  accentText: "#8fb2ff",
  brand: "#9b7bff",
  good: "#2ec27e",
  warning: "#f4c542",
  serious: "#fb8c3c",
  critical: "#f04b4b",
  line: "rgba(148,170,220,0.1)",
} as const;

/** One violet hue, calm → extreme: the volatility state is ordinal, so it gets a lightness ramp, not four hues. */
export const REGIME_RAMP = ["#6a55cf", "#8470e6", "#9f8ef6", "#bdb0ff"] as const;

const REGIME_ORDER: Record<RegimeLabel, 0 | 1 | 2 | 3> = { calm: 0, normal: 1, elevated: 2, extreme: 3 };

export function regimeLevel(label: RegimeLabel): 0 | 1 | 2 | 3 {
  return REGIME_ORDER[label] ?? 0;
}

export const REGIME_COLORS: Record<RegimeLabel, string> = {
  calm: REGIME_RAMP[0],
  normal: REGIME_RAMP[1],
  elevated: REGIME_RAMP[2],
  extreme: REGIME_RAMP[3],
};

export function regimeTone(label: string | null | undefined): RegimeLabel {
  return (label as RegimeLabel) ?? "calm";
}

/**
 * Shared chart chrome: a recessive blue-grey hairline grid, muted axis text, an
 * accent crosshair, and area fills that fade from `areaAlpha` at the line to
 * nothing at the baseline (see `areaGradient`).
 */
export const CHART = {
  grid: "rgba(148,170,220,0.07)",
  axis: "rgba(148,170,220,0.14)",
  text: COLORS.inkFaint,
  crosshair: "rgba(91,140,255,0.6)",
  font: "11px var(--font-geist-mono), ui-monospace, monospace",
  fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
  lineWidth: 2,
  areaAlpha: 0.26,
} as const;

/** Colour with alpha, e.g. rgba(COLORS.bid, 0.3). */
export function rgba(hex: string, alpha: number): string {
  const h = hex.replace("#", "");
  const n = parseInt(
    h.length === 3
      ? h
          .split("")
          .map((c) => c + c)
          .join("")
      : h,
    16,
  );
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

/** A vertical fill for an area under a line: `color` at `alpha` at the top of the band, fading to transparent at the bottom. */
export function areaGradient(
  ctx: CanvasRenderingContext2D,
  color: string,
  top: number,
  bottom: number,
  alpha: number = CHART.areaAlpha,
): CanvasGradient {
  const g = ctx.createLinearGradient(0, top, 0, bottom);
  g.addColorStop(0, rgba(color, alpha));
  g.addColorStop(1, rgba(color, 0));
  return g;
}
