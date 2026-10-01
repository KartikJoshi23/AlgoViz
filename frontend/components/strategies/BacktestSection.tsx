"use client";

import { useQueryClient } from "@tanstack/react-query";
import { CircleAlert, FlaskConical, Play, TrendingUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { EquityChart } from "@/components/charts/EquityChart";
import { Badge, Button, Field, Input, Panel, SegmentedControl, Select, TableWrap } from "@/components/ds";
import { MetricTile } from "@/components/ui/PageHeader";
import { useBacktestDetail, useBacktests, useStrategyMutations, type Backtest, type BacktestTrade } from "@/lib/api/hooks";
import { fmtDuration, fmtPrice, fmtSigned, fmtTime } from "@/lib/format";
import { useConnection, useStore } from "@/lib/store";

const money = (v: number) => `${v >= 0 ? "+" : "−"}$${Math.abs(v).toFixed(2)}`;

function windowMinutes(b: Backtest): number | null {
  if (!b.start_time || !b.end_time) return null;
  return Math.round((new Date(b.end_time).getTime() - new Date(b.start_time).getTime()) / 60_000);
}

function StatusChip({ status }: { status: string }) {
  const tone = status === "completed" ? "good" : status === "failed" ? "critical" : "accent";
  return <Badge tone={tone}>{status}</Badge>;
}

function Failure({ children }: { children: React.ReactNode }) {
  return (
    <div role="alert" className="flex items-start gap-2 rounded-lg border border-critical/40 bg-critical/10 px-3 py-2 text-meta text-ink">
      <CircleAlert size={14} className="mt-0.5 shrink-0 text-critical" aria-hidden />
      {children}
    </div>
  );
}

type SideFilter = "all" | "long" | "short";
type OutcomeFilter = "all" | "win" | "loss";

/** The run's trades, filterable by side, outcome and exit reason. */
function TradeTable({ trades }: { trades: BacktestTrade[] }) {
  const [side, setSide] = useState<SideFilter>("all");
  const [outcome, setOutcome] = useState<OutcomeFilter>("all");
  const [reason, setReason] = useState("");
  const reasons = useMemo(() => [...new Set(trades.map((t) => t.reason))].sort(), [trades]);
  const rows = trades.filter(
    (t) =>
      (side === "all" || t.side === side) &&
      (outcome === "all" || (outcome === "win" ? t.pnl > 0 : t.pnl <= 0)) &&
      (!reason || t.reason === reason),
  );

  return (
    <section aria-label="Trades" className="mt-5">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h3 className="text-ui font-medium text-ink">Trades</h3>
        <span className="num text-meta text-ink-faint">
          {rows.length} of {trades.length}
        </span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <SegmentedControl<SideFilter>
            label="Side"
            value={side}
            onChange={setSide}
            items={[
              { value: "all", label: "All" },
              { value: "long", label: "Long" },
              { value: "short", label: "Short" },
            ]}
          />
          <SegmentedControl<OutcomeFilter>
            label="Outcome"
            value={outcome}
            onChange={setOutcome}
            items={[
              { value: "all", label: "All" },
              { value: "win", label: "Winners" },
              { value: "loss", label: "Losers" },
            ]}
          />
          <Select value={reason} onChange={(e) => setReason(e.target.value)} className="h-8 w-auto text-meta" aria-label="Exit reason">
            <option value="">any exit</option>
            {reasons.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </Select>
        </div>
      </div>
      <TableWrap label="Backtest trades" maxHeight={360}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Side</th>
              <th>Entry</th>
              <th className="cell-num">Entry price</th>
              <th className="cell-num">Exit price</th>
              <th className="cell-num">Hold</th>
              <th className="cell-num">bps</th>
              <th className="cell-num">P&amp;L</th>
              <th>Exit reason</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 500).map((t, i) => (
              <tr key={i}>
                <td>
                  <span className="flex items-center gap-1.5">
                    <span className={`h-1.5 w-1.5 rounded-full ${t.side === "long" ? "bg-bid" : "bg-ask"}`} aria-hidden />
                    {t.side}
                  </span>
                </td>
                <td className="num text-ink-muted">{fmtTime(t.entry_ts)}</td>
                <td className="cell-num">{fmtPrice(t.entry_price, 2)}</td>
                <td className="cell-num">{fmtPrice(t.exit_price, 2)}</td>
                <td className="cell-num text-ink-muted">{fmtDuration(t.hold_s)}</td>
                <td className={`cell-num ${t.pnl_bps >= 0 ? "text-bid-text" : "text-ask-text"}`}>{fmtSigned(t.pnl_bps, 1)}</td>
                <td className={`cell-num ${t.pnl >= 0 ? "text-bid-text" : "text-ask-text"}`}>{money(t.pnl)}</td>
                <td className="text-ink-muted">{t.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
      {rows.length > 500 && <p className="hint mt-2">Showing the first 500 matching trades.</p>}
    </section>
  );
}

export function BacktestSection({ strategyId }: { strategyId: number }) {
  const qc = useQueryClient();
  const conn = useConnection();
  const addToast = useStore((s) => s.addToast);
  const progress = useStore((s) => s.backtests);
  const { backtest } = useStrategyMutations();
  const list = useBacktests(strategyId);
  const [selected, setSelected] = useState<number | null>(null);
  const [params, setParams] = useState({ lookback_minutes: 240, initial_capital: 10_000, commission_bps: 1, slippage_bps: 0.5 });

  const runs = list.data?.items;
  const effectiveId = selected ?? runs?.[0]?.id ?? null;
  const detail = useBacktestDetail(strategyId, effectiveId);
  const live = effectiveId != null ? progress[effectiveId] : undefined;

  // when the live job for the selected run finishes, refresh the persisted rows
  useEffect(() => {
    if (!live || (live.status !== "completed" && live.status !== "failed")) return;
    void qc.invalidateQueries({ queryKey: ["backtests", strategyId] }, { cancelRefetch: true });
    void qc.invalidateQueries({ queryKey: ["backtest", strategyId, live.backtest_id] }, { cancelRefetch: true });
  }, [live, qc, strategyId]);

  const run = async () => {
    try {
      const row = await backtest.mutateAsync({ id: strategyId, body: { ...params, symbol: conn.symbol } });
      setSelected(row.id);
      addToast({ tone: "accent", title: "Backtest started", body: `#${row.id} · ${params.lookback_minutes} min lookback` });
    } catch (e) {
      addToast({ tone: "critical", title: "Backtest rejected", body: (e as Error).message });
    }
  };

  const d = detail.data;
  // the persisted row is authoritative once it has settled; WS progress fills the gap before that
  const settled = d?.status === "completed" || d?.status === "failed";
  const running = !settled && !!live && live.status !== "completed" && live.status !== "failed";
  const trades = d?.trades ?? [];
  const failed = d?.status === "failed" ? ((d.trades?.[0] as { error?: string } | undefined)?.error ?? "failed") : null;
  const mins = d ? windowMinutes(d) : null;
  const avgBps = trades.length ? trades.reduce((a, t) => a + t.pnl_bps, 0) / trades.length : null;
  // Sharpe and Sortino are annualised from 1-minute returns; over less than a day that says little
  const ratioHint = mins != null && mins < 1440 ? `annualised from ${mins} min: not meaningful yet` : "annualised from 1-min returns";
  const field = (key: keyof typeof params) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setParams({ ...params, [key]: Number(e.target.value) });

  return (
    <div className="space-y-3">
      <Panel
        className="@container"
        icon={FlaskConical}
        title="Backtest"
        subtitle="next-bar fills · slippage and commission · stops and targets on bar extremes"
        actions={
          <Button variant="primary" onClick={run} disabled={backtest.isPending}>
            <Play size={14} /> Run on {conn.symbol}
          </Button>
        }
      >
        <div className="grid grid-cols-2 gap-3 @2xl:grid-cols-4">
          <Field label="Lookback (min)" hint="synthetic history if too few real bars">
            <Input type="number" min={10} max={1440} className="num" value={params.lookback_minutes} onChange={field("lookback_minutes")} />
          </Field>
          <Field label="Initial capital ($)">
            <Input type="number" min={100} step={100} className="num" value={params.initial_capital} onChange={field("initial_capital")} />
          </Field>
          <Field label="Commission (bps / side)">
            <Input type="number" min={0} step={0.1} className="num" value={params.commission_bps} onChange={field("commission_bps")} />
          </Field>
          <Field label="Slippage (bps / fill)">
            <Input type="number" min={0} step={0.1} className="num" value={params.slippage_bps} onChange={field("slippage_bps")} />
          </Field>
        </div>

        {(runs?.length ?? 0) > 0 && (
          <div className="mt-4">
            <h3 className="col-head mb-1.5">Runs</h3>
            <ul className="max-h-40 space-y-px overflow-y-auto">
              {runs!.map((b) => {
                const p = progress[b.id];
                const st = p && p.status !== "completed" && p.status !== "failed" ? p.status : b.status;
                return (
                  <li key={b.id}>
                    <button
                      type="button"
                      onClick={() => setSelected(b.id)}
                      aria-current={b.id === effectiveId}
                      className="row flex w-full items-center gap-3 px-3 py-1.5 text-left text-meta"
                    >
                      <span className="num w-10 text-ink-faint">#{b.id}</span>
                      <span className="num text-ink-muted">{new Date(b.created_at).toLocaleTimeString([], { hour12: false })}</span>
                      <StatusChip status={st} />
                      {b.data_source === "synthetic" && <Badge tone="warning">synthetic</Badge>}
                      {b.status === "completed" && (
                        <span className="num ml-auto text-ink">
                          {fmtSigned(b.total_pnl_pct, 2, "%")} · {b.total_trades} trades
                        </span>
                      )}
                      {p && st === "running" && (
                        <span className="num ml-auto text-ink-faint">{Math.round((p.done / Math.max(p.total, 1)) * 100)}%</span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </Panel>

      {effectiveId != null && (
        <Panel
          className="@container"
          icon={TrendingUp}
          title={`Result #${effectiveId}`}
          subtitle={
            d
              ? `${d.symbol} · ${mins != null ? `${mins} min window` : "…"} · ${d.data_source === "synthetic" ? "synthetic history" : "recorded bars"}`
              : "loading…"
          }
          actions={
            <>
              {d?.data_source === "synthetic" && <Badge tone="warning">synthetic data</Badge>}
              {d && <StatusChip status={running ? live!.status : d.status} />}
            </>
          }
        >
          {running && (
            <div className="mb-3">
              <div className="mb-1 flex justify-between text-meta text-ink-muted">
                <span>
                  {live!.status === "queued" ? "Waiting for a free slot…" : live!.status === "loading" ? "Loading bars…" : "Simulating…"}
                </span>
                <span className="num">
                  {live!.done.toLocaleString()} / {live!.total.toLocaleString()} bars
                </span>
              </div>
              <div
                className="h-1.5 overflow-hidden rounded-full bg-control"
                role="progressbar"
                aria-label="Backtest progress"
                aria-valuemin={0}
                aria-valuemax={live!.total}
                aria-valuenow={live!.done}
              >
                <div
                  className="h-full rounded-full bg-accent transition-[width] duration-300"
                  style={{ width: `${(live!.done / Math.max(live!.total, 1)) * 100}%` }}
                />
              </div>
            </div>
          )}
          {live?.status === "failed" && <Failure>{live.error}</Failure>}
          {failed && !running && <Failure>{failed}</Failure>}

          {d && d.status === "completed" && (
            <>
              <div className="grid grid-cols-2 gap-2 @xl:grid-cols-4">
                <MetricTile
                  label="Net P&L"
                  value={money(d.total_pnl)}
                  hint={`${fmtSigned(d.total_pnl_pct, 2, "%")} on $${d.initial_capital.toLocaleString()}`}
                />
                <MetricTile label="Trades" value={d.total_trades} hint={`${(d.win_rate * 100).toFixed(0)}% winners`} />
                <MetricTile label="Average trade" value={avgBps != null ? `${fmtSigned(avgBps, 2)} bps` : "—"} hint="after costs" />
                <MetricTile label="Max drawdown" value={`${d.max_drawdown_pct.toFixed(2)}%`} hint="peak to trough" />
                <MetricTile
                  label="Sharpe"
                  value={Number.isFinite(d.sharpe_ratio) ? d.sharpe_ratio.toFixed(2) : "—"}
                  tone="muted"
                  hint={ratioHint}
                />
                <MetricTile
                  label="Sortino"
                  value={Number.isFinite(d.sortino_ratio) ? d.sortino_ratio.toFixed(2) : "—"}
                  tone="muted"
                  hint={ratioHint}
                />
                <MetricTile
                  label="Profit factor"
                  value={d.profit_factor >= 999 ? "∞" : d.profit_factor.toFixed(2)}
                  hint="gross profit / gross loss"
                />
                <MetricTile label="Exposure" value={`${d.exposure_pct.toFixed(0)}%`} hint="time in the market" />
              </div>
              <div className="mt-5">
                <EquityChart curve={(d.equity_curve ?? []) as number[][]} initialCapital={d.initial_capital} height={300} />
              </div>
              {trades.length > 0 && <TradeTable trades={trades} />}
              {trades.length === 0 && (
                <p className="mt-4 text-body text-ink-faint">No trades: the entry conditions never held in this window.</p>
              )}
            </>
          )}
        </Panel>
      )}
    </div>
  );
}
