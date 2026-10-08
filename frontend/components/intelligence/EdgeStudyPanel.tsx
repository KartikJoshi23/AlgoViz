"use client";

import { FlaskConical } from "lucide-react";

import { Badge, Panel, ProgressRing, Skeleton, TableWrap, type BadgeTone } from "@/components/ds";
import { MetricTile } from "@/components/ui/PageHeader";
import { useEdgeStudy, type EdgeStudy } from "@/lib/api/hooks";
import { fmtDuration, fmtPct, fmtSigned } from "@/lib/format";

type Study = NonNullable<EdgeStudy["study"]>;

const VERDICT: Record<Study["verdict"]["kind"], { tone: BadgeTone; label: string }> = {
  exploratory: { tone: "neutral", label: "exploratory" },
  preliminary: { tone: "neutral", label: "preliminary" },
  too_few: { tone: "neutral", label: "too few samples" },
  no_holdout: { tone: "neutral", label: "no holdout" },
  no_edge: { tone: "warning", label: "no edge" },
  adopt: { tone: "good", label: "edge found" },
};
const utc = (ms: number) => `${new Date(ms).toISOString().slice(0, 16).replace("T", " ")} UTC`;
const fmt3 = (v: number) => v.toFixed(3);

/**
 * The pre-registered edge study (docs/edge-study-protocol.md): whether any tested
 * label definition and training window beats both priors when the model is
 * refitted as served, and how far the bars that decide it have come. Only bars
 * from the protocol's freeze on can decide; a run on earlier bars explores.
 */
export function EdgeStudyPanel({ symbol, className }: { symbol: string | null; className?: string }) {
  const q = useEdgeStudy(symbol);
  const c = q.data?.collection;
  const study = q.data?.study ?? null;
  const verdict = study ? VERDICT[study.verdict.kind] : null;
  const progress = c ? c.days_since_freeze / c.days_required : 0;

  return (
    <Panel
      className={className}
      icon={FlaskConical}
      title="Edge study"
      subtitle={
        study
          ? `protocol ${study.protocol ?? "—"} · ${study.configurations} configurations, refitted as served`
          : "a rule fixed in advance decides whether the model has an edge"
      }
      actions={verdict && <Badge tone={verdict.tone}>{verdict.label}</Badge>}
    >
      {!c && <Skeleton className="h-32" />}
      {c && (
        <>
          <div className="flex flex-wrap items-center gap-4">
            <ProgressRing value={progress} size={56} label="Days of deciding bars collected">
              <span className="num text-caption text-ink">{fmtPct(Math.min(1, progress), 0)}</span>
            </ProgressRing>
            <div className="min-w-0 flex-1">
              <p className="text-body text-ink">
                <span className="num">{c.days_since_freeze.toFixed(2)}</span> of {c.days_required} days of bars since the protocol froze,{" "}
                {utc(c.freeze_ms)}
              </p>
              <p className="text-meta text-ink-muted">
                <span className="num">{c.bars.toLocaleString()}</span> {c.source} bars stored · newest{" "}
                {c.newest_age_s != null ? `${fmtDuration(c.newest_age_s)} ago` : "—"} · kept {c.retention_days} days
              </p>
            </div>
          </div>
          {!study && (
            <p className="mt-4 text-body text-ink-faint">
              No study has run on this host yet. <code className="num">scripts/ml_study.py</code> explores the bars from before the freeze;{" "}
              <code className="num">--decide</code> runs once there are {c.days_required} days of bars from it on.
            </p>
          )}
          {study && <StudyReport study={study} />}
        </>
      )}
    </Panel>
  );
}

/** A study report as the API returns it: the verdict, four summary tiles and the best configurations. */
export function StudyReport({ study }: { study: Study }) {
  const { best, holdout, data, rule } = study;
  const better = holdout && Math.min(holdout.prior_log_loss, holdout.trailing_prior_log_loss);
  return (
    <>
      <p className="mt-4 text-body text-ink">{study.verdict.reason.charAt(0).toUpperCase() + study.verdict.reason.slice(1)}.</p>
      <div className="mt-3 grid grid-cols-2 gap-2 xl:grid-cols-4">
        <MetricTile
          label="Best in development"
          value={fmtSigned(best?.edge ?? null, 3)}
          hint={best ? `${best.quarters_beating} of ${best.quarters} quarters beat both priors` : "nothing scored"}
        />
        <MetricTile
          label="Holdout"
          value={fmtSigned(holdout?.edge ?? null, 3)}
          hint={holdout && better != null ? `log-loss ${fmt3(holdout.log_loss)} vs ${fmt3(better)}` : "not scored"}
        />
        <MetricTile
          label="Data"
          value={`${data.days.toFixed(2)} days`}
          hint={`${study.deciding ? "from the freeze on" : "from before the freeze"} · ${data.sessions} sessions`}
        />
        <MetricTile
          label="Rule"
          value={`${rule.min_quarters_beating} of ${rule.quarters}`}
          hint={`quarters, and the holdout · ${rule.min_days} days`}
        />
      </div>
      {best && (
        <p className="mt-3 text-meta text-ink-muted">
          Best: {best.label} · {best.features} · {best.training}. Edges are log-loss improvements in nats over the better of the class prior
          and the trailing prior; the holdout was scored once.
        </p>
      )}
      <TableWrap label="Best configurations of the edge study" className="mt-4">
        <table className="data-table">
          <thead>
            <tr>
              <th>Label</th>
              <th>Features</th>
              <th>Training</th>
              <th className="cell-num">vs better prior</th>
              <th className="cell-num">vs class prior</th>
              <th className="cell-num">vs trailing</th>
              <th className="cell-num">Quarters</th>
            </tr>
          </thead>
          <tbody>
            {study.top.slice(0, 8).map((r) => (
              <tr key={`${r.label}·${r.features}·${r.training}`}>
                <td>{r.label}</td>
                <td className="text-ink-muted">{r.features}</td>
                <td className="text-ink-muted">{r.training}</td>
                <td className="cell-num">
                  {fmtSigned(r.edge, 3)}
                  {r.edge_sd != null && <span className="text-ink-faint"> ± {r.edge_sd.toFixed(3)}</span>}
                </td>
                <td className="cell-num text-ink-muted">{fmtSigned(r.edge_vs_prior, 3)}</td>
                <td className="cell-num text-ink-muted">{fmtSigned(r.edge_vs_trailing_prior, 3)}</td>
                <td className="cell-num">
                  {r.quarters_beating} of {r.quarters}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
    </>
  );
}
