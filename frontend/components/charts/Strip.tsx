"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { cx } from "@/components/ds";
import { fmtTime } from "@/lib/format";
import { useBars, type BarCol } from "@/lib/store";
import { CHART, COLORS, areaGradient, rgba } from "@/lib/theme";

import { crisp, prepareCanvas, useWidth } from "./canvas";

interface Band {
  from: number;
  to: number;
  color: string;
}

const PAD_T = 6;
const PAD_B = 6;

/** Running sum of a series (gaps count as zero once it has started) — e.g. cumulative order flow. */
export function cumulative(vals: Float64Array): Float64Array {
  const out = new Float64Array(vals.length);
  let acc = Number.NaN;
  for (let i = 0; i < vals.length; i += 1) {
    const v = vals[i]!;
    if (Number.isFinite(v)) acc = (Number.isFinite(acc) ? acc : 0) + v;
    out[i] = acc;
  }
  return out;
}

/**
 * Compact canvas time-series of one bar column (spread, volatility, OFI…)
 * under a DOM caption with its latest value. `mode="bars"` draws a histogram
 * from zero; `polarity` colours it — or splits a line and its wash — bid
 * above zero and ask below, for signed flow. `transform` derives the plotted
 * series from the window (e.g. `cumulative`). Reads the typed-array ring
 * directly; redraws per bar, on resize and under the hover crosshair.
 */
export function Strip({
  col,
  height = 96,
  color = COLORS.accent,
  bands = [],
  domain,
  zero = false,
  polarity = false,
  mode = "line",
  transform,
  window = 300,
  label,
  format = (v) => v.toFixed(2),
  className,
}: {
  col: BarCol;
  height?: number;
  color?: string;
  /** Shaded value ranges (clipped to the plot; they don't widen the scale). */
  bands?: Band[];
  /** The smallest range the scale may show, so a quiet series isn't blown up to fill the strip. */
  domain?: [number, number];
  zero?: boolean;
  polarity?: boolean;
  mode?: "line" | "bars";
  transform?: (vals: Float64Array) => Float64Array;
  window?: number;
  label?: string;
  format?: (v: number) => string;
  className?: string;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [host, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const { bars, head } = useBars();

  const { vals, offset } = useMemo(() => {
    void head; // the ring is mutated in place; `head` keys the recompute
    const ring = bars.cols[col];
    const n = Math.min(ring.length, window);
    const off = ring.length - n;
    const raw = new Float64Array(n);
    for (let i = 0; i < n; i += 1) raw[i] = ring.at(off + i);
    return { vals: transform ? transform(raw) : raw, offset: off };
  }, [bars, head, col, window, transform]);
  const n = vals.length;
  const histogram = mode === "bars";
  const last = n > 0 ? vals[n - 1]! : Number.NaN;
  const hoverIdx = hover == null || n < 2 ? null : Math.min(n - 1, histogram ? Math.floor(hover * n) : Math.round(hover * (n - 1)));
  const hoverVal = hoverIdx == null ? Number.NaN : vals[hoverIdx]!;
  const hasData = vals.some(Number.isFinite);

  useEffect(() => {
    const el = canvas.current;
    if (!el || width === 0) return;
    const ctx = prepareCanvas(el, width, height);
    if (!ctx) return;
    const W = width;
    const H = height;

    let lo = Number.POSITIVE_INFINITY;
    let hi = Number.NEGATIVE_INFINITY;
    for (const v of vals) {
      if (Number.isFinite(v)) {
        lo = Math.min(lo, v);
        hi = Math.max(hi, v);
      }
    }
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) return;
    if (domain) {
      lo = Math.min(lo, domain[0]);
      hi = Math.max(hi, domain[1]);
    }
    const signed = zero || polarity || histogram;
    if (signed) {
      lo = Math.min(lo, 0);
      hi = Math.max(hi, 0);
    }
    if (hi - lo < 1e-9) hi = lo + 1;
    const pad = (hi - lo) * 0.08;
    lo -= pad;
    hi += pad;
    const y = (v: number) => PAD_T + (H - PAD_T - PAD_B) * (1 - (v - lo) / (hi - lo));
    const x = (i: number) => (histogram ? ((i + 0.5) / n) * W : n <= 1 ? W : (i / (n - 1)) * W);
    const base = signed ? y(0) : H;

    for (const b of bands) {
      ctx.fillStyle = b.color;
      ctx.fillRect(0, y(b.to), W, Math.max(1, y(b.from) - y(b.to)));
    }
    if (signed) {
      ctx.strokeStyle = CHART.axis;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, crisp(base));
      ctx.lineTo(W, crisp(base));
      ctx.stroke();
    }
    const tone = (v: number) => (polarity ? (v >= 0 ? COLORS.bid : COLORS.ask) : color);

    if (histogram) {
      const slot = W / n;
      const bw = Math.max(1, slot > 3 ? slot - 1 : slot);
      for (let i = 0; i < n; i += 1) {
        const v = vals[i]!;
        if (!Number.isFinite(v) || v === 0) continue;
        ctx.fillStyle = hoverIdx === i ? tone(v) : rgba(tone(v), 0.8);
        ctx.fillRect(x(i) - bw / 2, Math.min(y(v), base), bw, Math.max(1, Math.abs(y(v) - base)));
      }
    } else {
      const trace = (area: boolean) => {
        ctx.beginPath();
        let lastI = -1;
        for (let i = 0; i < n; i += 1) {
          const v = vals[i]!;
          if (!Number.isFinite(v)) continue;
          if (lastI < 0) {
            ctx.moveTo(x(i), area ? base : y(v));
            if (area) ctx.lineTo(x(i), y(v));
          } else ctx.lineTo(x(i), y(v));
          lastI = i;
        }
        if (area && lastI >= 0) {
          ctx.lineTo(x(lastI), base);
          ctx.closePath();
        }
      };
      // an area fades towards the baseline from whichever side of it it sits on
      const paint = (stroke: string, clip: [number, number], fade: [number, number]) => {
        ctx.save();
        ctx.beginPath();
        ctx.rect(0, clip[0], W, clip[1] - clip[0]);
        ctx.clip();
        trace(true);
        ctx.fillStyle = areaGradient(ctx, stroke, fade[0], fade[1]);
        ctx.fill();
        trace(false);
        ctx.strokeStyle = stroke;
        ctx.lineWidth = CHART.lineWidth;
        ctx.lineJoin = "round";
        ctx.stroke();
        ctx.restore();
      };
      if (polarity || signed) {
        paint(polarity ? COLORS.bid : color, [0, base], [PAD_T, base]);
        paint(polarity ? COLORS.ask : color, [base, H], [H - PAD_B, base]);
      } else paint(color, [0, H], [PAD_T, base]);
    }

    const dot = (i: number, r: number) => {
      const v = vals[i]!;
      if (!Number.isFinite(v)) return;
      ctx.beginPath();
      ctx.arc(x(i), y(v), r, 0, Math.PI * 2);
      ctx.fillStyle = tone(v);
      ctx.fill();
      ctx.strokeStyle = COLORS.panel;
      ctx.lineWidth = 2;
      ctx.stroke();
    };
    if (hoverIdx != null) {
      ctx.strokeStyle = CHART.crosshair;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(crisp(x(hoverIdx)), 0);
      ctx.lineTo(crisp(x(hoverIdx)), H);
      ctx.stroke();
      if (!histogram) dot(hoverIdx, 4);
    } else if (n > 0 && !histogram) dot(n - 1, 3.5);
  }, [vals, n, width, height, color, bands, domain, zero, polarity, histogram, hoverIdx]);

  const name = label ?? col;
  const hoverX = hoverIdx == null || n < 2 ? 0 : histogram ? ((hoverIdx + 0.5) / n) * width : (hoverIdx / (n - 1)) * width;

  return (
    <div className={cx("min-w-0", className)}>
      {label && (
        <div className="mb-1.5 flex items-baseline justify-between gap-2">
          <span className="col-head truncate">{label}</span>
          <span className="num text-meta text-ink">{Number.isFinite(last) ? format(last) : "—"}</span>
        </div>
      )}
      <div
        ref={host}
        className="relative"
        style={{ height }}
        onPointerMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          setHover(Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)));
        }}
        onPointerLeave={() => setHover(null)}
      >
        <canvas
          ref={canvas}
          className="absolute inset-0 block h-full w-full"
          role="img"
          aria-label={`${name}${Number.isFinite(last) ? `, now ${format(last)}` : ""}`}
        />
        {!hasData && <span className="absolute inset-0 grid place-items-center text-meta text-ink-faint">accumulating…</span>}
        {hoverIdx != null && Number.isFinite(hoverVal) && (
          <div
            className="float pointer-events-none absolute top-1 z-10 rounded-md px-2 py-1 text-caption"
            style={hoverX > width / 2 ? { right: width - hoverX + 8 } : { left: hoverX + 8 }}
          >
            <div className="num text-ink">{format(hoverVal)}</div>
            <div className="num text-ink-faint">{fmtTime(bars.cols.ts_ms.at(offset + hoverIdx))}</div>
          </div>
        )}
      </div>
    </div>
  );
}
