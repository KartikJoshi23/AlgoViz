"use client";

import { BellRing, Check, CheckCheck, History, ListChecks, Pencil, Plus, Trash2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { RuleDrawer } from "@/components/alerts/RuleForm";
import { Badge, Button, Panel, Select, Skeleton, Switch, TableWrap, type BadgeTone } from "@/components/ds";
import { EmptyState, PageHeader } from "@/components/ui/PageHeader";
import { useAlertHistory, useAlertMutations, useAlertRules, useSystemMetrics, type AlertHistory, type AlertRule } from "@/lib/api/hooks";
import { fmtAgo } from "@/lib/format";
import { useAlerts, useStore } from "@/lib/store";
import { useNow } from "@/lib/useNow";

const PRIORITY_TONE: Record<string, BadgeTone> = {
  critical: "critical",
  high: "serious",
  medium: "warning",
  low: "neutral",
  info: "accent",
};
const PRIORITY_DOT: Record<string, string> = {
  critical: "bg-critical",
  high: "bg-serious",
  medium: "bg-warning",
  low: "bg-ink-faint",
  info: "bg-accent",
};
const CMP: Record<string, string> = { gt: ">", gte: "≥", lt: "<", lte: "≤", eq: "=", in: "in" };

function RulesTable({ rules, now, onEdit }: { rules: AlertRule[]; now: number; onEdit: (r: AlertRule) => void }) {
  const { update, remove } = useAlertMutations();
  const addToast = useStore((s) => s.addToast);
  const del = async (rule: AlertRule) => {
    if (!window.confirm(`Delete rule "${rule.name}"?`)) return;
    try {
      await remove.mutateAsync(rule.id);
    } catch (e) {
      addToast({ tone: "critical", title: "Could not delete rule", body: (e as Error).message });
    }
  };
  return (
    <TableWrap label="Alert rules">
      <table className="data-table">
        <thead>
          <tr>
            <th>On</th>
            <th>Rule</th>
            <th>Fires when</th>
            <th>Priority</th>
            <th className="cell-num">Cooldown</th>
            <th>Last fired</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {rules.map((r) => (
            <tr key={r.id} className={r.is_enabled ? undefined : "text-ink-faint"}>
              <td>
                <Switch
                  checked={r.is_enabled}
                  onChange={(v) => update.mutate({ id: r.id, body: { is_enabled: v } })}
                  aria-label={`Enable ${r.name}`}
                />
              </td>
              <td>
                <span className="flex items-center gap-2">
                  <span className={r.is_enabled ? "text-ink" : "text-ink-faint"}>{r.name}</span>
                  {r.notify_discord && <Badge tone="accent">Discord</Badge>}
                </span>
              </td>
              <td className="num text-meta text-ink-muted">
                {r.condition_field} {CMP[r.comparison] ?? r.comparison} {r.threshold}
              </td>
              <td>
                <Badge tone={PRIORITY_TONE[r.priority] ?? "neutral"}>{r.priority}</Badge>
              </td>
              <td className="cell-num text-ink-muted">{r.cooldown_seconds} s</td>
              <td
                className="text-ink-muted"
                title={r.last_fired_at ? new Date(r.last_fired_at).toLocaleString([], { hour12: false }) : undefined}
              >
                {r.last_fired_at ? (now ? `${fmtAgo(new Date(r.last_fired_at).getTime(), now)} ago` : "—") : "never"}
              </td>
              <td>
                <span className="flex justify-end gap-1">
                  <Button variant="ghost" size="sm" icon onClick={() => onEdit(r)} aria-label="Edit rule">
                    <Pencil size={14} />
                  </Button>
                  <Button variant="ghost" size="sm" icon onClick={() => void del(r)} aria-label="Delete rule" disabled={remove.isPending}>
                    <Trash2 size={14} />
                  </Button>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}

const dayLabel = (t: Date, now: number) => {
  const today = new Date(now || t.getTime());
  const d = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const days = Math.round((d(today) - d(t)) / 86_400_000);
  return days === 0 ? "Today" : days === 1 ? "Yesterday" : t.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
};

/** Firings as a timeline grouped by day, newest first; each can be acknowledged. */
function HistoryTimeline({ items, now, onAck }: { items: AlertHistory[]; now: number; onAck: (id: number) => void }) {
  const groups = useMemo(() => {
    const out: { label: string; items: AlertHistory[] }[] = [];
    for (const a of items) {
      const label = dayLabel(new Date(a.triggered_at), now);
      const last = out[out.length - 1];
      if (last && last.label === label) last.items.push(a);
      else out.push({ label, items: [a] });
    }
    return out;
  }, [items, now]);

  return (
    <div className="space-y-4">
      {groups.map((g) => (
        <section key={g.label} aria-label={g.label}>
          <h3 className="col-head mb-2">{g.label}</h3>
          <ol className="relative space-y-1 before:absolute before:bottom-2 before:left-[90px] before:top-2 before:w-px before:bg-line">
            {g.items.map((a) => (
              <li
                key={a.id}
                className={`row enter grid grid-cols-[4.25rem_1.25rem_1fr_auto] items-start gap-x-2 px-1 py-2 ${a.acknowledged ? "opacity-60" : ""}`}
              >
                <time
                  className="num pt-0.5 text-right text-meta text-ink-muted"
                  dateTime={a.triggered_at}
                  title={new Date(a.triggered_at).toLocaleString([], { hour12: false })}
                >
                  {new Date(a.triggered_at).toLocaleTimeString([], { hour12: false })}
                </time>
                <span className="flex justify-center pt-1.5" aria-hidden>
                  <span className={`h-2.5 w-2.5 rounded-full ring-4 ring-panel ${PRIORITY_DOT[a.priority] ?? "bg-ink-faint"}`} />
                </span>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-body font-medium text-ink">{a.rule_name}</span>
                    <Badge tone={PRIORITY_TONE[a.priority] ?? "neutral"}>{a.priority}</Badge>
                  </div>
                  <p className="mt-0.5 text-meta text-ink-muted">{a.message}</p>
                  {a.value != null && (
                    <p className="num mt-0.5 text-caption text-ink-faint">
                      {a.field} = {a.value.toPrecision(4)}
                      {a.threshold != null ? ` · limit ${a.threshold}` : ""}
                    </p>
                  )}
                </div>
                {a.acknowledged ? (
                  <span className="flex items-center gap-1 pt-0.5 text-caption text-ink-faint">
                    <Check size={12} aria-hidden /> seen
                  </span>
                ) : (
                  <Button variant="ghost" size="sm" onClick={() => onAck(a.id)} aria-label="Acknowledge">
                    <Check size={14} /> Ack
                  </Button>
                )}
              </li>
            ))}
          </ol>
        </section>
      ))}
    </div>
  );
}

export default function AlertsPage() {
  const rules = useAlertRules();
  const metrics = useSystemMetrics();
  const [priority, setPriority] = useState<string>("");
  const [unackOnly, setUnackOnly] = useState(false);
  const history = useAlertHistory({ limit: 100, ...(priority ? { priority } : {}), unacknowledged_only: unackOnly });
  const live = useAlerts();
  const { acknowledge, acknowledgeAll } = useAlertMutations();
  const [editing, setEditing] = useState<AlertRule | "new" | null>(null);
  const now = useNow(5_000);
  const qc = useQueryClient();

  // a live alert means a rule fired: refresh last_fired_at and the persisted history
  useEffect(() => {
    if (live.length === 0) return;
    qc.invalidateQueries({ queryKey: ["alert-rules"] });
    qc.invalidateQueries({ queryKey: ["alert-history"] });
  }, [live.length, qc]);

  const discordConfigured = Boolean(metrics.data?.market?.alerts?.discord?.enabled);

  // live WS alerts that the last REST page hasn't caught up with yet
  const merged = useMemo(() => {
    const rest = history.data?.pages.flatMap((p) => p.items) ?? [];
    const seen = new Set(rest.map((a) => a.id));
    const fresh: AlertHistory[] = live
      .filter((a) => !seen.has(a.id))
      .filter((a) => (!priority || a.priority === priority) && !unackOnly)
      .map((a) => ({ ...a, acknowledged: false, acknowledged_at: null }));
    return [...fresh, ...rest];
  }, [history.data, live, priority, unackOnly]);
  const unacked = merged.filter((a) => !a.acknowledged).length;

  return (
    <div className="space-y-3">
      <PageHeader
        eyebrow="Monitoring"
        title="Alerts"
        subtitle="threshold rules on any catalog feature · checked every second · Discord delivery"
        actions={
          <>
            <Button onClick={() => acknowledgeAll.mutate()} disabled={unacked === 0 || acknowledgeAll.isPending}>
              <CheckCheck size={14} /> Acknowledge all {unacked > 0 && `(${unacked})`}
            </Button>
            <Button variant="primary" onClick={() => setEditing("new")}>
              <Plus size={14} /> New rule
            </Button>
          </>
        }
      />

      <RuleDrawer
        key={editing === "new" ? "new" : (editing?.id ?? "closed")}
        rule={editing === "new" ? null : editing}
        open={editing != null}
        onClose={() => setEditing(null)}
        discordConfigured={discordConfigured}
      />

      <div className="grid gap-3 lg:grid-cols-12">
        <Panel
          className="self-start lg:col-span-7"
          icon={ListChecks}
          title="Rules"
          subtitle={`${rules.data?.length ?? 0} configured · ${rules.data?.filter((r) => r.is_enabled).length ?? 0} on`}
        >
          {rules.isLoading && <Skeleton className="h-24" />}
          {rules.data && rules.data.length === 0 && (
            <EmptyState
              title="No rules yet"
              body="Alert on any catalog feature: spread z-score above 2σ, liquidity within 10 bps below a floor, a velocity spike, the model probability above a threshold."
              action={
                <Button variant="primary" onClick={() => setEditing("new")}>
                  <Plus size={14} /> New rule
                </Button>
              }
            />
          )}
          {rules.data && rules.data.length > 0 && <RulesTable rules={rules.data} now={now} onEdit={setEditing} />}
        </Panel>

        <Panel
          className="self-start lg:col-span-5"
          icon={History}
          title="History"
          subtitle={`${merged.length} shown · ${unacked} unacknowledged`}
          actions={
            <>
              <Select
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
                className="h-8 w-auto text-meta"
                aria-label="Priority filter"
              >
                <option value="">All priorities</option>
                {Object.keys(PRIORITY_TONE).map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </Select>
              <Switch checked={unackOnly} onChange={setUnackOnly} label="Unacknowledged" />
            </>
          }
        >
          {history.isLoading && <Skeleton className="h-24" />}
          {merged.length === 0 && !history.isLoading && (
            <div className="flex items-center gap-2 py-6 text-body text-ink-faint">
              <BellRing size={14} aria-hidden /> Nothing has fired{unackOnly || priority ? " for this filter" : " yet"}.
            </div>
          )}
          {merged.length > 0 && (
            <div className="max-h-[70vh] overflow-y-auto pr-1" tabIndex={0} role="region" aria-label="Alert history">
              <HistoryTimeline items={merged} now={now} onAck={(id) => acknowledge.mutate(id)} />
              {history.hasNextPage && (
                <div className="mt-3 flex justify-center">
                  <Button size="sm" variant="ghost" onClick={() => void history.fetchNextPage()} disabled={history.isFetchingNextPage}>
                    {history.isFetchingNextPage ? "Loading…" : "Load older alerts"}
                  </Button>
                </div>
              )}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
