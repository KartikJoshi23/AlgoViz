"use client";

import { Activity } from "lucide-react";
import { useMemo } from "react";

import { MiniSeries } from "@/components/charts/MiniSeries";
import { Badge, Divider, Panel, Skeleton, type BadgeTone } from "@/components/ds";
import { MetricTile } from "@/components/ui/PageHeader";
import { useDrift } from "@/lib/api/hooks";
import { fmtPct, fmtSigned } from "@/lib/format";
import { COLORS } from "@/lib/theme";

const WINDOW = 30;
const fmt3 = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? "—" : v.toFixed(3));
export const DRIFT_TONE: Record<string, BadgeTone> = { edge: "good", no_edge: "warning", decayed: "serious", no_data: "neutral" };

/** Live predictions scored against what the market did: summary tiles, rolling hit rate and log-loss. */
export function DriftPanel({ symbol, className }: { symbol: string | null; className?: string }) {
  const drift = useDrift(symbol);
  const s = drift.data?.summary;
  const series = drift.data?.series;
  const lines = useMemo(() => {
    const rows = series ?? [];
    const hit: (number | null)[] = [];
    const ll: (number | null)[] = [];
    let hits = 0;
    let lls = 0;
    rows.forEach((o, i) => {
      hits += o.hit ? 1 : 0;
      lls += o.log_loss;
      if (i >= WINDOW) {
        hits -= rows[i - WINDOW]!.hit ? 1 : 0;
        lls -= rows[i - WINDOW]!.log_loss;
      }
      const n = Math.min(i + 1, WINDOW);
      hit.push(i + 1 >= 10 ? hits / n : null);
      ll.push(i + 1 >= 10 ? lls / n : null);
    });
    return { hit, ll };
  }, [series]);
  const mix = (s?.realised_class_mix ?? null) as Record<string, number> | null;
  const trainEdge = s?.train_prior_log_loss != null && s.train_log_loss != null ? s.train_prior_log_loss - s.train_log_loss : null;

  return (
    <Panel
      className={className}
      icon={Activity}
      title="Drift monitor"
      subtitle={`live predictions scored against what happened · the latest ${s?.n ?? "…"} resolved`}
      actions={s && <Badge tone={DRIFT_TONE[s.status] ?? "neutral"}>{s.status.replace("_", " ")}</Badge>}
    >
      {!s && <Skeleton className="h-40" />}
      {s && (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
            <MetricTile
              label="Resolved"
              value={s.n}
              hint={s.n < s.n_required ? `metrics from ${s.n_required}` : `${s.total_resolved} in all`}
            />
            <MetricTile label="Hit rate" value={fmtPct(s.hit_rate, 1)} hint={`prior's own calls ${fmtPct(s.prior_hit_rate, 1)}`} />
            <MetricTile label="Directional hits" value={fmtPct(s.directional_hit_rate, 1)} hint="up / down calls only" />
            <MetricTile label="Log-loss" value={fmt3(s.log_loss)} hint={`class prior ${fmt3(s.prior_log_loss)}`} />
            <MetricTile
              label="Edge vs prior"
              value={fmtSigned(s.edge_vs_prior ?? null, 3)}
              hint={`at training ${fmtSigned(trainEdge, 3)}`}
            />
            <MetricTile
              label="Mean |move|"
              value={s.mean_abs_move_bps != null ? `${s.mean_abs_move_bps.toFixed(2)} bps` : "—"}
              hint="to barrier or horizon"
            />
          </div>
          <Divider className="my-4" />
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <div className="col-head mb-1">Rolling hit rate ({WINDOW})</div>
              <MiniSeries
                label={`Rolling hit rate over ${WINDOW} resolved predictions, against always calling the prior's likeliest class`}
                lines={[{ values: lines.hit, color: COLORS.accent, label: "hit rate", fill: true }]}
                baseline={s.prior_hit_rate != null ? { value: s.prior_hit_rate, label: "class prior" } : undefined}
                domain={[0, 1]}
                height={110}
                format={(v) => fmtPct(v, 0)}
                xLabel={(i) => `resolved prediction ${i + 1}`}
              />
            </div>
            <div>
              <div className="col-head mb-1">Rolling log-loss ({WINDOW}) · lower is better</div>
              <MiniSeries
                label={`Rolling log-loss over ${WINDOW} resolved predictions, against the class prior`}
                lines={[{ values: lines.ll, color: COLORS.accent, label: "log-loss" }]}
                baseline={s.prior_log_loss != null ? { value: s.prior_log_loss, label: "class prior" } : undefined}
                height={110}
                format={(v) => v.toFixed(3)}
                xLabel={(i) => `resolved prediction ${i + 1}`}
              />
            </div>
          </div>
          {mix && (
            <p className="num mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-meta text-ink-muted">
              <span className="text-ink-faint">Realised outcomes</span>
              {(["down", "flat", "up"] as const).map((k) => (
                <span key={k} className="flex items-center gap-1.5">
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${k === "down" ? "bg-ask" : k === "up" ? "bg-bid" : "bg-ink-disabled"}`}
                    aria-hidden
                  />
                  {k} {fmtPct(mix[k], 0)}
                </span>
              ))}
            </p>
          )}
        </>
      )}
    </Panel>
  );
}
