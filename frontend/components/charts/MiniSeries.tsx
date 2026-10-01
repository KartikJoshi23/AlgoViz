"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { CHART, COLORS, areaGradient, rgba } from "@/lib/theme";

import { crisp, prepareCanvas, useWidth } from "./canvas";

export interface MiniLine {
  values: (number | null)[];
  color: string;
  label: string;
  fill?: boolean;
}

const GUTTER = 44; // y-axis labels
const PAD_T = 8;
const PAD_B = 8;

/**
 * Small line chart for REST-fed series (drift, folds) on the shared chart
 * theme: hairline grid, 2px lines, an optional reference level drawn as a
 * labelled hairline, DOM axis labels and legend, and a hover crosshair that
 * reads every line at that index. Lines share the x index; y auto-scales
 * unless `domain` is given.
 */
export function MiniSeries({
  lines,
  height = 120,
  domain,
  baseline,
  format = (v) => v.toFixed(2),
  xLabel = (i) => `#${i + 1}`,
  label,
}: {
  lines: MiniLine[];
  height?: number;
  domain?: [number, number];
  baseline?: { value: number; label: string };
  format?: (v: number) => string;
  xLabel?: (i: number) => string;
  label: string;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [host, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const n = Math.max(0, ...lines.map((l) => l.values.length));

  const axes = useMemo(() => {
    let lo = domain?.[0] ?? Number.POSITIVE_INFINITY;
    let hi = domain?.[1] ?? Number.NEGATIVE_INFINITY;
    if (!domain) {
      const vals = lines.flatMap((l) => l.values).filter((v): v is number => v != null && Number.isFinite(v));
      if (baseline) vals.push(baseline.value);
      lo = vals.length ? Math.min(...vals) : 0;
      hi = vals.length ? Math.max(...vals) : 1;
      if (hi - lo < 1e-9) {
        lo -= 0.5;
        hi += 0.5;
      }
      const pad = (hi - lo) * 0.08;
      lo -= pad;
      hi += pad;
    }
    const plotW = Math.max(0, width - GUTTER);
    return {
      ticks: [lo + (hi - lo) * 0.1, (lo + hi) / 2, hi - (hi - lo) * 0.1],
      x: (i: number) => GUTTER + (n <= 1 ? plotW / 2 : (plotW * i) / (n - 1)),
      y: (v: number) => PAD_T + (height - PAD_T - PAD_B) * (1 - (v - lo) / (hi - lo)),
    };
  }, [lines, domain, baseline, width, height, n]);
  const { x, y } = axes;

  useEffect(() => {
    const el = canvas.current;
    if (!el || width === 0) return;
    const ctx = prepareCanvas(el, width, height);
    if (!ctx || n === 0) return;
    ctx.lineWidth = 1;
    ctx.strokeStyle = CHART.grid;
    for (const t of axes.ticks) {
      ctx.beginPath();
      ctx.moveTo(GUTTER, crisp(y(t)));
      ctx.lineTo(width, crisp(y(t)));
      ctx.stroke();
    }
    if (baseline) {
      ctx.strokeStyle = rgba(COLORS.ink, 0.35);
      ctx.beginPath();
      ctx.moveTo(GUTTER, crisp(y(baseline.value)));
      ctx.lineTo(width, crisp(y(baseline.value)));
      ctx.stroke();
    }
    for (const l of lines) {
      const trace = () => {
        ctx.beginPath();
        let started = false;
        l.values.forEach((v, i) => {
          if (v == null || !Number.isFinite(v)) {
            started = false;
            return;
          }
          if (started) ctx.lineTo(x(i), y(v));
          else ctx.moveTo(x(i), y(v));
          started = true;
        });
      };
      if (l.fill) {
        const first = l.values.findIndex((v) => v != null && Number.isFinite(v));
        const last = l.values.length - 1 - [...l.values].reverse().findIndex((v) => v != null && Number.isFinite(v));
        if (first >= 0) {
          trace();
          ctx.lineTo(x(last), height - PAD_B);
          ctx.lineTo(x(first), height - PAD_B);
          ctx.closePath();
          ctx.fillStyle = areaGradient(ctx, l.color, PAD_T, height - PAD_B);
          ctx.fill();
        }
      }
      trace();
      ctx.strokeStyle = l.color;
      ctx.lineWidth = CHART.lineWidth;
      ctx.lineJoin = "round";
      ctx.stroke();
    }
    if (hover != null) {
      ctx.strokeStyle = CHART.crosshair;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(crisp(x(hover)), PAD_T);
      ctx.lineTo(crisp(x(hover)), height - PAD_B);
      ctx.stroke();
      for (const l of lines) {
        const v = l.values[hover];
        if (v == null || !Number.isFinite(v)) continue;
        ctx.beginPath();
        ctx.arc(x(hover), y(v), 3.5, 0, Math.PI * 2);
        ctx.fillStyle = l.color;
        ctx.fill();
        ctx.strokeStyle = COLORS.panel;
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    }
  }, [lines, baseline, axes, x, y, width, height, n, hover]);

  const showLegend = lines.length > 1 || baseline;
  const hoverX = hover == null ? 0 : x(hover);

  return (
    <div className="min-w-0">
      {showLegend && (
        <div className="mb-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-meta text-ink-muted">
          {lines.map((l) => (
            <span key={l.label} className="flex items-center gap-1.5">
              <span className="h-0.5 w-3.5 rounded-full" style={{ background: l.color }} aria-hidden />
              {l.label}
            </span>
          ))}
          {baseline && (
            <span className="flex items-center gap-1.5">
              <span className="h-px w-3.5 bg-ink-muted opacity-60" aria-hidden />
              {baseline.label}
            </span>
          )}
        </div>
      )}
      <div
        ref={host}
        className="relative"
        style={{ height }}
        onPointerMove={(e) => {
          if (n === 0) return;
          const r = e.currentTarget.getBoundingClientRect();
          const f = (e.clientX - r.left - GUTTER) / Math.max(1, r.width - GUTTER);
          setHover(Math.min(n - 1, Math.max(0, Math.round(f * (n - 1)))));
        }}
        onPointerLeave={() => setHover(null)}
      >
        <canvas ref={canvas} className="absolute inset-0 block h-full w-full" role="img" aria-label={label} />
        {n === 0 ? (
          <span className="absolute inset-0 grid place-items-center text-meta text-ink-faint">no data yet</span>
        ) : (
          <div
            className="num pointer-events-none absolute inset-y-0 left-0 text-caption text-ink-faint"
            style={{ width: GUTTER }}
            aria-hidden
          >
            {/* a narrow range can round two ticks to one label: show each label once */}
            {axes.ticks.map((t, i) =>
              i > 0 && format(t) === format(axes.ticks[i - 1]!) ? null : (
                <span key={t} className="absolute left-0 -translate-y-1/2" style={{ top: y(t) }}>
                  {format(t)}
                </span>
              ),
            )}
          </div>
        )}
        {hover != null && (
          <div
            className="float pointer-events-none absolute top-1 z-10 rounded-md px-2 py-1 text-caption"
            style={hoverX > (width + GUTTER) / 2 ? { right: width - hoverX + 8 } : { left: hoverX + 8 }}
          >
            <div className="text-ink-faint">{xLabel(hover)}</div>
            {lines.map((l) => {
              const v = l.values[hover];
              return (
                <div key={l.label} className="num flex items-center gap-1.5 text-ink">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: l.color }} aria-hidden />
                  {l.label} {v != null && Number.isFinite(v) ? format(v) : "—"}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
