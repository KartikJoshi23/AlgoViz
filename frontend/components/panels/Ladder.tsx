"use client";

import { Rows3 } from "lucide-react";

import { Panel } from "@/components/ds";
import { fmtPrice, fmtQty } from "@/lib/format";
import { useBook, useConnection } from "@/lib/store";
import { COLORS, rgba } from "@/lib/theme";

const COLS = "grid grid-cols-[1fr_1fr_1fr] items-center gap-2";

function Row({
  price,
  qty,
  cum,
  maxCum,
  maxQty,
  wall,
  side,
}: {
  price: number;
  qty: number;
  cum: number;
  maxCum: number;
  maxQty: number;
  wall: boolean;
  side: "bid" | "ask";
}) {
  const color = side === "ask" ? COLORS.ask : COLORS.bid;
  return (
    <div className={`row relative ${COLS} px-2 py-[3px] text-meta`}>
      {/* cumulative depth from the outside in */}
      <div
        className="pointer-events-none absolute inset-y-px rounded-sm transition-[width] duration-200"
        style={{ [side === "ask" ? "right" : "left"]: 0, width: `${(cum / maxCum) * 100}%`, background: rgba(color, 0.07) }}
        aria-hidden
      />
      <span className={`num relative ${side === "ask" ? "text-ask-text" : "text-bid-text"}`}>{fmtPrice(price, 2)}</span>
      {/* heat: the level's own size on the side's ramp */}
      <span className="relative flex justify-end">
        <span
          className={`num rounded-sm px-1.5 text-right text-ink ${wall ? "font-semibold" : ""}`}
          style={{ background: rgba(color, 0.06 + 0.5 * Math.sqrt(qty / maxQty)) }}
        >
          {fmtQty(qty, 4)}
        </span>
      </span>
      <span className="num relative text-right text-ink-faint">{fmtQty(cum, 3)}</span>
    </div>
  );
}

/**
 * Top-N ladder: asks stacked above the spread, bids below. Each level's size
 * is shaded on its side's ramp (relative to the largest level shown) and the
 * cumulative depth runs behind the row; levels ≥ 3× the median are walls.
 */
export function Ladder({ levels = 12, className = "" }: { levels?: number; className?: string }) {
  const book = useBook();
  const base = useConnection().symbol.replace(/USDT$/, "");
  const asks = (book?.asks ?? []).slice(0, levels);
  const bids = (book?.bids ?? []).slice(0, levels);
  const cum = (side: number[][]) => {
    let c = 0;
    return side.map((l) => (c += l[1] ?? 0));
  };
  const askCum = cum(asks);
  const bidCum = cum(bids);
  const maxCum = Math.max(askCum[askCum.length - 1] ?? 0, bidCum[bidCum.length - 1] ?? 0, 1e-9);
  const sizes = [...asks, ...bids].map((l) => l[1] ?? 0);
  const maxQty = Math.max(...sizes, 1e-9);
  const median = [...sizes].sort((a, b) => a - b)[Math.floor(sizes.length / 2)] ?? 0;
  const isWall = (q: number) => median > 0 && q >= 3 * median;
  const spread = book ? (book.asks[0]?.[0] ?? 0) - (book.bids[0]?.[0] ?? 0) : 0;

  return (
    <Panel
      className={className}
      icon={Rows3}
      title="Ladder"
      subtitle={book ? `top ${levels} · ${book.levels} levels synced · #${book.update_id}` : "waiting for the book"}
    >
      <div className={`${COLS} col-head mb-1 px-2`}>
        <span>Price</span>
        <span className="text-right">Size {base}</span>
        <span className="text-right">Cumulative</span>
      </div>
      <div className="space-y-px">
        {[...asks].reverse().map((l, i) => {
          const q = l[1] ?? 0;
          return (
            <Row
              key={`a${i}`}
              price={l[0] ?? 0}
              qty={q}
              cum={askCum[asks.length - 1 - i] ?? 0}
              maxCum={maxCum}
              maxQty={maxQty}
              wall={isWall(q)}
              side="ask"
            />
          );
        })}
      </div>
      <div className="num raised my-1 flex items-center justify-between px-2 py-1 text-caption">
        <span className="text-ink-faint">spread</span>
        <span className="text-ink">{book ? `${spread.toFixed(2)} · ${book.spread_bps.toFixed(3)} bps` : "—"}</span>
        <span className="text-ink-faint">μ {book ? fmtPrice(book.microprice, 2) : "—"}</span>
      </div>
      <div className="space-y-px">
        {bids.map((l, i) => {
          const q = l[1] ?? 0;
          return (
            <Row key={`b${i}`} price={l[0] ?? 0} qty={q} cum={bidCum[i] ?? 0} maxCum={maxCum} maxQty={maxQty} wall={isWall(q)} side="bid" />
          );
        })}
      </div>
    </Panel>
  );
}
