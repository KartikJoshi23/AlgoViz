"use client";

import { useId, useMemo } from "react";

import { useBars, type BarCol } from "@/lib/store";

const MAX_POINTS = 120;

/**
 * A trend line: the values in the accent over a wash that fades to the
 * baseline, the newest point marked with a lit dot, and an optional reference
 * level (a baseline to beat) as a hairline. Drawn as SVG.
 */
export function SparkLine({
  values,
  height = 28,
  label,
  reference,
}: {
  values: number[];
  height?: number;
  label: string;
  reference?: number | null;
}) {
  const fillId = `spark-${useId().replace(/[^\w-]/g, "")}`;
  const geometry = useMemo(() => {
    const finite = values.filter(Number.isFinite);
    if (finite.length < 2) return null;
    let lo = Math.min(...finite);
    let hi = Math.max(...finite);
    if (reference != null && Number.isFinite(reference)) {
      lo = Math.min(lo, reference);
      hi = Math.max(hi, reference);
    }
    if (hi - lo < 1e-12) {
      lo -= 1;
      hi += 1;
    }
    const x = (i: number) => (i / (values.length - 1)) * 100;
    const y = (v: number) => 4 + (1 - (v - lo) / (hi - lo)) * 92;
    let line = "";
    let first: number | null = null;
    let lastX = 0;
    values.forEach((v, i) => {
      if (!Number.isFinite(v)) return;
      line += `${line ? "L" : "M"}${x(i).toFixed(2)},${y(v).toFixed(2)}`;
      first ??= x(i);
      lastX = x(i);
    });
    const last = values[values.length - 1]!;
    return {
      line,
      area: `${line}L${lastX.toFixed(2)},100L${(first ?? 0).toFixed(2)},100Z`,
      end: Number.isFinite(last) ? y(last) : null,
      ref: reference != null && Number.isFinite(reference) ? y(reference) : null,
    };
  }, [values, reference]);

  return (
    <div className="relative w-full" style={{ height }} role="img" aria-label={label}>
      {geometry && (
        <>
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full overflow-visible" aria-hidden>
            <defs>
              <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" style={{ stopColor: "var(--color-accent)", stopOpacity: 0.3 }} />
                <stop offset="100%" style={{ stopColor: "var(--color-accent)", stopOpacity: 0 }} />
              </linearGradient>
            </defs>
            <path d={geometry.area} fill={`url(#${fillId})`} />
            {geometry.ref != null && (
              <line
                x1={0}
                x2={100}
                y1={geometry.ref}
                y2={geometry.ref}
                stroke="var(--color-ink-disabled)"
                strokeWidth={1}
                vectorEffect="non-scaling-stroke"
              />
            )}
            <path
              d={geometry.line}
              fill="none"
              stroke="var(--color-accent)"
              strokeWidth={1.5}
              strokeLinejoin="round"
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
            />
          </svg>
          {geometry.end != null && (
            <span
              className="absolute right-0 h-[7px] w-[7px] -translate-y-1/2 translate-x-1/2 rounded-full bg-accent shadow-[0_0_10px_var(--color-accent)] ring-2 ring-panel-bottom"
              style={{ top: `${geometry.end}%` }}
              aria-hidden
            />
          )}
        </>
      )}
    </div>
  );
}

/**
 * A stat tile's trend: the last `window` bars of one column (or a value
 * derived per bar), downsampled to at most 120 points. Recomputed once per bar.
 */
export function Sparkline({
  col,
  window = 300,
  transform,
  height = 28,
  label,
}: {
  col: BarCol;
  window?: number;
  /** Derive the plotted value from the bar (e.g. microprice − mid in bps); defaults to the column. */
  transform?: (i: number) => number;
  height?: number;
  label: string;
}) {
  const { bars, head } = useBars();
  const values = useMemo(() => {
    void head;
    const ring = bars.cols[col];
    const n = Math.min(ring.length, window);
    const offset = ring.length - n;
    const step = Math.max(1, Math.ceil(n / MAX_POINTS));
    const out: number[] = [];
    for (let i = 0; i < n; i += step) out.push(transform ? transform(offset + i) : ring.at(offset + i));
    if (n > 0 && (n - 1) % step !== 0) out.push(transform ? transform(offset + n - 1) : ring.at(offset + n - 1));
    return out;
  }, [bars, head, col, window, transform]);
  return <SparkLine values={values} height={height} label={label} />;
}
