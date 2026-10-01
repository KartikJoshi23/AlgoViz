"use client";

import type { ReactNode } from "react";

import { Tooltip, cx } from "@/components/ds";
import { useSystemMetrics } from "@/lib/api/hooks";
import { fmtTime } from "@/lib/format";
import { useConnection, usePrediction, useStore } from "@/lib/store";
import { useNow } from "@/lib/useNow";
import { useFeedHealth } from "./AppBar";

/** A status read-out. A warning or critical state adds a status dot and lifts the text to full ink; the text itself stays ink. */
function Item({ label, children, tone }: { label: string; children: ReactNode; tone?: "warning" | "critical" }) {
  return (
    <Tooltip content={label}>
      <span
        tabIndex={0}
        className={cx("flex h-full items-center gap-1.5 rounded px-1.5 hover:bg-control hover:text-ink-muted", tone && "text-ink")}
      >
        {tone && <span className="status-dot" data-status={tone} aria-hidden />}
        {children}
      </span>
    </Tooltip>
  );
}

/** The terminal's bottom line: is the engine keeping up, and how fresh is what I'm looking at. */
export function StatusBar() {
  const conn = useConnection();
  const { health, text } = useFeedHealth();
  const metrics = useSystemMetrics();
  const prediction = usePrediction();
  const lastBarTs = useStore((s) => s.lastBarTs);
  const lastBarAt = useStore((s) => s.lastBarAt);
  const now = useNow(1000);

  const sym = metrics.data?.market?.symbols?.[conn.symbol];
  const loopP99 = metrics.data?.loop?.p99_ms;
  const barAge = lastBarAt ? Math.max(0, (now - lastBarAt) / 1000) : null;

  return (
    <footer className="float fixed inset-x-0 bottom-0 z-30 hidden h-7 border-x-0 border-b-0 md:block" aria-label="Engine status">
      <div className="num mx-auto flex h-full max-w-[1600px] items-center gap-1 px-4 text-caption text-ink-faint md:px-6">
        <Item label={`Socket ${conn.status} · feed ${text}`}>
          <span className="status-dot" data-status={health} />
          <span className="capitalize">{conn.source}</span>
          {sym?.event_rate_per_s != null && <span>{sym.event_rate_per_s.toFixed(1)} ev/s</span>}
        </Item>
        <Item
          label="Event-loop lag, p99 over the last minute — the server's responsiveness"
          tone={loopP99 == null ? undefined : loopP99 > 250 ? "critical" : loopP99 > 100 ? "warning" : undefined}
        >
          loop {loopP99 != null ? `${loopP99.toFixed(0)} ms` : "—"}
        </Item>
        <Item label="Local order book, rebuilt from the diff stream">
          book {sym?.book?.state ?? "—"}
          {sym?.book?.levels != null && ` · ${sym.book.levels.toLocaleString()} lv`}
        </Item>
        <Item label="Calibrated model serving predictions">
          model {prediction ? `v${prediction.model_version}` : "—"}
          {prediction && ` · ${prediction.training ? "training" : prediction.status.replace("_", " ")}`}
        </Item>
        <Item
          label="Close time of the newest 1-second bar; flagged when none has arrived for 5 s"
          tone={barAge != null && barAge > 5 ? "warning" : undefined}
        >
          bar {lastBarTs ? fmtTime(lastBarTs + 1000) : "—"}
        </Item>
        <span className="ml-auto flex items-center gap-3 pr-1.5">
          <span>rtt {conn.latencyMs != null ? `${conn.latencyMs} ms` : "—"}</span>
          <span className="text-ink-muted">{fmtTime(now)}</span>
        </span>
      </div>
    </footer>
  );
}
