"use client";

import { ArrowLeftRight, ChartArea, Layers } from "lucide-react";
import type { ReactNode } from "react";

import { DepthCurve } from "@/components/charts/DepthCurve";
import { Strip } from "@/components/charts/Strip";
import { Badge, Divider, Panel, Switch, ZBadge } from "@/components/ds";
import { Ladder } from "@/components/panels/Ladder";
import { LiquidityHero } from "@/components/panels/LiquidityHero";
import { PageHeader } from "@/components/ui/PageHeader";
import { fmtBps, fmtPrice, fmtQty, fmtSigned } from "@/lib/format";
import { useBook, useConnection, useFeatures, useStore } from "@/lib/store";

function Stat({ label, children, extra }: { label: string; children: ReactNode; extra?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 py-0.5">
      <dt className="text-ink-faint">{label}</dt>
      <dd className="num flex items-center gap-2 text-ink">
        {extra}
        {children}
      </dd>
    </div>
  );
}

/** Resting size within ±5 / ±10 / ±25 bps of mid on one scale (the bands nest), then the book's shape. */
function LiquidityBands({ className }: { className?: string }) {
  const f = useFeatures();
  const base = useConnection().symbol.replace(/USDT$/, "");
  const bands = [
    { label: "±5 bps", v: f?.liquidity_5bps },
    { label: "±10 bps", v: f?.liquidity_10bps, z: f?.liquidity_z },
    { label: "±25 bps", v: f?.liquidity_25bps },
  ];
  const max = Math.max(...bands.map((b) => b.v ?? 0), 1e-9);
  return (
    <Panel className={className} icon={Layers} title="Liquidity bands" subtitle="resting size near mid · both sides · full local book">
      <div className="space-y-3">
        {bands.map((b) => (
          <div key={b.label} className="grid grid-cols-[3.75rem_1fr_7.5rem] items-center gap-3">
            <span className="text-meta text-ink-muted">{b.label}</span>
            <div className="h-2.5 rounded-sm bg-raised">
              <div
                className="h-full rounded-sm bg-accent transition-[width] duration-500 ease-out"
                style={{ width: `${((b.v ?? 0) / max) * 100}%` }}
              />
            </div>
            <span className="num flex items-center justify-end gap-2 text-body text-ink">
              {"z" in b && <ZBadge z={b.z} />}
              {fmtQty(b.v, 1)}
              <span className="stat-unit">{base}</span>
            </span>
          </div>
        ))}
      </div>
      <Divider className="my-4" />
      <dl className="grid grid-cols-1 gap-x-8 text-meta sm:grid-cols-2 xl:grid-cols-3">
        <Stat label="Book slope, bids">{f?.book_slope_bid != null ? `${f.book_slope_bid.toFixed(3)} ${base}/bps` : "—"}</Stat>
        <Stat label="Book slope, asks">{f?.book_slope_ask != null ? `${f.book_slope_ask.toFixed(3)} ${base}/bps` : "—"}</Stat>
        <Stat label="Imbalance, L1">{fmtSigned(f?.imbalance_l1, 3)}</Stat>
        <Stat label="Imbalance, weighted" extra={<ZBadge z={f?.imbalance_z} />}>
          {fmtSigned(f?.imbalance_w, 3)}
        </Stat>
        <Stat label="Microprice − mid">{fmtSigned(f?.microprice_dev_bps, 3, " bps")}</Stat>
        <Stat label="Spread" extra={<ZBadge z={f?.spread_z} />}>
          {fmtBps(f?.spread_bps)}
        </Stat>
      </dl>
    </Panel>
  );
}

export default function BookPage() {
  const conn = useConnection();
  const book = useBook();
  const base = conn.symbol.replace(/USDT$/, "");
  const subscribed = useStore((s) => s.prefs.bookSubscribed);
  const setPrefs = useStore((s) => s.setPrefs);

  return (
    <div className="space-y-3">
      <PageHeader
        eyebrow="Market depth"
        title="Order book"
        subtitle={`${conn.symbol} · full L2 reconstruction from the diff stream · resynced on gaps · depth profile at 5 Hz`}
        actions={
          <>
            {book && (
              <>
                <Badge tone="mid">
                  <span className="num">mid {fmtPrice(book.mid, 2)}</span>
                </Badge>
                <Badge>
                  <span className="num">{book.spread_bps.toFixed(3)} bps</span>
                </Badge>
                <Badge tone={book.ofi_1s >= 0 ? "bid" : "ask"}>
                  <span className="num">OFI 1 s {fmtSigned(book.ofi_1s, 2)}</span>
                </Badge>
              </>
            )}
            <Switch checked={subscribed} onChange={(v) => setPrefs({ bookSubscribed: v })} label="Live book" />
          </>
        }
      />

      <LiquidityHero height={520} />

      <div className="grid gap-3 lg:grid-cols-12">
        <div className="grid gap-3 lg:col-span-8">
          <Panel icon={ChartArea} title="Cumulative depth" subtitle="full book across the profile band · symmetric, clamped scale">
            <DepthCurve height={300} />
          </Panel>
          <LiquidityBands />
        </div>
        <Ladder className="lg:col-span-4" levels={10} />
      </div>

      <Panel icon={ArrowLeftRight} title="Flow" subtitle="per 1 s bar · last 5 minutes">
        <div className="grid gap-4 md:grid-cols-3">
          <Strip col="ofi" mode="bars" polarity height={110} label={`Order-flow imbalance (${base})`} format={(v) => fmtSigned(v, 3)} />
          <Strip col="imbalance_w" polarity height={110} label="Weighted imbalance" format={(v) => fmtSigned(v, 3)} />
          <Strip col="spread_bps" height={110} label="Spread (bps)" format={(v) => v.toFixed(4)} />
        </div>
      </Panel>
    </div>
  );
}
