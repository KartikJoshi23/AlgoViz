"use client";

import { Target } from "lucide-react";
import { useMemo, useState } from "react";

import { Panel, SegmentedControl, Skeleton } from "@/components/ds";
import { useDrift, type ModelInfo } from "@/lib/api/hooks";
import { fmtPct } from "@/lib/format";
import { reliability, reliabilityFromCurve, type ClassFilter, type ReliabilityBin } from "@/lib/reliability";
import { COLORS } from "@/lib/theme";

const SIZE = 220; // plot square (viewBox units)
const PAD_L = 34;
const PAD_B = 26;
const HIST = 36; // predicted-probability histogram under the plot
const MIN_N = 5; // bins with fewer pairs are drawn hollow: too few to read

const TICKS = [0, 0.25, 0.5, 0.75, 1];

type Source = "held_out" | "live";

/**
 * How well the probabilities are calibrated: for forecasts of about p, did
 * the class happen about p of the time? Two sources: the walk-forward folds'
 * held-out forecasts (each fold's served model on data it never saw, pooled)
 * and the resolved live predictions (the drift monitor's window). One class
 * or all three pooled.
 */
export function ReliabilityPanel({ symbol, info }: { symbol: string | null; info: ModelInfo | undefined }) {
  const drift = useDrift(symbol);
  const [source, setSource] = useState<Source>("held_out");
  const [cls, setCls] = useState<ClassFilter>("all");
  const [hover, setHover] = useState<ReliabilityBin | null>(null);
  const curve = info?.metrics.reliability;
  const r = useMemo(
    () => (source === "held_out" ? reliabilityFromCurve(curve, cls) : reliability(drift.data?.series ?? [], cls)),
    [source, curve, drift.data, cls],
  );
  const heldBrier = cls === "all" ? (info?.metrics.oos as Record<string, number> | undefined)?.brier : undefined;
  const brier = source === "held_out" ? (heldBrier ?? null) : r.brier;
  const loading = source === "held_out" ? !info : !drift.data;
  const maxN = Math.max(1, ...r.bins.map((b) => b.n));
  const x = (p: number) => PAD_L + p * SIZE;
  const y = (p: number) => SIZE - p * SIZE;
  const readable = r.bins.filter((b) => b.n >= MIN_N);

  return (
    <Panel
      icon={Target}
      title="Reliability"
      subtitle={
        source === "held_out" ? `walk-forward folds · ${r.outcomes} held-out forecasts` : `live predictions · last ${r.outcomes} resolved`
      }
      actions={
        <SegmentedControl<Source>
          label="Source"
          value={source}
          onChange={setSource}
          items={[
            { value: "held_out", label: "Held-out" },
            { value: "live", label: "Live" },
          ]}
        />
      }
    >
      <SegmentedControl<ClassFilter>
        label="Class"
        className="mb-3 self-start"
        value={cls}
        onChange={setCls}
        items={[
          { value: "all", label: "All" },
          { value: "down", label: "Down" },
          { value: "flat", label: "Flat" },
          { value: "up", label: "Up" },
        ]}
      />
      {loading && <Skeleton className="h-56" />}
      {!loading && r.pairs === 0 && (
        <p className="py-6 text-body text-ink-faint">
          {source === "held_out" ? "Available once the first model has trained." : "No live prediction has resolved yet."}
        </p>
      )}
      {!loading && r.pairs > 0 && (
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
          <div className="relative w-full max-w-[300px] shrink-0">
            <svg
              viewBox={`0 0 ${PAD_L + SIZE + 6} ${SIZE + PAD_B + HIST + 8}`}
              className="h-auto w-full overflow-visible"
              role="img"
              aria-label={`Reliability diagram, ${cls === "all" ? "all classes" : cls}: expected calibration error ${r.ece != null ? fmtPct(r.ece, 1) : "unknown"} over ${r.pairs} probability-outcome pairs`}
            >
              {TICKS.map((t) => (
                <g key={t}>
                  <line x1={x(0)} x2={x(1)} y1={y(t)} y2={y(t)} stroke="var(--color-line)" />
                  <line x1={x(t)} x2={x(t)} y1={y(0)} y2={y(1)} stroke="var(--color-line)" />
                  <text x={PAD_L - 6} y={y(t) + 3.5} textAnchor="end" className="fill-ink-faint text-[10px]">
                    {t * 100}%
                  </text>
                  <text x={x(t)} y={SIZE + 14} textAnchor="middle" className="fill-ink-faint text-[10px]">
                    {t * 100}%
                  </text>
                </g>
              ))}
              {/* perfect calibration */}
              <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke="var(--color-ink-faint)" strokeOpacity={0.6} />
              <polyline
                fill="none"
                stroke={COLORS.accent}
                strokeWidth={2}
                strokeLinejoin="round"
                points={readable.map((b) => `${x(b.predicted)},${y(b.observed)}`).join(" ")}
              />
              {r.bins.map((b) =>
                b.n === 0 ? null : (
                  <g key={b.lo} onPointerEnter={() => setHover(b)} onPointerLeave={() => setHover(null)}>
                    <circle cx={x(b.predicted)} cy={y(b.observed)} r={12} fill="transparent" />
                    <circle
                      cx={x(b.predicted)}
                      cy={y(b.observed)}
                      r={3 + 5 * Math.sqrt(b.n / maxN)}
                      fill={b.n >= MIN_N ? COLORS.accent : COLORS.panel}
                      stroke={b.n >= MIN_N ? COLORS.panel : COLORS.accent}
                      strokeWidth={2}
                    />
                  </g>
                ),
              )}
              <text x={x(0.5)} y={SIZE + 25} textAnchor="middle" className="fill-ink-muted text-[10px]">
                predicted probability
              </text>
              {/* how often each probability was predicted */}
              {r.bins.map((b) => {
                const h = (b.n / maxN) * HIST;
                return (
                  <rect
                    key={`h${b.lo}`}
                    x={x(b.lo) + 1}
                    y={SIZE + PAD_B + 8 + HIST - h}
                    width={SIZE / r.bins.length - 2}
                    height={Math.max(h, b.n ? 1 : 0)}
                    rx={1}
                    fill="var(--color-ink-disabled)"
                  />
                );
              })}
            </svg>
            {hover && (
              <div
                className="float pointer-events-none absolute z-10 whitespace-nowrap rounded-md px-2 py-1 text-caption"
                style={{
                  left: `${((PAD_L + hover.predicted * SIZE) / (PAD_L + SIZE + 6)) * 100}%`,
                  top: `${((SIZE - hover.observed * SIZE) / (SIZE + PAD_B + HIST + 8)) * 100}%`,
                  transform: "translate(12px, -110%)",
                }}
              >
                <div className="num text-ink">
                  predicted {fmtPct(hover.predicted, 0)} → happened {fmtPct(hover.observed, 0)}
                </div>
                <div className="num text-ink-faint">
                  {fmtPct(hover.lo, 0)}–{fmtPct(hover.hi, 0)} bin · {hover.n} pairs{hover.n < MIN_N ? " · too few to read" : ""}
                </div>
              </div>
            )}
          </div>
          <dl className="grid flex-1 grid-cols-3 gap-2 sm:grid-cols-1">
            <div className="raised px-3 py-2">
              <dt className="text-meta text-ink-muted">Calibration error</dt>
              <dd className="num text-title font-semibold text-ink">{r.ece != null ? fmtPct(r.ece, 1) : "—"}</dd>
              <dd className="text-caption text-ink-faint">count-weighted gap to the diagonal</dd>
            </div>
            <div className="raised px-3 py-2">
              <dt className="text-meta text-ink-muted">Brier score</dt>
              <dd className="num text-title font-semibold text-ink">{brier != null ? brier.toFixed(3) : "—"}</dd>
              <dd className="text-caption text-ink-faint">
                {brier == null ? "held-out: all classes only" : cls === "all" ? "summed over classes · lower is better" : "lower is better"}
              </dd>
            </div>
            <div className="raised px-3 py-2">
              <dt className="text-meta text-ink-muted">Pairs</dt>
              <dd className="num text-title font-semibold text-ink">{r.pairs}</dd>
              <dd className="text-caption text-ink-faint">hollow points: fewer than {MIN_N}</dd>
            </div>
          </dl>
        </div>
      )}
    </Panel>
  );
}
