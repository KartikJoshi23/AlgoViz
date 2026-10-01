"use client";

import { Radar, Zap } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge, Panel } from "@/components/ds";
import { useSignalHistory } from "@/lib/api/hooks";
import { fmtAgo, fmtTime } from "@/lib/format";
import { useConnection, useSignals, useStore } from "@/lib/store";
import type { ActiveSignal, SignalTransition } from "@/lib/ws/types";

const WINDOW_MS = 10 * 60_000;
const MAX_LANES = 5;
const PRIORITY_ORDER = { high: 0, medium: 1, low: 2 } as const;
const PRIORITY_BAR = { high: "bg-serious", medium: "bg-warning", low: "bg-ink-faint" } as const;

function priorityTone(p: string): "serious" | "warning" | "neutral" {
  return p === "high" ? "serious" : p === "medium" ? "warning" : "neutral";
}

interface Interval {
  from: number;
  to: number;
  open: boolean;
}
interface Lane {
  ruleId: string;
  name: string;
  priority: keyof typeof PRIORITY_ORDER;
  intervals: Interval[];
}

/**
 * Activation intervals per rule over the last ten minutes of event time: the
 * engine's recent history (REST, once) extended by live transitions, with
 * still-active signals running to now.
 */
function useLanes(now: number, active: ActiveSignal[], feed: SignalTransition[]): Lane[] {
  const { symbol } = useConnection();
  const history = useSignalHistory(symbol);
  return useMemo(() => {
    if (!now) return [];
    const start = now - WINDOW_MS;
    const lanes = new Map<string, Lane>();
    const seen = new Set<string>();
    const add = (id: string, name: string, priority: Lane["priority"], from: number, to: number, open: boolean) => {
      const key = `${id}:${from}`;
      if (seen.has(key) || to < start) return;
      seen.add(key);
      const lane = lanes.get(id) ?? { ruleId: id, name, priority, intervals: [] };
      lane.intervals.push({ from: Math.max(from, start), to: Math.min(to, now), open });
      lanes.set(id, lane);
    };
    for (const s of active) add(s.rule_id, s.name, s.priority, s.activated_at_ms, now, true);
    for (const t of [...feed, ...(history.data?.recent ?? [])]) {
      if (t.kind === "deactivated") add(t.rule_id, t.name, t.priority, t.activated_at_ms, t.ts_ms, false);
    }
    return [...lanes.values()].sort(
      (a, b) =>
        PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority] ||
        Math.max(...b.intervals.map((i) => i.to)) - Math.max(...a.intervals.map((i) => i.to)),
    );
  }, [now, active, feed, history.data]);
}

function Timeline({ lanes, now }: { lanes: Lane[]; now: number }) {
  const [hover, setHover] = useState<{ lane: Lane; iv: Interval; x: number; y: number } | null>(null);
  const shown = lanes.slice(0, MAX_LANES);
  const pct = (t: number) => `${((t - (now - WINDOW_MS)) / WINDOW_MS) * 100}%`;
  return (
    <div className="relative">
      <div className="space-y-1.5">
        {shown.map((lane) => (
          <div key={lane.ruleId} className="grid grid-cols-[7.5rem_1fr] items-center gap-2">
            <span className="truncate text-meta text-ink-muted" title={lane.name}>
              {lane.name}
            </span>
            <div
              className="relative h-2.5 rounded-sm bg-raised"
              onPointerMove={(e) => {
                const r = e.currentTarget.getBoundingClientRect();
                const t = now - WINDOW_MS + ((e.clientX - r.left) / r.width) * WINDOW_MS;
                const iv = lane.intervals.find((i) => t >= i.from - 2000 && t <= i.to + 2000);
                const host = e.currentTarget.parentElement!.parentElement!.getBoundingClientRect();
                setHover(iv ? { lane, iv, x: e.clientX - host.left, y: r.top - host.top } : null);
              }}
              onPointerLeave={() => setHover(null)}
            >
              {lane.intervals.map((iv) => (
                <span
                  key={iv.from}
                  className={`absolute inset-y-0 min-w-[3px] rounded-sm ${PRIORITY_BAR[lane.priority]} ${iv.open ? "" : "opacity-70"}`}
                  style={{ left: pct(iv.from), width: `calc(${pct(iv.to)} - ${pct(iv.from)})` }}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="num mt-1 grid grid-cols-[7.5rem_1fr] gap-2 text-caption text-ink-faint">
        <span>{lanes.length > MAX_LANES ? `+${lanes.length - MAX_LANES} more rules` : ""}</span>
        <span className="flex justify-between">
          <span>−10 min</span>
          <span>−5 min</span>
          <span>now</span>
        </span>
      </div>
      {hover && (
        <div
          className="float pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-md px-2 py-1 text-caption"
          style={{ left: hover.x, top: hover.y - 6 }}
        >
          <span className="text-ink">{hover.lane.name}</span>
          <span className="num text-ink-faint">
            {" "}
            · {fmtTime(hover.iv.from)}–{hover.iv.open ? "now" : fmtTime(hover.iv.to)} ({Math.round((hover.iv.to - hover.iv.from) / 1000)} s)
          </span>
        </div>
      )}
    </div>
  );
}

function ActiveRow({ s, now }: { s: ActiveSignal; now: number }) {
  return (
    <li className="raised enter px-3 py-2">
      <div className="flex items-center gap-2">
        <Badge tone={priorityTone(s.priority)}>{s.priority}</Badge>
        <span className="truncate text-body font-medium text-ink">{s.name}</span>
        {now > 0 && <span className="num ml-auto shrink-0 text-caption text-ink-faint">{fmtAgo(s.activated_at_ms, now)}</span>}
      </div>
      <p className="mt-1 text-meta leading-snug text-ink-muted">{s.message}</p>
      {s.action && <p className="mt-0.5 text-meta text-ink-faint">→ {s.action}</p>}
    </li>
  );
}

export function SignalsFeed({ className }: { className?: string }) {
  const { active, feed } = useSignals();
  // event time, so replay and live read the same: the close of the newest bar
  const lastBarTs = useStore((s) => s.lastBarTs);
  const now = lastBarTs ? lastBarTs + 1000 : 0;
  const lanes = useLanes(now, active, feed);

  return (
    <Panel
      className={className}
      icon={Zap}
      title="Signals"
      subtitle="rules with hysteresis · last 10 min"
      actions={<Badge tone={active.length ? "warning" : "neutral"}>{active.length} active</Badge>}
      bodyClassName="gap-3"
    >
      {lanes.length > 0 && <Timeline lanes={lanes} now={now} />}
      <div className="min-h-0 flex-1 overflow-y-auto" tabIndex={0} role="region" aria-label="Active signals">
        {active.length === 0 ? (
          <div className="flex items-start gap-3 rounded-lg border border-dashed border-line-strong px-3 py-3">
            <Radar className="mt-0.5 h-4 w-4 shrink-0 text-ink-faint" aria-hidden />
            <div>
              <div className="text-body text-ink">Nothing unusual right now</div>
              <p className="mt-0.5 text-meta leading-snug text-ink-faint">
                Rules fire when a feature leaves its 15-minute baseline by 2σ or more.
              </p>
            </div>
          </div>
        ) : (
          <ul className="space-y-2">
            {active.map((s) => (
              <ActiveRow key={s.rule_id} s={s} now={now} />
            ))}
          </ul>
        )}
      </div>
    </Panel>
  );
}
