"use client";

import { Lightbulb, ListOrdered } from "lucide-react";
import { useMemo } from "react";

import { Badge, Panel, type BadgeTone } from "@/components/ds";
import { useCatalog, useShap, type ModelInfo } from "@/lib/api/hooks";
import { featureLabel, formatFeatureValue } from "@/lib/features";
import { fmtPct, fmtSigned } from "@/lib/format";
import { usePrediction } from "@/lib/store";
import { COLORS } from "@/lib/theme";

function useCatalogLabels(): Record<string, string> {
  const catalog = useCatalog();
  return useMemo(() => Object.fromEntries((catalog.data ?? []).map((f) => [f.name, f.label])), [catalog.data]);
}

// label · bar · value; a literal so Tailwind can see the class
const ROW = "grid grid-cols-[minmax(0,13rem)_1fr_4.5rem] items-center gap-3";

// ── SHAP waterfall ──────────────────────────────────────────────────

interface Step {
  key: string;
  label: string;
  detail?: string;
  from: number;
  to: number;
}

/**
 * Why the model leans the way it does: a waterfall from the average output
 * (base value) through each feature's SHAP contribution to this prediction,
 * in raw log-odds of the class the served model favours. The served model is
 * an ensemble of calibrated tree models; SHAP is averaged over its tree
 * models, before calibration (a monotone per-class map it can't attribute).
 */
export function ShapPanel({ symbol }: { symbol: string | null }) {
  const p = usePrediction();
  const shap = useShap(symbol, p?.status === "ready");
  const labels = useCatalogLabels();
  const d = shap.data;
  const toward = d?.predicted_class === "up" ? COLORS.bid : d?.predicted_class === "down" ? COLORS.ask : COLORS.accent;

  const chart = useMemo(() => {
    if (!d) return null;
    const top = [...d.contributions].sort((a, b) => Math.abs(b.shap) - Math.abs(a.shap));
    const steps: Step[] = [];
    let cum = d.base_value;
    for (const c of top) {
      steps.push({
        key: c.feature,
        label: featureLabel(c.feature, labels),
        detail: formatFeatureValue(c.feature, c.value),
        from: cum,
        to: cum + c.shap,
      });
      cum += c.shap;
    }
    const rest = d.prediction_logit - cum;
    if (Math.abs(rest) > 1e-6) steps.push({ key: "other", label: "All other features", from: cum, to: d.prediction_logit });
    const ends = [d.base_value, d.prediction_logit, ...steps.flatMap((s) => [s.from, s.to])];
    let lo = Math.min(...ends);
    let hi = Math.max(...ends);
    const pad = (hi - lo) * 0.06 || 0.5;
    lo -= pad;
    hi += pad;
    return { steps, lo, hi };
  }, [d, labels]);
  const pct = (v: number) => (chart ? ((v - chart.lo) / (chart.hi - chart.lo)) * 100 : 0);
  const tone: BadgeTone = d?.predicted_class === "up" ? "bid" : d?.predicted_class === "down" ? "ask" : "neutral";

  return (
    <Panel
      icon={Lightbulb}
      title="Why this prediction"
      subtitle="SHAP of the served ensemble, raw log-odds of the favoured class"
      actions={
        d && (
          <Badge tone={tone}>
            favours {d.predicted_class} · {fmtPct(d.probability, 0)}
          </Badge>
        )
      }
    >
      {!d && (
        <p className="py-6 text-body text-ink-faint">
          {p?.status === "ready" ? "Computing the explanation…" : "Available once the first model has trained."}
        </p>
      )}
      {d && chart && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-meta text-ink-muted">
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-3 rounded-sm" style={{ background: toward }} aria-hidden />
              pushes toward {d.predicted_class}
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-3 rounded-sm bg-ink-faint" aria-hidden />
              pushes away
            </span>
          </div>
          <ol className="space-y-1" aria-label="SHAP waterfall, largest contribution first">
            <WaterfallRow
              label="Base value"
              detail="the model's average output"
              marker={pct(d.base_value)}
              value={d.base_value.toFixed(2)}
            />
            {chart.steps.map((s) => {
              const up = s.to >= s.from;
              return (
                <li key={s.key} className={`row ${ROW} px-2 py-1`}>
                  <span className="min-w-0">
                    <span className="block text-meta text-ink">{s.label}</span>
                    {s.detail && <span className="num block truncate text-caption text-ink-faint">{s.detail}</span>}
                  </span>
                  <span className="relative h-3" aria-hidden>
                    <span
                      className="absolute inset-y-0 rounded-[2px]"
                      style={{
                        left: `${pct(Math.min(s.from, s.to))}%`,
                        width: `max(2px, ${Math.abs(pct(s.to) - pct(s.from))}%)`,
                        background: up ? toward : "var(--color-ink-faint)",
                      }}
                    />
                  </span>
                  <span className="num text-right text-meta text-ink">{fmtSigned(s.to - s.from, 3)}</span>
                </li>
              );
            })}
            <WaterfallRow
              label="Prediction"
              detail={`log-odds of ${d.predicted_class}`}
              marker={pct(d.prediction_logit)}
              value={d.prediction_logit.toFixed(2)}
              strong
            />
          </ol>
          <p className="hint mt-3 leading-snug">
            Averaged over the served model&apos;s {d.models_averaged} tree model{d.models_averaged === 1 ? "" : "s"} (one per calibration
            split), in log-odds before calibration. The favoured class and its {fmtPct(d.probability, 0)} are the served, calibrated
            prediction; calibration only rescales each class monotonically, so it never reorders what pushes toward it.
          </p>
        </>
      )}
    </Panel>
  );
}

function WaterfallRow({
  label,
  detail,
  marker,
  value,
  strong,
}: {
  label: string;
  detail: string;
  marker: number;
  value: string;
  strong?: boolean;
}) {
  return (
    <li className={`${ROW} px-2 py-1`}>
      <span className="min-w-0">
        <span className={`block truncate text-meta ${strong ? "font-medium text-ink" : "text-ink-muted"}`}>{label}</span>
        <span className="block truncate text-caption text-ink-faint">{detail}</span>
      </span>
      <span className="relative h-3" aria-hidden>
        <span className="absolute inset-y-[-3px] w-0.5 rounded-full bg-ink" style={{ left: `${marker}%` }} />
      </span>
      <span className={`num text-right text-meta ${strong ? "font-medium text-ink" : "text-ink-muted"}`}>{value}</span>
    </li>
  );
}

// ── Permutation importance ──────────────────────────────────────────

/**
 * Which inputs the model leans on: how much held-out log-loss rises when each
 * one is shuffled, measured by each recent walk-forward fold's own served
 * model on the fold it never saw. Whiskers are ±1 s.d. over folds and repeats.
 */
export function ImportancePanel({ info }: { info: ModelInfo | undefined }) {
  const labels = useCatalogLabels();
  const rows = useMemo(() => {
    const sd = info?.feature_importance_std ?? {};
    const entries = Object.entries(info?.feature_importance ?? {})
      .filter(([, v]) => Number.isFinite(v))
      .sort((a, b) => b[1] - a[1])
      .slice(0, 14)
      .map(([name, v]) => ({ name, v, sd: sd[name] ?? 0 }));
    return { entries, max: Math.max(...entries.map((e) => e.v + e.sd), 1e-9) };
  }, [info?.feature_importance, info?.feature_importance_std]);
  const pct = (v: number) => `${Math.min(100, Math.max(0, (v / rows.max) * 100))}%`;

  return (
    <Panel icon={ListOrdered} title="Permutation importance" subtitle="held-out log-loss increase when a feature is shuffled">
      {rows.entries.length === 0 && <p className="py-6 text-body text-ink-faint">Available once the first model has trained.</p>}
      {rows.entries.length > 0 && (
        <>
          <ol className="space-y-1" aria-label="Features by importance">
            {rows.entries.map(({ name, v, sd }) => (
              <li key={name} className={`row ${ROW} px-2 py-1`} title={`+${v.toFixed(4)} ± ${sd.toFixed(4)} nats`}>
                <span className="text-meta text-ink">{featureLabel(name, labels)}</span>
                <span className="relative h-2.5 rounded-[2px] bg-raised" aria-hidden>
                  <span className="absolute inset-y-0 left-0 rounded-[2px] bg-accent" style={{ width: `max(2px, ${pct(v)})` }} />
                  <span
                    className="absolute top-1/2 h-px -translate-y-1/2 bg-ink"
                    style={{ left: pct(v - sd), width: `calc(${pct(v + sd)} - ${pct(v - sd)})` }}
                  />
                </span>
                <span className="num text-right text-meta text-ink">+{v.toFixed(3)}</span>
              </li>
            ))}
          </ol>
          <p className="hint mt-3 leading-snug">
            Rise in log-loss (nats) on held-out data when the feature&apos;s values are shuffled, from the two most recent walk-forward
            folds, each scored by its own calibrated model on the fold it never trained on; ±1 s.d. over folds and repeats. Only features
            whose shuffle hurts are listed.
          </p>
        </>
      )}
    </Panel>
  );
}
