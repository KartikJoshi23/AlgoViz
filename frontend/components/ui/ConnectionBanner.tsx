"use client";

import { useConnection, useStore } from "@/lib/store";
import { useNow } from "@/lib/useNow";

/**
 * Shown only when something is wrong: the connection dropped or failed, or the
 * market feed is not flowing. The first connection is not announced: it opens
 * within a second, and a banner that appears and vanishes would push the page
 * down and back up (a layout shift on every load). A failed first attempt
 * becomes "reconnecting" and shows.
 */
export function ConnectionBanner() {
  const conn = useConnection();
  const sourceStatus = useStore((s) => s.sourceStatus);
  const now = useNow(250, conn.status !== "open");

  const degraded = conn.status === "open" && sourceStatus && !["connected", "idle"].includes(sourceStatus.status);
  const firstConnect = conn.status === "idle" || conn.status === "connecting";
  if ((conn.status === "open" && !degraded) || firstConnect) return null;

  const retryIn = conn.nextRetryAt ? Math.max(0, Math.ceil((conn.nextRetryAt - now) / 1000)) : null;
  const critical = conn.status === "closed" || sourceStatus?.status === "failed" || sourceStatus?.status === "geo_blocked";
  const text =
    conn.status === "reconnecting"
      ? `No connection to the market engine — retrying${retryIn != null ? ` in ${retryIn}s` : ""} (attempt ${conn.attempt})`
      : conn.status === "closed"
        ? "Disconnected from the market engine"
        : degraded
          ? `Market feed ${sourceStatus?.status.replace("_", " ")}${sourceStatus?.detail ? ` · ${sourceStatus.detail}` : ""}`
          : "";

  return (
    <div
      className="border-b border-line"
      style={{
        background: `color-mix(in oklab, var(--color-${critical ? "critical" : "warning"}) 10%, var(--color-page))`,
      }}
      role="status"
      aria-live="polite"
    >
      <div className="mx-auto flex h-9 max-w-[1600px] items-center gap-2.5 px-4 text-body md:px-6">
        <span className="status-dot" data-status={critical ? "critical" : "warning"} />
        <span className="text-ink">{text}</span>
        <span className="ml-auto text-meta capitalize text-ink-faint">{conn.source} data</span>
      </div>
    </div>
  );
}
