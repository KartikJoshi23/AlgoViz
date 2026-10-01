"use client";

import { Layers3 } from "lucide-react";
import type { ReactNode } from "react";

import { DepthCurve } from "@/components/charts/DepthCurve";
import { Panel, Switch } from "@/components/ds";
import { fmtPrice, fmtQty, fmtSigned } from "@/lib/format";
import { useBook, useConnection, useStore } from "@/lib/store";

function Touch({ label, dot, children, align = "left" }: { label: string; dot?: string; children: ReactNode; align?: "left" | "right" }) {
  return (
    <div className={`min-w-0 ${align === "right" ? "text-right" : ""}`}>
      <div className={`col-head flex items-center gap-1.5 ${align === "right" ? "justify-end" : ""}`}>
        {dot && <span className={`h-1.5 w-1.5 rounded-full ${dot}`} aria-hidden />}
        {label}
      </div>
      <div className="num mt-0.5 truncate text-body text-ink">{children}</div>
    </div>
  );
}

export function BookPanel({ height = 200, className }: { height?: number; className?: string }) {
  const book = useBook();
  const base = useConnection().symbol.replace(/USDT$/, "");
  const subscribed = useStore((s) => s.prefs.bookSubscribed);
  const setPrefs = useStore((s) => s.setPrefs);

  return (
    <Panel
      className={className}
      icon={Layers3}
      title="Order book"
      subtitle={book ? `${book.levels} levels · #${book.update_id}` : "L2 reconstruction"}
      actions={<Switch checked={subscribed} onChange={(v) => setPrefs({ bookSubscribed: v })} label="Live" />}
    >
      <DepthCurve height={height} />
      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 border-t border-line pt-3">
        <Touch label="Best bid" dot="bg-bid">
          {book ? (
            <>
              {fmtPrice(book.bids[0]?.[0], 2)} <span className="text-ink-faint">× {fmtQty(book.bids[0]?.[1], 3)}</span>
            </>
          ) : (
            "—"
          )}
        </Touch>
        <Touch label="Best ask" dot="bg-ask" align="right">
          {book ? (
            <>
              <span className="text-ink-faint">{fmtQty(book.asks[0]?.[1], 3)} ×</span> {fmtPrice(book.asks[0]?.[0], 2)}
            </>
          ) : (
            "—"
          )}
        </Touch>
        <Touch label="Liquidity ±10 bps">{book ? `${fmtQty(book.liquidity_10bps, 1)} ${base}` : "—"}</Touch>
        <Touch label="Order-flow imbalance 1 s" align="right">
          {book ? fmtSigned(book.ofi_1s, 2) : "—"}
        </Touch>
      </div>
    </Panel>
  );
}
