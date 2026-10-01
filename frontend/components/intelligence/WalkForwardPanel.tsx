"use client";

import { CalendarRange } from "lucide-react";
import { useMemo } from "react";

import { Badge, Panel, TableWrap, type BadgeTone } from "@/components/ds";
import type { ModelInfo } from "@/lib/api/hooks";
import { fmtPct, fmtSigned } from "@/lib/format";

const fmt3 = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? "—" : v.toFixed(3));

/**
 * Held-out log-loss per walk-forward fold, as a dot plot: the model — built
 * with the served recipe inside each training window, so what is scored is
 * what is served — against the class prior (the bar for "edge") and a
 * regularised logistic baseline. The scale fits the model and prior; a
 * baseline far outside it is pinned to the edge with its value, so one bad
 * fold can't flatten the comparison that matters.
 */
export function WalkForwardPanel({ info, className }: { info: ModelInfo | undefined; className?: string }) {
  const folds = useMemo(() => info?.metrics.folds ?? [], [info?.metrics.folds]);
  const oos = (info?.metrics.oos ?? {}) as Record<string, number>;
  const edge = oos.edge_vs_prior;
  const edgeTone: BadgeTone = edge == null ? "neutral" : edge > 0 ? "good" : "warning";

  const scale = useMemo(() => {
    const core = folds.flatMap((f) => [f.log_loss, f.prior_log_loss]).filter(Number.isFinite);
    if (core.length === 0) return null;
    let lo = Math.min(...core);
    let hi = Math.max(...core);
    const pad = (hi - lo) * 0.15 || 0.05;
    lo -= pad;
    hi += pad;
    const step = [0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1].find((s) => (hi - lo) / s <= 5) ?? 1;
    const ticks: number[] = [];
    for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) ticks.push(t);
    return { lo, hi, ticks };
  }, [folds]);
  const pct = (v: number) => (scale ? ((v - scale.lo) / (scale.hi - scale.lo)) * 100 : 0);
  const beatsPrior = folds.filter((f) => f.log_loss < f.prior_log_loss).length;
  const beatsLogistic = folds.filter((f) => f.log_loss < f.logistic_log_loss).length;

  return (
    <Panel
      className={className}
      icon={CalendarRange}
      title="Walk-forward validation"
      subtitle={`calibrated as served · time-ordered folds · ${info?.horizon_s ?? "?"} s embargo · ${info?.training_samples ?? 0} samples`}
      actions={
        info && (
          <>
            <Badge tone={edgeTone}>edge vs prior {fmtSigned(edge ?? null, 3)}</Badge>
            <Badge>
              <span className="num">held-out log-loss {fmt3(oos.log_loss)}</span>
            </Badge>
          </>
        )
      }
    >
      {folds.length === 0 && (
        <p className="py-6 text-body text-ink-faint">No trained model yet — folds appear after the first training run.</p>
      )}
      {folds.length > 0 && scale && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-meta text-ink-muted">
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-accent" aria-hidden /> model, calibrated
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full border-2 border-ink-muted" aria-hidden /> class prior
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rotate-45 rounded-[2px] bg-mid" aria-hidden /> logistic baseline
            </span>
            <span className="ml-auto text-ink-faint">log-loss · lower is better</span>
          </div>
          <ol className="space-y-1" aria-label="Held-out log-loss by fold">
            {folds.map((f, i) => {
              const clipped = f.logistic_log_loss > scale.hi ? "hi" : f.logistic_log_loss < scale.lo ? "lo" : null;
              const logistic = Math.min(scale.hi, Math.max(scale.lo, f.logistic_log_loss));
              return (
                <li
                  key={i}
                  className="row grid grid-cols-[7rem_1fr] items-center gap-3 px-2 py-1.5"
                  aria-label={`Fold ${i + 1}: model ${fmt3(f.log_loss)}, prior ${fmt3(f.prior_log_loss)}, logistic ${fmt3(f.logistic_log_loss)}`}
                >
                  <span>
                    <span className="block text-meta text-ink">Fold {i + 1}</span>
                    <span className="num block text-caption text-ink-faint">
                      {f.n_train} → {f.n_test}
                    </span>
                  </span>
                  <span className="relative h-5" aria-hidden>
                    <span className="absolute inset-x-0 top-1/2 h-px bg-line" />
                    <span
                      className="absolute top-1/2 h-0.5 -translate-y-1/2 bg-ink-faint"
                      style={{
                        left: `${Math.min(pct(f.log_loss), pct(f.prior_log_loss))}%`,
                        width: `${Math.abs(pct(f.log_loss) - pct(f.prior_log_loss))}%`,
                      }}
                    />
                    <span
                      className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rotate-45 rounded-[2px] bg-mid"
                      style={{ left: `${pct(logistic)}%` }}
                    />
                    {clipped && (
                      <span className={`num absolute -top-0.5 text-caption text-mid-text ${clipped === "hi" ? "right-3" : "left-3"}`}>
                        {clipped === "hi" ? "→" : "←"} {f.logistic_log_loss.toFixed(2)}
                      </span>
                    )}
                    <span
                      className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-ink-muted bg-panel"
                      style={{ left: `${pct(f.prior_log_loss)}%` }}
                    />
                    <span
                      className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent ring-2 ring-panel"
                      style={{ left: `${pct(f.log_loss)}%` }}
                    />
                  </span>
                </li>
              );
            })}
          </ol>
          <div className="num relative ml-[calc(7rem+20px)] mr-2 mt-1 h-4 text-caption text-ink-faint" aria-hidden>
            {scale.ticks.map((t) => (
              <span key={t} className="absolute -translate-x-1/2" style={{ left: `${pct(t)}%` }}>
                {t.toFixed(2)}
              </span>
            ))}
          </div>
          <p className="mt-2 text-meta text-ink-muted">
            The model beats the class prior in {beatsPrior} of {folds.length} folds and the logistic baseline in {beatsLogistic}. Each
            fold&apos;s model is trained, early-stopped on the time-ordered tail and calibrated inside its own training window, then scored
            on the fold it never saw.
          </p>
          {oos.brier != null && (
            <dl className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4" aria-label="Held-out Brier score decomposition, mean over folds">
              <Term label="Brier" value={oos.brier} hint="lower is better" />
              <Term label="Reliability" value={oos.brier_reliability} hint="miscalibration · lower is better" sign="−" />
              <Term label="Resolution" value={oos.brier_resolution} hint="separation · higher is better" sign="+" />
              <Term label="Uncertainty" value={oos.brier_uncertainty} hint="the data's own · fixed" />
            </dl>
          )}

          <TableWrap label="Walk-forward folds" className="mt-4">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Fold</th>
                  <th className="cell-num">Train</th>
                  <th className="cell-num">Test</th>
                  <th>Calibration</th>
                  <th className="cell-num">Log-loss</th>
                  <th className="cell-num">Raw</th>
                  <th className="cell-num">Prior</th>
                  <th className="cell-num">Logistic</th>
                  <th className="cell-num">Brier</th>
                  <th className="cell-num">Reliability</th>
                  <th className="cell-num">Resolution</th>
                  <th className="cell-num">Accuracy</th>
                  <th>Beats prior</th>
                </tr>
              </thead>
              <tbody>
                {folds.map((f, i) => {
                  const beats = f.log_loss < f.prior_log_loss;
                  return (
                    <tr key={i}>
                      <td>{i + 1}</td>
                      <td className="cell-num text-ink-muted">{f.n_train}</td>
                      <td className="cell-num text-ink-muted">{f.n_test}</td>
                      <td className="text-ink-muted">{f.calibration}</td>
                      <td className="cell-num">{fmt3(f.log_loss)}</td>
                      <td className="cell-num text-ink-muted">{fmt3(f.raw_log_loss)}</td>
                      <td className="cell-num text-ink-muted">{fmt3(f.prior_log_loss)}</td>
                      <td className="cell-num text-ink-muted">{fmt3(f.logistic_log_loss)}</td>
                      <td className="cell-num">{fmt3(f.brier)}</td>
                      <td className="cell-num text-ink-muted">{f.brier_reliability.toFixed(4)}</td>
                      <td className="cell-num text-ink-muted">{f.brier_resolution.toFixed(4)}</td>
                      <td className="cell-num">{fmtPct(f.accuracy, 1)}</td>
                      <td>
                        <span className="flex items-center gap-1.5 text-meta">
                          <span className="status-dot" data-status={beats ? "good" : "critical"} aria-hidden />
                          {beats ? "yes" : "no"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </TableWrap>
        </>
      )}
    </Panel>
  );
}

/** One term of Brier = reliability − resolution + uncertainty, with the sign it enters with. */
function Term({ label, value, hint, sign }: { label: string; value: number | undefined; hint: string; sign?: "+" | "−" }) {
  return (
    <div className="raised px-3 py-2">
      <dt className="flex items-center gap-1.5 text-meta text-ink-muted">
        {sign && <span className="num text-ink-faint">{sign}</span>}
        {label}
      </dt>
      <dd className="num text-title font-semibold text-ink">{value != null ? value.toFixed(4) : "—"}</dd>
      <dd className="truncate text-caption text-ink-faint">{hint}</dd>
    </div>
  );
}
