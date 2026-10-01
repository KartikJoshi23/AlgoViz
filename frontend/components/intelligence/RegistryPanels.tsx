"use client";

import { Boxes, SlidersHorizontal } from "lucide-react";

import { Badge, Panel, TableWrap, type BadgeTone } from "@/components/ds";
import { useModelRegistry, useSignalRules } from "@/lib/api/hooks";
import { fmtAgo, fmtSigned } from "@/lib/format";
import { useSignals, useStore } from "@/lib/store";
import { useNow } from "@/lib/useNow";

// ── Model registry ──────────────────────────────────────────────────

/** Every training run as a timeline, newest first; the active version serves live predictions. */
export function RegistryPanel({ symbol }: { symbol: string | null }) {
  const reg = useModelRegistry(symbol);
  const now = useNow(60_000);
  const rows = reg.data?.items ?? [];
  return (
    <Panel
      icon={Boxes}
      title="Model registry"
      subtitle={`${rows.length} training run${rows.length === 1 ? "" : "s"} · held-out log-loss and edge vs the class prior`}
    >
      {rows.length === 0 && <p className="py-6 text-body text-ink-faint">No models registered yet.</p>}
      {rows.length > 0 && (
        <TableWrap label="Model registry" maxHeight={340}>
          <table className="data-table">
            <thead>
              <tr>
                <th aria-label="Timeline" className="w-6" />
                <th>Version</th>
                <th>Trained</th>
                <th className="cell-num">Samples</th>
                <th className="cell-num">Log-loss</th>
                <th className="cell-num">Edge</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m, i) => {
                const oos = ((m.metrics as { oos?: Record<string, number> } | null)?.oos ?? {}) as Record<string, number>;
                const trained = new Date(m.trained_at).getTime();
                return (
                  <tr key={m.id} data-selected={m.is_active ? "" : undefined}>
                    <td className="relative" aria-hidden>
                      <span
                        className={`absolute left-1/2 w-px bg-line-strong ${i === 0 ? "top-1/2" : "top-0"} ${i === rows.length - 1 ? "bottom-1/2" : "bottom-0"}`}
                      />
                      <span
                        className={`relative mx-auto block h-2.5 w-2.5 rounded-full ring-2 ring-panel ${m.is_active ? "bg-accent" : "bg-ink-disabled"}`}
                      />
                    </td>
                    <td>
                      <span className="flex items-center gap-2">
                        <span className="num">v{m.version}</span>
                        {m.is_active && <Badge tone="good">active</Badge>}
                      </span>
                    </td>
                    <td className="text-ink-muted" title={new Date(m.trained_at).toLocaleString([], { hour12: false })}>
                      {now ? `${fmtAgo(trained, now)} ago` : new Date(m.trained_at).toLocaleTimeString([], { hour12: false })}
                    </td>
                    <td className="cell-num text-ink-muted">{m.training_samples?.toLocaleString() ?? "—"}</td>
                    <td className="cell-num">{oos.log_loss != null ? oos.log_loss.toFixed(3) : "—"}</td>
                    <td className="cell-num">{fmtSigned(oos.edge_vs_prior ?? null, 3)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </TableWrap>
      )}
    </Panel>
  );
}

// ── Signal rules ────────────────────────────────────────────────────

const PRIORITY_TONE: Record<string, BadgeTone> = { high: "serious", medium: "warning", low: "neutral" };
const PRIORITY_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };

/** The signal rule set with each rule's live state: active ones first, with how long they have held. */
export function SignalRulesPanel({ symbol }: { symbol: string | null }) {
  const rules = useSignalRules(symbol);
  const { active } = useSignals();
  const lastBarTs = useStore((s) => s.lastBarTs);
  const now = lastBarTs ? lastBarTs + 1000 : 0; // event time, like the engine
  const since = new Map(active.map((a) => [a.rule_id, a.activated_at_ms]));
  const rows = [...(rules.data ?? [])].sort(
    (a, b) => Number(since.has(b.id)) - Number(since.has(a.id)) || (PRIORITY_ORDER[a.priority] ?? 9) - (PRIORITY_ORDER[b.priority] ?? 9),
  );

  return (
    <Panel
      icon={SlidersHorizontal}
      title="Signal rules"
      subtitle={`${rows.length} rules on z-scores, regime and the model, with hysteresis, minimum duration and cooldown · ${since.size} active`}
    >
      <TableWrap label="Signal rules" maxHeight={520}>
        <table className="data-table">
          <thead>
            <tr>
              <th>State</th>
              <th>Rule</th>
              <th>Priority</th>
              <th>Enters when</th>
              <th>Exits when</th>
              <th className="cell-num">Min hold</th>
              <th className="cell-num">Cooldown</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const at = since.get(r.id);
              return (
                <tr key={r.id} className="row" data-selected={at != null ? "" : undefined}>
                  <td>
                    <span className="flex items-center gap-2 text-meta">
                      <span className="status-dot" data-status={at != null ? "warning" : undefined} aria-hidden />
                      {at != null ? `active ${now ? fmtAgo(at, now) : ""}` : <span className="text-ink-faint">idle</span>}
                    </span>
                  </td>
                  <td>
                    <span className="block text-ink">{r.name}</span>
                    <span className="block max-w-[22rem] truncate text-caption text-ink-faint" title={r.action}>
                      {r.action} · {r.tags.join(" · ")}
                    </span>
                  </td>
                  <td>
                    <Badge tone={PRIORITY_TONE[r.priority] ?? "neutral"}>{r.priority}</Badge>
                  </td>
                  <td className="num text-meta text-ink-muted">{r.enter_text}</td>
                  <td className="num text-meta text-ink-muted">{r.exit_text}</td>
                  <td className="cell-num text-ink-muted">{r.min_duration_s} s</td>
                  <td className="cell-num text-ink-muted">{r.cooldown_s} s</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </TableWrap>
    </Panel>
  );
}
