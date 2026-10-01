"use client";

import { ScrollText } from "lucide-react";
import { useMemo } from "react";

import { Badge, Panel } from "@/components/ds";
import { fmtPrice, fmtQty, fmtTime } from "@/lib/format";
import { useConnection, useTrades } from "@/lib/store";
import { COLORS, rgba } from "@/lib/theme";
import { aggregatePrints } from "@/lib/tape";

const COLS = "grid grid-cols-[1fr_1.1fr_1fr_2rem_3rem] gap-3";

export function TradeTape({ rows = 18, className }: { rows?: number; className?: string }) {
  const trades = useTrades();
  const base = useConnection().symbol.replace(/USDT$/, "");
  const { prints, ref, buyShare } = useMemo(() => {
    const all = aggregatePrints(trades);
    // the size scale is the 90th percentile of recent prints, so one block trade doesn't flatten the rest
    const sizes = all.map((p) => p.qty).sort((a, b) => a - b);
    const p90 = sizes[Math.floor(sizes.length * 0.9)] ?? 0;
    let bought = 0;
    let total = 0;
    for (const p of all) {
      total += p.qty;
      if (p.side === "buy") bought += p.qty;
    }
    return { prints: all.slice(0, rows), ref: Math.max(p90, 1e-9), buyShare: total ? bought / total : null };
  }, [trades, rows]);

  return (
    <Panel
      className={className}
      icon={ScrollText}
      title="Tape"
      subtitle={`${trades.length} fills · sweeps merged`}
      actions={
        buyShare == null ? (
          <Badge>no fills yet</Badge>
        ) : (
          <Badge tone={buyShare >= 0.5 ? "bid" : "ask"}>{(buyShare * 100).toFixed(0)}% bought</Badge>
        )
      }
      padded={false}
    >
      <div className={`${COLS} col-head px-6 pb-1.5`}>
        <span>Time</span>
        <span className="text-right">Price</span>
        <span className="text-right">Size {base}</span>
        <span className="text-right">Fills</span>
        <span className="text-right">Side</span>
      </div>
      <ul className="num min-h-0 flex-1 overflow-hidden px-2 pb-2 text-body">
        {prints.length === 0 && <li className="px-4 py-3 text-meta text-ink-faint">Waiting for prints…</li>}
        {prints.map((p) => {
          const rel = p.qty / ref;
          const large = rel >= 2;
          const color = p.side === "buy" ? COLORS.bid : COLORS.ask;
          return (
            <li
              key={p.key}
              className={`row ${COLS} items-center px-4 py-[3px]`}
              title={p.fills > 1 ? `${p.fills} fills from ${fmtPrice(p.lo, 2)} to ${fmtPrice(p.hi, 2)}` : undefined}
            >
              <span className="text-ink-faint">{fmtTime(p.from)}</span>
              <span className={`text-right text-ink ${large ? "font-medium" : ""}`}>{fmtPrice(p.notional / p.qty, 2)}</span>
              {/* the size bar grows leftward from the figure, on the aggressor's colour */}
              <span className={`relative text-right ${large ? "font-medium text-ink" : "text-ink-muted"}`}>
                <span
                  className="pointer-events-none absolute -inset-y-px right-0 rounded-sm"
                  style={{ width: `${Math.min(100, Math.sqrt(rel) * 45)}%`, background: rgba(color, large ? 0.28 : 0.14) }}
                  aria-hidden
                />
                <span className="relative">{fmtQty(p.qty, 4)}</span>
              </span>
              <span className="text-right text-meta text-ink-faint">{p.fills > 1 ? `×${p.fills}` : ""}</span>
              <span className="flex items-center justify-end gap-1.5 text-meta text-ink-muted">
                <span className={`h-1.5 w-1.5 rounded-full ${p.side === "buy" ? "bg-bid" : "bg-ask"}`} aria-hidden />
                {p.side}
              </span>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
