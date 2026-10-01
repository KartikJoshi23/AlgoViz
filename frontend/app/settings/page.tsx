"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Cable, Globe, KeyRound, MonitorCog, RotateCcw, Server } from "lucide-react";
import { useEffect, useState, useSyncExternalStore, type ReactNode } from "react";

import { Badge, Button, Divider, Field, Input, Panel, SegmentedControl, Select, Switch } from "@/components/ds";
import { MetricTile, PageHeader } from "@/components/ui/PageHeader";
import { API_URL, WS_URL, readAdminToken, subscribeAdminToken, writeAdminToken } from "@/lib/api/client";
import { useAccess, useHealth, useSystemMetrics } from "@/lib/api/hooks";
import { fmtAgo } from "@/lib/format";
import { useConnection, useEffectiveMotion, useEffectiveTier, useStore, type MotionPref, type PerfTier } from "@/lib/store";
import { useNow } from "@/lib/useNow";

const DEFAULT_PREFS = { perfTier: "auto", motion: "auto", accentIntensity: 1, bookSubscribed: true, symbol: null } as const;

const SECTIONS = [
  { id: "market", label: "Market" },
  { id: "display", label: "Display" },
  { id: "connection", label: "Connection" },
  { id: "access", label: "Access" },
  { id: "engine", label: "Engine" },
] as const;

/** One read-out row: a term and its value. */
function KV({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1 text-meta">
      <dt className="text-ink-faint">{k}</dt>
      <dd className="num min-w-0 truncate text-right text-ink">{children}</dd>
    </div>
  );
}

function Status({ tone, children }: { tone: "good" | "warning" | "critical" | undefined; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="status-dot" data-status={tone} aria-hidden />
      {children}
    </span>
  );
}

/**
 * The section in view, for the side index: the first section, in page order,
 * inside the upper part of the viewport. Callbacks only report the entries
 * that changed, so every section's visibility is tracked.
 */
function useActiveSection(): string {
  const [active, setActive] = useState<string>(SECTIONS[0].id);
  useEffect(() => {
    const els = SECTIONS.map((s) => document.getElementById(s.id)).filter((e): e is HTMLElement => !!e);
    const inView = new Set<string>();
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) inView.add(e.target.id);
          else inView.delete(e.target.id);
        }
        const first = SECTIONS.find((s) => inView.has(s.id));
        if (first) setActive(first.id);
      },
      { rootMargin: "-80px 0px -55% 0px" },
    );
    els.forEach((e) => io.observe(e));
    return () => io.disconnect();
  }, []);
  return active;
}

export default function SettingsPage() {
  const prefs = useStore((s) => s.prefs);
  const setPrefs = useStore((s) => s.setPrefs);
  const ui = useStore((s) => s.ui);
  const conn = useConnection();
  const motion = useEffectiveMotion();
  const tier = useEffectiveTier();
  const health = useHealth();
  const metrics = useSystemMetrics();
  const now = useNow(1000);
  const active = useActiveSection();
  const m = metrics.data;
  const sym = m?.market?.symbols?.[conn.symbol];
  const resyncs = sym?.book?.resyncs ?? 0;
  const failedFlushes = m?.market?.writer?.failed_flushes ?? 0;

  return (
    <div className="space-y-3">
      <PageHeader eyebrow="Preferences" title="Settings" subtitle="preferences live in this browser · the engine runs on the server" />

      <div className="grid gap-3 lg:grid-cols-[11rem_minmax(0,1fr)]">
        <nav aria-label="Settings sections" className="lg:sticky lg:top-[72px] lg:self-start">
          <ul className="flex gap-1 overflow-x-auto lg:flex-col">
            {SECTIONS.map((s) => (
              <li key={s.id}>
                <a
                  href={`#${s.id}`}
                  className="nav-link w-full"
                  data-active={active === s.id}
                  aria-current={active === s.id ? "location" : undefined}
                >
                  {s.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="min-w-0 space-y-3">
          <Panel id="market" className="scroll-mt-20" icon={Globe} title="Market" subtitle="symbol and streams">
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Symbol" hint="switching resets the rings and re-hydrates from the server snapshot">
                <Select value={prefs.symbol ?? conn.symbol} onChange={(e) => setPrefs({ symbol: e.target.value })}>
                  {conn.symbols.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field as="div" label="Order book stream" hint="5 Hz top levels and depth profile · off saves bandwidth">
                <Switch checked={prefs.bookSubscribed} onChange={(v) => setPrefs({ bookSubscribed: v })} label="Stream the order book" />
              </Field>
            </div>
            <Divider className="my-4" />
            <h3 className="col-head mb-1">Data source</h3>
            <dl className="grid gap-x-8 md:grid-cols-2">
              <KV k="Source">
                <Badge tone={conn.source === "live" ? "good" : "warning"}>{conn.source}</Badge>
              </KV>
              <KV k="Time scale">{conn.timeScale}×</KV>
              <KV k="Engine version">{conn.hello?.version ?? "—"}</KV>
              <KV k="Environment">{health.data?.environment ?? "—"}</KV>
              <KV k="Uptime">{health.data && now ? fmtAgo(now - health.data.uptime_seconds * 1000, now) : "—"}</KV>
            </dl>
            <p className="hint mt-2">The data source is set on the server (DATA_SOURCE = live, replay or synthetic).</p>
          </Panel>

          <Panel id="display" className="scroll-mt-20" icon={MonitorCog} title="Display" subtitle="motion, quality and ambience">
            <div className="grid gap-5 md:grid-cols-2">
              <Field as="div" label="Performance tier" hint={`detected: ${ui.detectedTier ?? "detecting…"} · in use: ${tier}`}>
                <SegmentedControl<PerfTier>
                  label="Performance tier"
                  value={prefs.perfTier}
                  onChange={(v) => setPrefs({ perfTier: v })}
                  items={[
                    { value: "auto", label: "auto" },
                    { value: "low", label: "low" },
                    { value: "mid", label: "mid" },
                    { value: "high", label: "high" },
                  ]}
                />
              </Field>
              <Field
                as="div"
                label="Motion"
                hint={`OS prefers reduced motion: ${ui.reducedMotionOS ? "yes" : "no"} · in use: ${motion ? "full" : "reduced"}`}
              >
                <SegmentedControl<MotionPref>
                  label="Motion"
                  value={prefs.motion}
                  onChange={(v) => setPrefs({ motion: v })}
                  items={[
                    { value: "auto", label: "auto" },
                    { value: "reduced", label: "reduced" },
                    { value: "full", label: "full" },
                  ]}
                />
              </Field>
              <Field
                as="div"
                label={`Ambient tint · ${prefs.accentIntensity.toFixed(2)}`}
                hint="strength of the regime-coloured light behind the page"
              >
                <input
                  type="range"
                  min={0}
                  max={2}
                  step={0.05}
                  value={prefs.accentIntensity}
                  onChange={(e) => setPrefs({ accentIntensity: Number(e.target.value) })}
                  className="slider"
                  aria-label="Ambient tint"
                />
              </Field>
              <div className="flex items-end">
                <Button variant="ghost" onClick={() => setPrefs({ ...DEFAULT_PREFS })}>
                  <RotateCcw size={14} /> Reset preferences
                </Button>
              </div>
            </div>
            <Divider className="my-4" />
            <div className="grid gap-x-8 gap-y-4 md:grid-cols-2">
              <div>
                <h3 className="col-head mb-1.5">What the tiers change</h3>
                <ul className="space-y-1 text-meta text-ink-muted">
                  <li>
                    <span className="text-ink">low</span> · terrain on a 64 × 48 mesh at 30 fps, 512 trade particles, 1× pixel ratio
                  </li>
                  <li>
                    <span className="text-ink">mid</span> · full 128 × 96 mesh, 1 024 particles, up to 1.5× pixel ratio
                  </li>
                  <li>
                    <span className="text-ink">high</span> · full mesh, 2 048 particles, up to 1.5× pixel ratio
                  </li>
                  <li>The heatmap and every 2D chart are the same on all tiers.</li>
                </ul>
              </div>
              <div>
                <h3 className="col-head mb-1.5">Reduced motion</h3>
                <ul className="space-y-1 text-meta text-ink-muted">
                  <li>No entrance animation; counters snap to new values; the terrain camera cuts instead of gliding.</li>
                  <li>Trade particles are off; the regime tint changes without a fade.</li>
                  <li>Data and layout are unchanged.</li>
                </ul>
              </div>
            </div>
          </Panel>

          <Panel id="connection" className="scroll-mt-20" icon={Cable} title="Connection" subtitle="this browser ↔ engine">
            <dl className="grid gap-x-8 md:grid-cols-2">
              <KV k="Status">
                <Status tone={conn.status === "open" ? "good" : conn.status === "closed" ? "critical" : "warning"}>{conn.status}</Status>
              </KV>
              <KV k="Round trip">{conn.latencyMs != null ? `${conn.latencyMs} ms` : "—"}</KV>
              <KV k="Clock offset">{`${conn.serverOffsetMs >= 0 ? "+" : "−"}${Math.abs(conn.serverOffsetMs)} ms`}</KV>
              <KV k="Reconnect attempts">{conn.attempt}</KV>
              <KV k="Channels">{conn.channels.length}</KV>
              <KV k="API">{API_URL}</KV>
              <KV k="WebSocket">{WS_URL}</KV>
            </dl>
          </Panel>

          <AccessPanel />

          <Panel
            id="engine"
            className="scroll-mt-20"
            icon={Server}
            title="Engine"
            subtitle={`/system/metrics · ${conn.symbol}`}
            actions={metrics.isError && <Badge tone="critical">unreachable</Badge>}
          >
            {!sym && <div className="skeleton h-24" />}
            {sym && (
              <>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
                  <MetricTile label="events / s" value={sym.event_rate_per_s?.toFixed(1) ?? "—"} />
                  <MetricTile label="trades" value={sym.trades?.toLocaleString() ?? "—"} />
                  <MetricTile label="book diffs" value={sym.diffs?.toLocaleString() ?? "—"} hint={`${sym.dropped_diffs ?? 0} dropped`} />
                  <MetricTile label="bars closed" value={sym.bars_closed?.toLocaleString() ?? "—"} />
                  <MetricTile
                    label="clock skew"
                    value={sym.clock_skew_ms != null ? `${sym.clock_skew_ms.toFixed(0)} ms` : "n/a"}
                    hint="exchange − local"
                  />
                  <MetricTile label="resyncs" value={resyncs} hint={sym.book?.state} />
                </div>
                <div className="mt-4 grid gap-x-8 gap-y-3 md:grid-cols-3">
                  <div>
                    <h3 className="col-head mb-1">Book</h3>
                    <dl>
                      <KV k="State">
                        <Status tone={sym.book?.state === "synced" ? "good" : "warning"}>{sym.book?.state ?? "—"}</Status>
                      </KV>
                      <KV k="Levels">{sym.book?.levels?.toLocaleString() ?? "—"}</KV>
                      <KV k="Updates applied">{sym.book?.updates_applied?.toLocaleString() ?? "—"}</KV>
                      <KV k="Resyncs">
                        <Status tone={resyncs > 0 ? "warning" : undefined}>{resyncs}</Status>
                      </KV>
                      <KV k="Source status">{sym.source?.status ?? "—"}</KV>
                    </dl>
                  </div>
                  <div>
                    <h3 className="col-head mb-1">Intelligence</h3>
                    <dl>
                      <KV k="Model">{`${sym.ml?.status ?? "—"} · v${sym.ml?.version ?? 0}`}</KV>
                      <KV k="Samples">{sym.ml?.samples?.toLocaleString() ?? "—"}</KV>
                      <KV k="Regime">{`${sym.regime?.label ?? "—"} · ${sym.regime?.source ?? ""}`}</KV>
                      <KV k="Backtests running">{m?.market?.backtests_running?.length ?? 0}</KV>
                    </dl>
                  </div>
                  <div>
                    <h3 className="col-head mb-1">Persistence and alerts</h3>
                    <dl>
                      <KV k="Bars written">{m?.market?.writer?.written?.toLocaleString() ?? "—"}</KV>
                      <KV k="Failed flushes">
                        <Status tone={failedFlushes > 0 ? "critical" : undefined}>{failedFlushes}</Status>
                      </KV>
                      <KV k="Alert checks">{`${m?.market?.alerts?.evaluations?.toLocaleString() ?? "—"} · ${m?.market?.alerts?.fired ?? 0} fired`}</KV>
                      <KV k="Discord">
                        {m?.market?.alerts?.discord?.enabled ? `on · ${m.market.alerts.discord.sent ?? 0} sent` : "not configured"}
                      </KV>
                      <KV k="WebSocket clients">{`${m?.ws?.clients ?? 0} · ${m?.ws?.total_sent?.toLocaleString() ?? 0} frames`}</KV>
                    </dl>
                  </div>
                </div>
              </>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}

/**
 * Where changes are gated (production), the admin token that allows them.
 * It stays in this browser; the server checks it on every change.
 */
function AccessPanel() {
  const access = useAccess();
  const qc = useQueryClient();
  const [draft, setDraft] = useState("");
  const stored = useSyncExternalStore(
    subscribeAdminToken,
    () => Boolean(readAdminToken()),
    () => false,
  );
  const save = (token: string | null) => {
    writeAdminToken(token);
    setDraft("");
    void qc.invalidateQueries({ queryKey: ["access"] });
  };
  const a = access.data;

  return (
    <Panel id="access" className="scroll-mt-20" icon={KeyRound} title="Access" subtitle="who may change strategies and alert rules">
      <dl className="mb-4 grid gap-x-8 md:grid-cols-2">
        <KV k="This server">{a ? (a.writes_require_auth ? "changes need the admin token" : "open: changes need no token") : "—"}</KV>
        <KV k="This browser">
          {a ? <Status tone={a.can_write ? "good" : "warning"}>{a.can_write ? "may make changes" : "read-only"}</Status> : "—"}
        </KV>
      </dl>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (draft.trim()) save(draft.trim());
        }}
      >
        <Field label="Admin token" className="min-w-0 flex-1">
          <Input
            type="password"
            autoComplete="off"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={stored ? "•••••••• (saved)" : "paste the server's ADMIN_TOKEN"}
          />
        </Field>
        <Button type="submit" variant="primary" disabled={!draft.trim()}>
          Save
        </Button>
        <Button onClick={() => save(null)} disabled={!stored}>
          Forget
        </Button>
      </form>
      <p className="hint mt-1.5">Kept in this browser only and sent with every request; the server checks it on each change.</p>
    </Panel>
  );
}
