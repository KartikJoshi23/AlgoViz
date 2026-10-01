"use client";

import { Compass } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge, Panel, Tooltip, type BadgeTone } from "@/components/ds";
import { fmtPct, fmtSigned, fmtTime } from "@/lib/format";
import { useBars, useRegime } from "@/lib/store";
import { REGIME_RAMP, regimeTone } from "@/lib/theme";
import { REGIMES, TRENDS } from "@/lib/ws/types";

interface Run {
  from: number; // bar index, inclusive
  to: number;
  code: number | null; // null: bars from before the regime tier labelled them
}

/** Trend colours: the book's own down / up, and a neutral grey for no significant drift. */
const TREND_FILL = ["var(--color-ask)", "var(--color-ink-disabled)", "var(--color-bid)"] as const;
const T_SPAN = 4; // the gauge shows t in −4…+4
const T_ENTER = 2;

/** Runs of equal code in one bar column over the ring, plus each code's share of the labelled bars. */
function useRuns(col: "regime" | "trend", codes: number) {
  const { bars, head } = useBars();
  return useMemo(() => {
    void head;
    const n = bars.length;
    const runs: Run[] = [];
    const counts = Array.from({ length: codes }, () => 0);
    let labelled = 0;
    for (let i = 0; i < n; i += 1) {
      const c = bars.cols[col].at(i);
      const code = Number.isFinite(c) ? c : null;
      if (code != null) {
        counts[code] = (counts[code] ?? 0) + 1;
        labelled += 1;
      }
      const last = runs[runs.length - 1];
      if (last && last.code === code) last.to = i;
      else runs.push({ from: i, to: i, code });
    }
    return { bars, n, runs, shares: counts.map((k) => (labelled ? k / labelled : 0)) };
  }, [bars, head, col, codes]);
}

/** A ribbon of runs over the last minutes of bars, with a hover read-out of the run under the pointer. */
function Ribbon({
  col,
  names,
  fills,
  label,
}: {
  col: "regime" | "trend";
  names: readonly string[];
  fills: readonly string[];
  label: string;
}) {
  const { bars, n, runs } = useRuns(col, names.length);
  const [hover, setHover] = useState<{ run: Run; x: number } | null>(null);
  if (n < 2) return <div className="h-3 rounded-sm bg-raised" aria-hidden />;
  const minutes = Math.max(1, Math.round(n / 60));
  return (
    <div
      className="relative h-3"
      onPointerMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        const i = Math.min(n - 1, Math.max(0, Math.floor(((e.clientX - r.left) / r.width) * n)));
        const run = runs.find((u) => i >= u.from && i <= u.to);
        setHover(run ? { run, x: e.clientX - r.left } : null);
      }}
      onPointerLeave={() => setHover(null)}
    >
      <svg
        viewBox={`0 0 ${n} 1`}
        preserveAspectRatio="none"
        className="h-full w-full overflow-hidden rounded-sm bg-raised"
        role="img"
        aria-label={`${label} over the last ${minutes} minutes`}
      >
        {runs.map((u) =>
          u.code == null ? null : <rect key={u.from} x={u.from} y={0} width={u.to - u.from + 1} height={1} fill={fills[u.code]} />,
        )}
      </svg>
      {hover && hover.run.code != null && (
        <div
          className="float pointer-events-none absolute bottom-full z-10 mb-2 -translate-x-1/2 whitespace-nowrap rounded-md px-2 py-1 text-caption"
          style={{ left: hover.x }}
        >
          <span className="capitalize text-ink">{names[hover.run.code]}</span>
          <span className="num text-ink-faint">
            {" "}
            · {fmtTime(bars.cols.ts_ms.at(hover.run.from))}–{fmtTime(bars.cols.ts_ms.at(hover.run.to) + 1000)}
          </span>
        </div>
      )}
    </div>
  );
}

/** The drift t-statistic on −4…+4, with the zones where it counts as a trend (|t| ≥ 2) marked. */
function TrendGauge({ t }: { t: number }) {
  const pos = (v: number) => ((Math.max(-T_SPAN, Math.min(T_SPAN, v)) + T_SPAN) / (2 * T_SPAN)) * 100;
  return (
    <div className="relative h-1.5 rounded-full bg-raised" aria-hidden>
      <span className="absolute inset-y-0 left-0 rounded-l-full bg-ask/70" style={{ width: `${pos(-T_ENTER)}%` }} />
      <span className="absolute inset-y-0 right-0 rounded-r-full bg-bid/70" style={{ width: `${100 - pos(T_ENTER)}%` }} />
      <span className="absolute inset-y-[-3px] left-1/2 w-px bg-line-strong" />
      <span
        className="absolute top-1/2 h-3.5 w-1 -translate-y-1/2 rounded-full bg-ink ring-2 ring-panel-bottom transition-[left] duration-500"
        style={{ left: `calc(${pos(t)}% - 2px)` }}
      />
    </div>
  );
}

/**
 * Two separate axes. The volatility state (HMM, calm → extreme on the
 * ordinal ramp) says how wild the market is; the trend (the drift's
 * Newey–West t-statistic over two minutes) says whether it is going
 * anywhere. "Trending" is shown only while that t-statistic clears ±2.
 */
export function RegimePanel({ className }: { className?: string }) {
  const r = useRegime();
  const { shares } = useRuns("regime", REGIMES.length);
  const current = r?.probs?.[r.label];
  const trend = r?.trend ?? "flat";
  const t = r?.trend_t ?? 0;
  const trendTone: BadgeTone = trend === "up" ? "bid" : trend === "down" ? "ask" : "neutral";

  return (
    <Panel
      className={className}
      icon={Compass}
      title="Regime"
      subtitle={
        r
          ? `${r.source === "hmm" ? `HMM v${r.model_version}` : "threshold fallback"}${current != null ? ` · p ${current.toFixed(2)}` : ""}`
          : "warming up"
      }
      actions={
        <>
          <Badge tone={regimeTone(r?.label)}>{r?.label ?? "—"}</Badge>
          <Badge tone={trendTone}>{r ? (trend === "flat" ? "no trend" : `trending ${trend}`) : "—"}</Badge>
        </>
      }
    >
      <div className="flex flex-1 flex-col justify-center gap-4">
        <section aria-label="Volatility state" className="flex flex-col gap-2">
          <div className="flex items-baseline justify-between">
            <h3 className="eyebrow">Volatility state</h3>
            <span className="num text-caption text-ink-faint">HMM · by volatility z</span>
          </div>
          <Ribbon col="regime" names={REGIMES} fills={REGIME_RAMP} label="Volatility state" />
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-meta">
            {REGIMES.map((lab, i) => (
              <span key={lab} className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-sm" style={{ background: REGIME_RAMP[i] }} aria-hidden />
                <span className={`capitalize ${lab === r?.label ? "font-medium text-ink" : "text-ink-muted"}`}>{lab}</span>
                <span className="num ml-auto text-ink-faint">{fmtPct(shares[i], 0)}</span>
              </span>
            ))}
          </div>
        </section>
        <section aria-label="Trend" className="flex flex-col gap-2">
          <div className="flex items-baseline justify-between">
            <h3 className="eyebrow">Trend · 2 min</h3>
            <span className="num text-caption text-ink-muted">t {fmtSigned(t, 2)}</span>
          </div>
          <Ribbon col="trend" names={TRENDS} fills={TREND_FILL} label="Trend" />
          <Tooltip
            content="Drift of 1 s returns over two minutes as a t-statistic with a Newey–West standard error. A trend needs |t| ≥ 2 and ends below 1.5."
            className="w-full"
          >
            <div tabIndex={0} className="w-full rounded-md pt-1">
              <TrendGauge t={t} />
              <div className="num mt-1.5 flex justify-between text-caption text-ink-faint">
                <span>down · t ≤ −2</span>
                <span>no trend</span>
                <span>up · t ≥ 2</span>
              </div>
            </div>
          </Tooltip>
        </section>
      </div>
    </Panel>
  );
}
