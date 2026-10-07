"use client";

import { BrainCircuit } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";

import { SparkLine } from "@/components/charts/Sparkline";
import { Badge, Panel, ProgressRing, Tooltip, type BadgeTone } from "@/components/ds";
import { useDrift } from "@/lib/api/hooks";
import { fmtPct, fmtSigned } from "@/lib/format";
import { useConnection, usePrediction } from "@/lib/store";

const DRIFT_TONE: Record<string, BadgeTone> = { edge: "good", no_edge: "warning", decayed: "serious", no_data: "neutral" };
const ROLL = 30;

/** Down | flat | up as one bar: the three calibrated probabilities sum to one. */
function ProbabilityBar({ down, flat, up }: { down: number; flat: number; up: number }) {
  const parts = [
    { key: "Down", p: down, color: "var(--color-ask)", dot: "bg-ask" },
    { key: "Flat", p: flat, color: "var(--color-ink-disabled)", dot: "bg-ink-disabled" },
    { key: "Up", p: up, color: "var(--color-bid)", dot: "bg-bid" },
  ];
  return (
    <div>
      <div
        className="flex h-3 gap-0.5 overflow-hidden rounded-sm"
        role="img"
        aria-label={parts.map((s) => `${s.key} ${fmtPct(s.p, 1)}`).join(", ")}
      >
        {parts.map((s) => (
          <div
            key={s.key}
            className="h-full transition-[flex-grow] duration-500 ease-out"
            style={{ flexGrow: Math.max(s.p, 0.004), flexBasis: 0, background: s.color }}
          />
        ))}
      </div>
      <div className="mt-2 grid grid-cols-3 text-meta">
        {parts.map((s, i) => (
          <span key={s.key} className={`flex items-center gap-1.5 ${i === 1 ? "justify-center" : i === 2 ? "justify-end" : ""}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} aria-hidden />
            <span className="text-ink-muted">{s.key}</span>
            <span className="num text-ink">{fmtPct(s.p, 1)}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

/** Rolling log-loss of the live predictions against the class-prior baseline (below the line = edge). */
function DriftSpark() {
  const { symbol } = useConnection();
  const drift = useDrift(symbol);
  const values = useMemo(() => {
    const s = drift.data?.series ?? [];
    const out: number[] = [];
    let sum = 0;
    s.forEach((o, i) => {
      sum += o.log_loss;
      if (i >= ROLL) sum -= s[i - ROLL]!.log_loss;
      if (i >= ROLL - 1) out.push(sum / ROLL);
    });
    return out;
  }, [drift.data]);
  if (values.length < 2) return null;
  return (
    <Tooltip
      content={`Rolling log-loss over ${ROLL} resolved predictions. The line is the class-prior baseline; staying below it is the edge.`}
    >
      <div tabIndex={0} className="w-24 shrink-0 rounded-sm">
        <SparkLine values={values} reference={drift.data?.summary.prior_log_loss} height={20} label="Rolling log-loss against the prior" />
      </div>
    </Tooltip>
  );
}

export function PredictionPanel({ className }: { className?: string }) {
  const p = usePrediction();
  const drift = p?.drift;
  const warming = !p || p.status !== "ready";
  const remaining = p ? Math.max(0, p.samples_required - p.samples) : null;

  return (
    <Panel
      className={className}
      icon={BrainCircuit}
      title="Model"
      subtitle={
        p
          ? `next ${p.horizon_s} s · barrier ±${p.barrier_bps.toFixed(2)} bps · v${p.model_version}`
          : "calibrated probability of the next move"
      }
      actions={<Badge tone={p?.signal === "long" ? "bid" : p?.signal === "short" ? "ask" : "neutral"}>{p?.signal ?? "flat"}</Badge>}
      footer={
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="flex shrink-0 items-center gap-2">
            Drift
            <Badge tone={DRIFT_TONE[drift?.status ?? "no_data"] ?? "neutral"}>{drift?.status.replace("_", " ") ?? "no data"}</Badge>
          </span>
          <DriftSpark />
          <span className="num ml-auto whitespace-nowrap">
            {drift && drift.status !== "no_data"
              ? `edge ${fmtSigned(drift.edge_vs_prior, 3)} vs prior`
              : drift
                ? `${drift.n}/${drift.n_required} resolved`
                : "—"}
          </span>
        </div>
      }
    >
      {warming ? (
        <div className="flex flex-1 items-center gap-4">
          <ProgressRing value={p ? p.samples / Math.max(1, p.samples_required) : 0} size={48} label="Labelled samples collected">
            <span className="num text-caption text-ink-muted">
              {p ? Math.round((p.samples / Math.max(1, p.samples_required)) * 100) : 0}%
            </span>
          </ProgressRing>
          <div className="min-w-0">
            <div className="text-body text-ink">
              {!p ? "Waiting for the model stream…" : p.training ? "Training the first model…" : "Collecting labelled samples"}
            </div>
            {p && (
              <div className="num mt-0.5 text-meta text-ink-faint">
                {p.samples} / {p.samples_required}
                {remaining ? ` · ~${Math.ceil(remaining / 60)} min at one bar per second` : ""}
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="flex flex-1 flex-col justify-center gap-3">
          <ProbabilityBar down={p.p_down ?? 0} flat={p.p_flat ?? 0} up={p.p_up ?? 0} />
          <p className="hint leading-snug">
            Chance the mid touches +{p.barrier_bps.toFixed(2)} or −{p.barrier_bps.toFixed(2)} bps first within {p.horizon_s} s, or neither ·{" "}
            {p.calibration && p.calibration !== "none"
              ? `${p.calibration}-calibrated on embargoed time splits`
              : "uncalibrated (too few samples to split)"}{" "}
            ·{" "}
            <Link href="/intelligence" className="text-ink-muted underline decoration-line-strong underline-offset-2 hover:text-ink">
              reliability
            </Link>
          </p>
        </div>
      )}
    </Panel>
  );
}
